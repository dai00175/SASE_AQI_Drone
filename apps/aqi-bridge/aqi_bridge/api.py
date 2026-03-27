"""
FastAPI WebSocket server that bridges PWA clients to the BLE drone.

Responsibilities
-----------------
* ``/ws`` — WebSocket endpoint: authenticates at handshake, receives control
  commands, broadcasts telemetry.
* ``/health`` — REST health-check returning BLE status, client count, queue
  metrics, and auth mode info.
* Manages a client registry (``set`` of active, authenticated-or-allowed WebSocket
  connections).  Unauthenticated clients are NEVER added to the registry.
* Runs a telemetry broadcast loop at a configurable rate.
* Pushes validated control commands into a bounded ``asyncio.Queue`` via
  ``enqueue_command_drop_oldest()`` — the **single** enqueue path.

WebSocket Authentication Policy
---------------------------------
  Three modes, set via ``WS_AUTH_MODE`` in config.py or the environment variable
  ``WS_AUTH_MODE``.  Token is passed as a query parameter:
    ws://host:port/ws?token=<TOKEN>

  disabled  — No auth checks.  All connections accepted.
              Suitable only for local dev on a trusted LAN.

  telemetry_only  — Token present and valid → authenticated (may send commands).
                    Token absent → unauthenticated (allowed but telemetry-only).
                    Token present but invalid → rejected (code 1008).

  required  — Token present and valid → accepted.
              Token absent OR invalid → rejected (code 1008, Policy Violation).
              Unauthenticated clients are never added to the registry.

  Enforcement order (required/telemetry_only):
    1. Parse token from query string.
    2. Evaluate auth result (allowed, authenticated) — see _check_ws_auth().
    3. If NOT allowed: close(1008) and return WITHOUT calling ws.accept() first
       (Starlette accepts before closing, so we close immediately after accept
        to properly signal rejection while the client sees a close frame).
    4. Register client in set ONLY if allowed.
    5. In telemetry_only mode, unauthenticated clients may receive
       telemetry but CANNOT send control commands.

Locking Rules
-------------
All shared-state access follows a strict two-rule contract:

  Rule 1 — Lock ONLY protects shared memory reads/writes.
    ``ble.telemetry_lock`` is acquired briefly to read ``ble.latest_telemetry``
    and copy the reference into a local variable.  The lock is released
    immediately after the copy.  No I/O of any kind occurs inside the lock.

  Rule 2 — All network I/O happens outside any lock.
    JSON serialisation, ws.send_text(), and client pruning all happen after
    the lock is released.  A slow or stalled client cannot block BLE
    notification processing.

  Rule 3 — Per-client send timeout (WS_SEND_TIMEOUT_S).
    Each ws.send_text() is wrapped in asyncio.wait_for().  If a client does
    not accept the frame within the deadline it is removed from the registry
    immediately, preventing cascading latency.

  Rule 4 — Client registry is asyncio-safe without an extra lock.
    All mutations (add on connect, discard on error/disconnect) happen on the
    same single-threaded asyncio event loop, so a plain ``set`` is safe.
    We always iterate over a ``list(clients)`` snapshot to avoid mutating the
    set while iterating.

Command Queue Policy
--------------------
  Policy: DROP_OLDEST
  Rationale: the newest command always represents current pilot intent.
             Sending a stale command from 200ms ago is dangerous.

  Implementation: ``enqueue_command_drop_oldest()`` is the **single** enqueue
  path.  It is called by the WebSocket handler and must not be bypassed.
  Rate-limited drop logging prevents log spam during bursts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Set

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from aqi_bridge.config import (
    ALLOW_DEBUG_CRASH,
    ALLOW_TOKEN_ROTATION,
    COMMAND_DROP_LOG_INTERVAL_S,
    COMMAND_QUEUE_SIZE,
    MAX_WS_CLIENTS,
    TELEMETRY_BROADCAST_HZ,
    WS_ALLOWED_ORIGINS,
    WS_AUTH_FAILURE_CLOSE_CODE,
    WS_AUTH_MODE,
    WS_AUTH_QUERY_PARAM,
    WS_AUTH_TOKEN,
    WS_BROADCAST_LOG_INTERVAL_S,
    WS_SEND_TIMEOUT_S,
)
from aqi_bridge.models import ControlCommand, TelemetryMessage

if TYPE_CHECKING:
    from aqi_bridge.ble import BLEDroneClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth startup check
# ---------------------------------------------------------------------------
_VALID_AUTH_MODES = frozenset({"disabled", "telemetry_only", "required"})
if WS_AUTH_MODE not in _VALID_AUTH_MODES:
    logger.error(
        "Invalid WS_AUTH_MODE=%r (must be one of: disabled, telemetry_only, required). "
        "Defaulting to 'required' for safety.",
        WS_AUTH_MODE,
    )

if WS_AUTH_MODE in ("telemetry_only", "required") and not WS_AUTH_TOKEN and not ALLOW_TOKEN_ROTATION:
    logger.warning(
        "WS_AUTH_MODE=%r but WS_AUTH_TOKEN is empty and ALLOW_TOKEN_ROTATION is False. "
        "No token is configured — set WS_AUTH_TOKEN environment variable. "
        "In 'required' mode all connections will be rejected.",
        WS_AUTH_MODE,
    )

logger.info("WebSocket auth mode: %s, token_rotation_allowed: %s", WS_AUTH_MODE, ALLOW_TOKEN_ROTATION)


# ---------------------------------------------------------------------------
# Command queue metrics  (module-level so they survive across coroutines)
# ---------------------------------------------------------------------------

class _QueueMetrics:
    """Simple counters for the command pipeline.  Thread-safe: single event loop."""
    __slots__ = (
        "commands_received",
        "commands_enqueued",
        "commands_dropped_oldest",
        "_last_drop_log_at",
        "clients_rejected_capacity",
    )

    def __init__(self) -> None:
        self.commands_received: int = 0
        self.commands_enqueued: int = 0
        self.commands_dropped_oldest: int = 0
        self._last_drop_log_at: float = 0.0
        self.clients_rejected_capacity: int = 0

    def reset(self) -> None:
        self.commands_received = 0
        self.commands_enqueued = 0
        self.commands_dropped_oldest = 0
        self._last_drop_log_at = 0.0


# Singleton metrics object shared across this module.
_metrics = _QueueMetrics()


# ---------------------------------------------------------------------------
# Drop-oldest enqueue helper  — SINGLE enqueue path for control commands
# ---------------------------------------------------------------------------

def enqueue_command_drop_oldest(
    queue: asyncio.Queue[ControlCommand],
    cmd: ControlCommand,
) -> None:
    """
    Push a new command into the queue, enforcing the queue size limit.

    TRADEOFF: Bounded Latency > Command Completeness
    Normally, queues block or reject input when full (QueueFull exception).
    Here, bounded latency is critical for drone control. A stale command
    is dangerous. If the queue is full, we intentionally evict the oldest
    command (front of queue) to make room for the newest command, ensuring
    the drone always executes the most recent pilot intent.

    This is the **only** function that may enqueue commands. All callers
    (WebSocket handler, deadman) must use this function.

    Parameters
    ----------
    queue:
        The bounded ``asyncio.Queue`` shared with the BLE command consumer.
    cmd:
        The validated ``ControlCommand`` to enqueue.

    - Increments ``_metrics.commands_received`` on every call.
    - Increments ``_metrics.commands_dropped_oldest`` when an old command
      is evicted.  Emits a rate-limited WARNING log (at most once per
      ``COMMAND_DROP_LOG_INTERVAL_S``) so bursts don't spam the log.
    - Increments ``_metrics.commands_enqueued`` on each successful enqueue.
    - Never raises ``QueueFull``.
    """
    _metrics.commands_received += 1

    if queue.full():
        # Evict oldest: discard the front-of-queue item
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass  # race: consumer drained it between full-check and get

        _metrics.commands_dropped_oldest += 1

        # Rate-limited drop log to avoid flooding during bursts
        now = time.monotonic()
        if now - _metrics._last_drop_log_at >= COMMAND_DROP_LOG_INTERVAL_S:
            logger.warning(
                "Command queue full — dropped oldest (total drops: %d, "
                "queue size: %d/%d, policy: drop_oldest)",
                _metrics.commands_dropped_oldest,
                queue.qsize(),
                COMMAND_QUEUE_SIZE,
            )
            _metrics._last_drop_log_at = now

    try:
        cmd.ts_enqueued = time.monotonic()
        queue.put_nowait(cmd)
        _metrics.commands_enqueued += 1
    except asyncio.QueueFull:
        # Should not happen after the drain above; guard defensively.
        logger.error(
            "Unexpected QueueFull after drain — command lost. "
            "This is a bug; please investigate."
        )


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _check_ws_auth(token: str | None) -> tuple[bool, bool, str]:
    """
    Evaluate authentication for a connecting WebSocket client.

    Parameters
    ----------
    token:
        The raw token string from the query parameter, or None if absent.

    Returns
    -------
    (allowed, authenticated, reason)
        allowed       — True if the connection should be accepted.
        authenticated — True if the client presented a valid token.
        reason        — Human-readable string for structured logging.

    Auth mode semantics:

      disabled        → (True, True, "auth disabled")

      telemetry_only  → token present and valid   → (True,  True,  "valid token")
                        token absent               → (True,  False, "no token (telemetry-only)")
                        token present but invalid  → (False, False, "invalid token")

      required        → token present and valid   → (True,  True,  "valid token")
                        token absent               → (False, False, "missing token")
                        token present but invalid  → (False, False, "invalid token")

      unknown         → (False, False, "unknown auth mode (fail-closed)")
    """
    import hmac
    import os

    mode = WS_AUTH_MODE
    
    # Reload token dynamically if rotation is allowed, otherwise use the startup constant
    correct_token = os.environ.get("WS_AUTH_TOKEN", "") if ALLOW_TOKEN_ROTATION else WS_AUTH_TOKEN

    if mode == "disabled":
        return True, True, "auth disabled"

    if mode == "telemetry_only":
        if token is None:
            return True, False, "no token (telemetry-only)"
        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(token, correct_token):
            return True, True, "valid token"
        return False, False, "invalid token"

    if mode == "required":
        if token is None:
            return False, False, "missing token"
        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(token, correct_token):
            return True, True, "valid token"
        return False, False, "invalid token"

    # Unknown mode — fail-closed
    return False, False, f"unknown auth mode {mode!r} (fail-closed)"


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app(
    ble: "BLEDroneClient",
    command_queue: asyncio.Queue[ControlCommand],
    loop_lag: list[float] = None,
    starvation_count: list[int] = None,
    ble_write_metrics: dict[str, float] = None,
) -> FastAPI:
    """
    Build and return the FastAPI application.

    Parameters
    ----------
    ble:
        Shared BLE client instance (for reading telemetry + connection state).
    command_queue:
        Bounded queue that feeds commands to the BLE write consumer.
    loop_lag:
        Mutable reference to the current event loop lag (seconds).
    starvation_count:
        Mutable reference to the total number of watchdog starvation events.
    """

    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="AQI Drone Bridge", version="1.0.0")

    cors_origins = ["*"] if "*" in WS_ALLOWED_ORIGINS else list(WS_ALLOWED_ORIGINS)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # --- client registry ------------------------------------------------
    # Plain set is safe: all mutations happen on the single asyncio event loop.
    # Only clients that PASS auth are ever added here.
    clients: Set[WebSocket] = set()
    authenticated_clients: Set[WebSocket] = set()

    # ----------------------------------------------------------------
    # Health + metrics endpoint
    # ----------------------------------------------------------------
    @app.get("/health")
    async def health() -> dict:
        import os
        token_configured = bool(os.environ.get("WS_AUTH_TOKEN", "")) if ALLOW_TOKEN_ROTATION else bool(WS_AUTH_TOKEN)
        return {
            "ble_connected": ble.connected.is_set(),
            "negotiated_mtu": ble.negotiated_mtu,
            "usable_payload_bytes": ble.usable_payload,
            "chunking_enabled": ble.chunking_enabled,
            "auth": {
                "mode": WS_AUTH_MODE,
                "token_configured": token_configured,
            },
            "ws_clients": {
                "total": len(clients),
                "capacity": MAX_WS_CLIENTS,
                "authenticated": len(authenticated_clients),
                "unauthenticated": len(clients) - len(authenticated_clients),
                "rejected_capacity": _metrics.clients_rejected_capacity,
            },
            "system": {
                "loop_lag_s": loop_lag[0] if loop_lag else 0.0,
                "starvation_events": starvation_count[0] if starvation_count else 0,
            },
            "ble_write": ble_write_metrics or {},
            "command_queue": {
                "size": command_queue.qsize(),
                "capacity": COMMAND_QUEUE_SIZE,
                "policy": "drop_oldest",
                "commands_received": _metrics.commands_received,
                "commands_enqueued": _metrics.commands_enqueued,
                "commands_dropped_oldest": _metrics.commands_dropped_oldest,
            },
        }

    # ----------------------------------------------------------------
    # Reliability / Debugging
    # ----------------------------------------------------------------
    if ALLOW_DEBUG_CRASH:
        @app.post("/debug/crash")
        async def crash() -> dict:
            """Intentionally raise an exception to test supervisor restart."""
            logger.warning("Setting crash flag on BLE client via /debug/crash")
            ble._trigger_crash = True
            return {"status": "crash_triggered"}

    # ----------------------------------------------------------------
    # WebSocket endpoint
    # ----------------------------------------------------------------
    @app.websocket("/ws")
    async def websocket_endpoint(
        ws: WebSocket,
        token: str | None = Query(default=None, alias=WS_AUTH_QUERY_PARAM),
    ) -> None:
        """
        WebSocket handler for PWA clients.

        Auth is evaluated BEFORE the client is added to the registry.
        Rejected clients receive a 1008 (Policy Violation) close frame.
        Unauthenticated clients (telemetry_only mode) are in the registry but
        may ONLY receive telemetry — control messages are silently dropped.
        """
        # --- Step 0: Enforce strict connection memory bounds -----------------
        if len(clients) >= MAX_WS_CLIENTS:
            logger.warning(
                "WS connection REJECTED from %s | reason=Registry full (%d/%d)",
                ws.client, len(clients), MAX_WS_CLIENTS
            )
            _metrics.clients_rejected_capacity += 1
            await ws.accept()
            # 1013 = Try Again Later
            await ws.close(code=1013, reason="Server at capacity")
            return

        # --- Step 1: Evaluate authentication ---------------------------------
        allowed, authenticated, reason = _check_ws_auth(token)

        # FastAPI's WebSocket requires accept() before close() can send a frame.
        await ws.accept()

        if not allowed:
            logger.warning(
                "WS connection REJECTED from %s | mode=%s | reason=%s",
                ws.client, WS_AUTH_MODE, reason,
            )
            await ws.close(code=WS_AUTH_FAILURE_CLOSE_CODE, reason="Policy Violation")
            return

        # --- Step 2: Register accepted client --------------------------------
        clients.add(ws)
        if authenticated:
            authenticated_clients.add(ws)

        logger.info(
            "WS client ACCEPTED from %s | mode=%s | authenticated=%s | "
            "reason=%s | total=%d (auth=%d)",
            ws.client, WS_AUTH_MODE, authenticated, reason,
            len(clients), len(authenticated_clients),
        )

        # --- Step 3: Message loop --------------------------------------------
        try:
            while True:
                raw = await ws.receive_text()

                # In telemetry_only mode, unauthenticated clients are telemetry-only.
                if not authenticated:
                    logger.debug(
                        "Control message from unauthenticated client %s dropped "
                        "(telemetry-only mode)",
                        ws.client,
                    )
                    continue

                _handle_control_message(
                    raw, 
                    command_queue, 
                    app.state.control_inhibited  # type: ignore[attr-defined]
                )

        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("WS client error")
        finally:
            clients.discard(ws)
            if authenticated:
                authenticated_clients.discard(ws)
            logger.info(
                "WS client DISCONNECTED from %s | authenticated=%s | "
                "total=%d (auth=%d)",
                ws.client, authenticated, len(clients), len(authenticated_clients),
            )

    # ----------------------------------------------------------------
    # Attach helpers as app state so main.py can access them
    # ----------------------------------------------------------------
    app.state.clients = clients  # type: ignore[attr-defined]
    app.state.authenticated_clients = authenticated_clients  # type: ignore[attr-defined]
    app.state.ble = ble          # type: ignore[attr-defined]

    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _handle_control_message(
    raw: str,
    queue: asyncio.Queue[ControlCommand],
    control_inhibited: list[bool] | None = None,
) -> None:
    """Validate incoming JSON and route to ``enqueue_command_drop_oldest``."""
    recv_time = time.monotonic()
    try:
        data = json.loads(raw)
        cmd = ControlCommand.model_validate(data)
        cmd.ts_received = recv_time
    except Exception as exc:
        logger.debug("Bad control message: %s — %s", exc, raw[:200])
        return

    # --- Deadman Safety Contract: Control Inhibition ---
    if control_inhibited and control_inhibited[0]:
        is_neutral_rearm = (
            getattr(cmd, "arm", False)
            and cmd.vx == 0.0
            and cmd.vy == 0.0
            and cmd.vz == 0.0
            and cmd.yaw == 0.0
        )
        if is_neutral_rearm:
            logger.warning("Explicit neutral RE-ARM received. Lifting control inhibition.")
            control_inhibited[0] = False
        else:
            # Drop all other inputs (like pegging the joystick forward)
            return

    # Single enqueue path — enforces drop-oldest policy.
    enqueue_command_drop_oldest(queue, cmd)


async def broadcast_telemetry_loop(
    ble: "BLEDroneClient",
    clients: Set[WebSocket],
    authenticated_clients: Set[WebSocket] | None = None,
) -> None:
    """
    Periodically snapshot the latest telemetry and fan-out to every
    connected WebSocket client.

    Design guarantees (see module docstring Locking Rules):
    - The BLE telemetry_lock is held for <<1 µs (one Python reference copy).
    - JSON serialisation happens outside the lock.
    - Each ws.send_text() has a hard deadline of WS_SEND_TIMEOUT_S.
    - Slow/stalled clients are removed without affecting other clients.
    - The broadcast rate is maintained via a fixed sleep interval, independent
      of how long individual sends take.
    """
    interval = 1.0 / TELEMETRY_BROADCAST_HZ
    last_sent: str | None = None          # avoid re-serialising unchanged data
    last_log_time = time.monotonic()
    total_dropped = 0
    total_cycles = 0

    while True:
        cycle_start = time.monotonic()

        try:
            await asyncio.sleep(interval)

            # ----------------------------------------------------------------
            # Step 1: Snapshot under lock (memory only — no I/O inside lock)
            # ----------------------------------------------------------------
            async with ble.telemetry_lock:
                telem = ble.latest_telemetry  # atomic reference copy

            if telem is None:
                continue

            # Defensive type guard: TelemetryMessage must be frozen (immutable).
            # If this fails, someone assigned a wrong type to latest_telemetry.
            assert isinstance(telem, TelemetryMessage), (
                f"Snapshot is {type(telem).__name__!r}, expected TelemetryMessage. "
                "Was latest_telemetry assigned a raw dict instead of a parsed model?"
            )

            # ----------------------------------------------------------------
            # Step 2: Serialise outside the lock
            # ----------------------------------------------------------------
            payload = telem.model_dump_json()

            # Skip unchanged telemetry (saves bandwidth on idle drone)
            if payload == last_sent:
                continue
            last_sent = payload

            # ----------------------------------------------------------------
            # Step 3: Fan-out with per-client timeout — no lock held
            # ----------------------------------------------------------------
            snapshot = list(clients)   # safe: iterate a local copy
            n_clients = len(snapshot)
            dead: list[WebSocket] = []

            for ws in snapshot:
                try:
                    if ws.client_state != WebSocketState.CONNECTED:
                        dead.append(ws)
                        continue
                    # Hard deadline: if send stalls the client is dropped
                    await asyncio.wait_for(
                        ws.send_text(payload),
                        timeout=WS_SEND_TIMEOUT_S,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "WS client %s timed out after %.0fms — dropping",
                        ws.client, WS_SEND_TIMEOUT_S * 1000,
                    )
                    dead.append(ws)
                except Exception:
                    dead.append(ws)

            # ----------------------------------------------------------------
            # Step 4: Prune dead clients (outside lock, outside send loop)
            # ----------------------------------------------------------------
            for ws in dead:
                clients.discard(ws)
                if authenticated_clients is not None:
                    authenticated_clients.discard(ws)
            if dead:
                total_dropped += len(dead)
                logger.info(
                    "Pruned %d dead WS client(s) — %d remaining",
                    len(dead), len(clients),
                )

            # ----------------------------------------------------------------
            # Step 5: Periodic performance summary log
            # ----------------------------------------------------------------
            total_cycles += 1
            now = time.monotonic()
            cycle_ms = (now - cycle_start) * 1000

            if now - last_log_time >= WS_BROADCAST_LOG_INTERVAL_S:
                logger.debug(
                    "Broadcast summary [last %.0fs]: %d cycles | "
                    "%d clients | %d total dropped | last cycle %.2fms",
                    WS_BROADCAST_LOG_INTERVAL_S,
                    total_cycles,
                    n_clients,
                    total_dropped,
                    cycle_ms,
                )
                last_log_time = now
                total_cycles = 0
                total_dropped = 0

        except asyncio.CancelledError:
            logger.info("Telemetry broadcast loop cancelled")
            raise
        except Exception:
            logger.exception("Error in broadcast loop")
            await asyncio.sleep(1)
