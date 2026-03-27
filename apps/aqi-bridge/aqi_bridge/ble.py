"""
Async BLE central that connects to the Arduino drone peripheral.

Responsibilities
-----------------
* Scan for the device by advertised name.
* Connect, log negotiated MTU, and subscribe to telemetry notifications.
* Reassemble fragmented telemetry via newline-delimited byte buffer.
* Optionally reassemble chunked frames if payload < direct-send threshold.
* Validate parsed telemetry with Pydantic; store atomic snapshot.
* Expose ``_write_command_bytes`` for writing control JSON — INTERNAL USE ONLY.
* Auto-reconnect forever on BLE disconnect.

BLE WRITE SERIALIZATION RULE
-----------------------------
  ``_write_command_bytes`` is NOT safe for concurrent use. All BLE writes must
  flow through a single command consumer coroutine (main.command_consumer_loop).
  No other code path may call ``_write_command_bytes`` directly.

  Enforcement layers:
    1. The method is prefixed with ``_`` to signal internal-only access.
    2. An asyncio.Lock (``_write_lock``) wraps every bleak write as a
       defense-in-depth fallback.  It should never contend in correct operation.
    3. A ``writes_in_flight`` counter is incremented before and decremented
       after every write.  If writes_in_flight > 1 an error is logged — this
       indicates a concurrency bug that must be fixed immediately.

MTU Strategy
------------
ArduinoBLE default ATT MTU = 23 bytes → max notification payload = 20 bytes.
Our telemetry JSON is ~200 bytes, so it will fragment.

Two-layer strategy:
  Layer 1 — Byte-buffer reassembly (always active):
    Appends every notification chunk into a bytearray; extracts complete
    newline-terminated frames.  Handles fragmentation at the L2CAP level
    transparently via bleak.

  Layer 2 — Chunked framing protocol (active when MTU payload < threshold):
    Arduino sends:  <seq>|<total>|<idx>|<data>\n
    Bridge collects all chunks for a seq_id and reassembles the full JSON.

Thread safety: ``latest_telemetry`` is assigned atomically (CPython).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import zlib
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from aqi_bridge.config import (
    BLE_CONNECTION_TIMEOUT_S,
    BLE_CRC_REQUIRED,
    BLE_DEFAULT_PAYLOAD_BYTES,
    BLE_DEVICE_NAME,
    BLE_MIN_DIRECT_PAYLOAD_BYTES,
    BLE_OVERHEAD_BYTES,
    BLE_RECONNECT_DELAY_S,
    BLE_SCAN_TIMEOUT_S,
    BLE_TARGET_MTU_BYTES,
    BLE_USE_BINARY_COMMANDS,
    CHUNK_ASSEMBLY_TIMEOUT_S,
    CHUNK_MAX_MESSAGE_SIZE,
    COMMAND_CHAR_UUID,
    MAX_TELEMETRY_BUFFER_SIZE,
    MAX_TELEMETRY_JSON_BYTES,
    TELEMETRY_CHAR_UUID,
    USE_WRITE_WITH_RESPONSE,
)
from aqi_bridge.models import ControlCommand, TelemetryMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-sequence chunk assembly record
# ---------------------------------------------------------------------------
class _ChunkAssembly:
    """Accumulates chunks for a single sequence until all arrive or it times out."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.chunks: dict[int, bytes] = {}
        self.created_at = time.monotonic()

    def add(self, index: int, data: bytes) -> None:
        self.chunks[index] = data

    @property
    def complete(self) -> bool:
        return len(self.chunks) == self.total

    def assemble(self) -> bytes:
        return b"".join(self.chunks[i] for i in range(self.total))

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created_at) > CHUNK_ASSEMBLY_TIMEOUT_S


# ---------------------------------------------------------------------------
# Main BLE client
# ---------------------------------------------------------------------------
class BLEDroneClient:
    """Manages the BLE connection to a single Arduino drone peripheral."""

    def __init__(self) -> None:
        # --- public state (read by other modules) --------------------------
        self.connected: asyncio.Event = asyncio.Event()
        self.latest_telemetry: Optional[TelemetryMessage] = None
        self.telemetry_lock: asyncio.Lock = asyncio.Lock()

        # negotiated MTU info (set on connect)
        self.negotiated_mtu: int = 23                     # conservative default
        self.usable_payload: int = BLE_DEFAULT_PAYLOAD_BYTES  # 20 bytes
        self.chunking_enabled: bool = True                # always-on until we know better

        # --- BLE write serialization enforcement ----------------------------
        # Defense-in-depth lock: wraps every call to write_gatt_char.
        # Should never contend under correct single-writer design.
        self._write_lock: asyncio.Lock = asyncio.Lock()
        # Incremented before / decremented after every write attempt.
        # writes_in_flight > 1 means concurrent writes — a definite bug.
        self.writes_in_flight: int = 0

        # --- internal -------------------------------------------------------
        self._client: Optional[BleakClient] = None
        self._buffer: bytearray = bytearray()            # byte-level reassembly buffer
        self._assemblies: dict[int, _ChunkAssembly] = {}  # seq_id → assembly

        # --- reliability / testing -----------------------------------------
        self._trigger_crash = False  # Set to True via /debug/crash to test fail-fast

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------
    async def _scan(self) -> Optional[str]:
        """Scan for the drone by advertised name. Returns the BLE address or None."""
        logger.info("BLE scanning for drone...")
        # Reliability check: intentional crash for testing
        if self._trigger_crash:
            logger.warning("BLE loop intentional crash triggered")
            raise RuntimeError("Intentional crash for reliability testing")

        devices = await BleakScanner.discover(timeout=BLE_SCAN_TIMEOUT_S)
        for d in devices:
            if d.name and BLE_DEVICE_NAME.lower() in d.name.lower():
                logger.info("Found device: %s [%s]", d.name, d.address)
                return d.address
        logger.warning("Device '%s' not found in scan.", BLE_DEVICE_NAME)
        return None

    # ------------------------------------------------------------------
    # Connection + MTU negotiation
    # ------------------------------------------------------------------
    async def _connect(self, address: str) -> None:
        """Connect, negotiate MTU, log result, and subscribe to telemetry."""
        logger.info("Connecting to %s ...", address)
        self._client = BleakClient(
            address,
            disconnected_callback=self._on_disconnect,
        )
        await self._client.connect(timeout=BLE_CONNECTION_TIMEOUT_S)

        # --- MTU negotiation ------------------------------------------------
        # bleak negotiates MTU automatically during connection on most backends.
        # We query it post-connect to determine usable payload size.
        try:
            # bleak exposes MTU via the backend attribute (platform-specific).
            # Prefer the public API when available.
            mtu = getattr(self._client, "mtu_size", None)
            if mtu is None:
                # Fallback: attempt winrt / bluezdbus backend attribute
                backend = getattr(self._client, "_backend", None)
                if backend is not None:
                    mtu = getattr(backend, "mtu_size", None)
            self.negotiated_mtu = int(mtu) if mtu else BLE_TARGET_MTU_BYTES
        except Exception:
            self.negotiated_mtu = 23  # safe fallback

        self.usable_payload = self.negotiated_mtu - BLE_OVERHEAD_BYTES

        # Determine framing mode
        if self.usable_payload >= BLE_MIN_DIRECT_PAYLOAD_BYTES:
            self.chunking_enabled = False
            logger.info(
                "MTU negotiated: %d bytes | Payload per notification: %d bytes | "
                "Mode: DIRECT (no chunking required)",
                self.negotiated_mtu, self.usable_payload,
            )
        else:
            self.chunking_enabled = True
            logger.warning(
                "MTU negotiated: %d bytes | Payload per notification: %d bytes | "
                "Mode: CHUNKED (payload below %d byte threshold) — "
                "ensure Arduino firmware sends chunked frames",
                self.negotiated_mtu, self.usable_payload, BLE_MIN_DIRECT_PAYLOAD_BYTES,
            )

        # --- Subscribe to telemetry -----------------------------------------
        await self._client.start_notify(
            TELEMETRY_CHAR_UUID,
            self._on_telemetry_notification,
        )
        logger.info("Subscribed to telemetry notifications (%s)", TELEMETRY_CHAR_UUID)
        self.connected.set()

    # ------------------------------------------------------------------
    # BLE notification handler
    # ------------------------------------------------------------------
    def _on_telemetry_notification(self, _sender: int, data: bytearray) -> None:
        """
        Called by bleak on every BLE notification.

        Layer 1: Appends raw bytes to a buffer and extracts newline-terminated
        frames.  No assumption about packet size or JSON alignment.

        Layer 2: If chunking is enabled, each frame is parsed as a chunk header
        and assembled before being dispatched to JSON parsing.
        """
        # Expire stale incomplete assemblies (GC)
        self._gc_assemblies()

        # --- Layer 1: byte-buffer reassembly --------------------------------
        self._buffer += data
        logger.debug(
            "BLE notification: %d raw bytes received, buffer now %d bytes",
            len(data), len(self._buffer),
        )

        while b"\n" in self._buffer:
            # Split on first newline only; keep the rest for next iteration
            idx = self._buffer.index(b"\n")
            raw_frame = bytes(self._buffer[:idx]).strip()
            self._buffer = self._buffer[idx + 1:]

            if not raw_frame:
                continue

            # --- Layer 2: route to chunk assembler or direct parse ----------
            # A chunk frame starts with an integer seq_id (digit), 
            # while a JSON frame starts with '{'.
            if self.chunking_enabled and raw_frame and chr(raw_frame[0]).isdigit():
                self._handle_chunk(raw_frame)
            else:
                self._process_frame(raw_frame)

        # Overflow guard
        if len(self._buffer) > MAX_TELEMETRY_BUFFER_SIZE:
            logger.warning(
                "Telemetry buffer overflow (%d bytes, no '\\n' seen) — resetting.",
                len(self._buffer),
            )
            self._buffer = bytearray()

    # ------------------------------------------------------------------
    # Chunk handling
    # ------------------------------------------------------------------
    def _handle_chunk(self, raw_frame: bytes) -> None:
        """
        Parse a chunk frame: <seq_id>|<total_chunks>|<chunk_index>|<data>

        Accumulate chunks for the same seq_id; when all arrive, assemble and
        dispatch the full JSON payload.
        """
        parts = raw_frame.split(b"|", 3)
        if len(parts) != 4:
            logger.debug("Malformed chunk header (expected 4 parts): %s", raw_frame[:60])
            return

        try:
            seq_id = int(parts[0])
            total = int(parts[1])
            idx = int(parts[2])
            data = parts[3]
        except ValueError:
            logger.debug("Unparseable chunk header: %s", raw_frame[:60])
            return

        if total < 1 or total > 255 or idx < 0 or idx >= total:
            logger.debug("Chunk values out of range (seq=%d total=%d idx=%d)", seq_id, total, idx)
            return

        # Get or create assembly record
        if seq_id not in self._assemblies:
            self._assemblies[seq_id] = _ChunkAssembly(total=total)

        assembly = self._assemblies[seq_id]

        # Guard against reassembled size explosion
        projected = sum(len(c) for c in assembly.chunks.values()) + len(data)
        if projected > CHUNK_MAX_MESSAGE_SIZE:
            logger.warning(
                "Chunk assembly seq=%d exceeds max message size (%d bytes) — discarding",
                seq_id, CHUNK_MAX_MESSAGE_SIZE,
            )
            del self._assemblies[seq_id]
            return

        assembly.add(idx, data)
        logger.debug("Chunk seq=%d idx=%d/%d buffered", seq_id, idx + 1, total)

        if assembly.complete:
            full_frame = assembly.assemble()
            del self._assemblies[seq_id]

            # --- MTU / Memory Enforcement ---
            if len(full_frame) > MAX_TELEMETRY_JSON_BYTES:
                logger.warning(
                    "Reassembled chunked sequence %d rejected: exceeds "
                    "MAX_TELEMETRY_JSON_BYTES (%d > %d).",
                    seq_id, len(full_frame), MAX_TELEMETRY_JSON_BYTES
                )
                return

            logger.debug("Chunk seq=%d fully assembled (%d bytes)", seq_id, len(full_frame))
            self._process_frame(full_frame)

    def _gc_assemblies(self) -> None:
        """Discard incomplete chunk assemblies that have timed out."""
        expired = [k for k, v in self._assemblies.items() if v.expired]
        for k in expired:
            logger.warning("Chunk assembly seq=%d timed out — discarding", k)
            del self._assemblies[k]

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------
    def _process_frame(self, frame: bytes) -> None:
        """
        Parse a complete frame and update the atomic snapshot.
        If BLE_CRC_REQUIRED is set, verifies trailing CRC32 before parsing.
        """
        # --- CRC32 Hardening ---
        if BLE_CRC_REQUIRED:
            if b"|" not in frame:
                logger.debug("Hardening Error: Incoming frame lacks mandatory CRC separator '|'")
                return
            
            # Split into payload and checksum (e.g. b'{"aqi":10}|1a2b3c4d')
            parts = frame.rsplit(b"|", 1)
            if len(parts) != 2:
                return
            
            payload_bytes, crc_hex = parts
            try:
                # Calculate CRC32 of raw payload
                expected_crc = zlib.crc32(payload_bytes) & 0xFFFFFFFF
                # Checksum transmitted as hex string
                actual_crc = int(crc_hex, 16)
                if expected_crc != actual_crc:
                    logger.warning(
                        "Hardening Violation: CRC32 mismatch! Discarding malformed "
                        "frame before parsing. (exp=%08x, act=%08x)",
                        expected_crc, actual_crc
                    )
                    return
            except ValueError:
                logger.debug("Hardening Error: Invalid CRC hex format: %s", crc_hex)
                return
            
            # If valid, we parse the payload_bytes
            data_to_decode = payload_bytes
        else:
            # Legacy mode
            data_to_decode = frame

        # --- MTU / Memory Enforcement ---
        if len(data_to_decode) > MAX_TELEMETRY_JSON_BYTES:
            logger.warning(
                "Telemetry JSON rejected: exceeds MAX_TELEMETRY_JSON_BYTES "
                "(%d > %d). Length violation.",
                len(data_to_decode), MAX_TELEMETRY_JSON_BYTES
            )
            return

        # Decode UTF-8 safely
        try:
            raw_str = data_to_decode.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.error("UTF-8 decode failure on telemetry frame: %s", exc)
            return

        # Parse JSON
        try:
            raw = json.loads(raw_str)
        except json.JSONDecodeError as exc:
            logger.debug("Malformed JSON telemetry (discarded): %s — %.80s", exc, raw_str)
            return

        # Validate with Pydantic
        try:
            msg = TelemetryMessage.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telemetry validation failed (discarded): %s", exc)
            return

        # IMMUTABLE REPLACEMENT — do NOT mutate self.latest_telemetry in-place.
        # ``TelemetryMessage`` is frozen (Pydantic frozen=True), so field mutation
        # raises at runtime.  Always assign a new object here; never do:
        #   self.latest_telemetry.aqi = ...  # ✗ forbidden
        # See ARCHITECTURE.md "Telemetry Snapshot Safety".
        self.latest_telemetry = msg
        logger.debug("Valid telemetry frame stored (%d bytes)", len(frame))

    # ------------------------------------------------------------------
    # BLE command writer  — SINGLE WRITE SURFACE  (internal use only)
    # ------------------------------------------------------------------
    # ⚠ WARNING: THIS METHOD IS NOT SAFE FOR CONCURRENT USE.
    # It must ONLY be called by main.command_consumer_loop.
    # Do NOT call this from WebSocket handlers, deadman timers, or any
    # other coroutine.  Violating this rule will cause interleaved BLE
    # writes that can corrupt command ordering or be rejected by the OS
    # BLE stack under load.
    async def _write_command_bytes(self, cmd: ControlCommand) -> bool:
        """
        Serialise *cmd* to JSON bytes and write to the command characteristic.

        INTERNAL — called ONLY by ``main.command_consumer_loop``.
        Any other caller is a bug.

        Raises BleakError or asyncio.TimeoutError if the underlying BLE write fails.
        Returns ``True`` if successfully dispatched, ``False`` if the interface was already explicitly disconnected.
        Uses write-without-response for lowest latency unless configured otherwise.

        Defense-in-depth serialization:
          * ``_write_lock`` serializes concurrent callers (should never contend).
          * ``writes_in_flight`` counter detects accidental concurrent calls.
        """
        if self._client is None or not self._client.is_connected:
            return False

        # --- concurrency guard: detect concurrent writes -------------------
        self.writes_in_flight += 1
        if self.writes_in_flight > 1:
            logger.error(
                "BLE WRITE CONCURRENCY BUG DETECTED: writes_in_flight=%d. "
                "This means _write_command_bytes was called from more than one "
                "coroutine simultaneously, violating the single-writer rule. "
                 "Investigate immediately.",
                self.writes_in_flight,
            )

        if BLE_USE_BINARY_COMMANDS:
            payload = cmd.pack_binary()
        else:
            payload = cmd.model_dump_json().encode("utf-8")
            if BLE_CRC_REQUIRED:
                crc = zlib.crc32(payload) & 0xFFFFFFFF
                payload += f"|{crc:08x}".encode("ascii")

        try:
            # Defense-in-depth lock: serializes any accidental concurrent caller.
            # Should never contend in correct operation.
            async with self._write_lock:
                await self._client.write_gatt_char(
                    COMMAND_CHAR_UUID,
                    payload,
                    response=USE_WRITE_WITH_RESPONSE, 
                )
            return True
        finally:
            self.writes_in_flight -= 1

    # ------------------------------------------------------------------
    # Disconnect callback
    # ------------------------------------------------------------------
    def _on_disconnect(self, _client: BleakClient) -> None:
        logger.warning("BLE disconnected.")
        self.connected.clear()
        self._buffer = bytearray()         # flush reassembly buffer
        self._assemblies.clear()           # discard in-flight chunk assemblies

    # ------------------------------------------------------------------
    # Reconnection loop
    # ------------------------------------------------------------------
    async def run_forever(self) -> None:
        """
        Outer loop: scan → connect → wait for disconnect → sleep → retry.

        This coroutine never returns under normal operation.
        """
        while True:
            try:
                address = await self._scan()
                if address is None:
                    logger.info("Retrying scan in %ss ...", BLE_RECONNECT_DELAY_S)
                    await asyncio.sleep(BLE_RECONNECT_DELAY_S)
                    continue

                await self._connect(address)

                # Block here until disconnected
                while self._client and self._client.is_connected:
                    await asyncio.sleep(0.5)

            except BleakError as exc:
                logger.error("BLE error: %s", exc)
            except asyncio.CancelledError:
                logger.info("BLE client task cancelled — disconnecting")
                await self._safe_disconnect()
                raise
            except Exception:
                logger.exception("Unexpected error in BLE loop")

            # Clean up before retrying
            await self._safe_disconnect()
            logger.info("Reconnecting in %ss ...", BLE_RECONNECT_DELAY_S)
            await asyncio.sleep(BLE_RECONNECT_DELAY_S)

    async def _safe_disconnect(self) -> None:
        """Gracefully close the BLE connection if still open."""
        self.connected.clear()
        self._buffer = bytearray()
        self._assemblies.clear()
        if self._client is not None:
            try:
                if self._client.is_connected:
                    await self._client.disconnect()
            except Exception:
                pass
            self._client = None
