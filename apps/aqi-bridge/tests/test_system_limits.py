"""
Tests to verify System-Level Mitigation strategies.

Targets:
1. MAX_WS_CLIENTS enforcement (Registry bounding).
2. Event Loop Watchdog starvation detection.
"""

import asyncio
import time
from unittest.mock import MagicMock

import httpx
from aqi_bridge.api import create_app
from aqi_bridge.app import event_loop_watchdog
from aqi_bridge.config import LOOP_STARVATION_THRESHOLD_S, MAX_WS_CLIENTS
from starlette.websockets import WebSocketState


class FakeWebSocket:
    def __init__(self) -> None:
        self.client = ("127.0.0.1", 9999)
        self.client_state = WebSocketState.CONNECTED
        self.accepted = False
        self.closed_code: int | None = None
        self.closed_reason: str | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int, reason: str | None = None) -> None:
        self.closed_code = code
        self.closed_reason = reason
        self.client_state = WebSocketState.DISCONNECTED

    async def receive_text(self) -> str:
        raise AssertionError("receive_text should not be reached when capacity is full")


async def _get_json(app, path: str) -> tuple[int, dict]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(path)
    return resp.status_code, resp.json()


def test_max_ws_clients_enforced():
    """Verify connections are rejected with 1013 when the registry hits MAX_WS_CLIENTS."""
    print(f"\n--- System Test 1: Bounding WS registry to {MAX_WS_CLIENTS} ---")
    mock_ble = MagicMock()
    mock_ble.connected.is_set.return_value = False
    
    queue = asyncio.Queue(maxsize=4)
    app = create_app(mock_ble, queue)

    # Manually stuff the registry to maximum capacity with unique objects
    app.state.clients.update([MagicMock() for _ in range(MAX_WS_CLIENTS)])

    websocket_route = next(route for route in app.router.routes if getattr(route, "path", None) == "/ws")
    fake_ws = FakeWebSocket()
    asyncio.run(websocket_route.endpoint(fake_ws, token=None))

    assert fake_ws.accepted is True
    assert fake_ws.closed_code == 1013

    status_code, body = asyncio.run(_get_json(app, "/health"))
    assert status_code == 200
    assert body["ws_clients"]["total"] == MAX_WS_CLIENTS
    assert body["ws_clients"]["rejected_capacity"] == 1
    print("  Client rejected. Capacity limit enforced.")
    print("  SUCCESS")


async def _run_watchdog_test():
    loop_lag = [0.0]
    starvation_count = [0]
    
    # Start the watchdog as a background task
    task = asyncio.create_task(event_loop_watchdog(loop_lag, starvation_count))
    
    # Let it run to the first await sleep
    await asyncio.sleep(0.1)
    
    # SIMULATE STARVATION: synchronous blocking code
    # This prevents the event loop from waking the watchdog from its asyncio.sleep(1.0) on time
    
    # We delay the blocking to ensure the watchdog has entered its 1.0s sleep.
    await asyncio.sleep(0.1)
    
    # Block forcefully for longer than the threshold + the watchdog's sleep
    block_duration = 1.0 + LOOP_STARVATION_THRESHOLD_S + 0.1
    print(f"  Blocking CPU synchronously for {block_duration}s...")
    time.sleep(block_duration)
    
    # Yield control back to watchdog so it completes/measures
    await asyncio.sleep(0.1)
    
    # Cancel the watchdog before exit
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
        
    assert starvation_count[0] > 0, "Watchdog failed to detect the synchronous starvation event"
    print(f"  Watchdog correctly logged {starvation_count[0]} starvation events.")
    print(f"  Final recorded loop lag: {loop_lag[0]*1000:.1f}ms")


def test_loop_starvation_detection():
    """Verify the watchdog detects sync blocking code on the event loop."""
    print("\n--- System Test 2: Event Loop Watchdog detects starvation ---")
    asyncio.run(_run_watchdog_test())
    print("  SUCCESS")

if __name__ == "__main__":
    test_max_ws_clients_enforced()
    test_loop_starvation_detection()
    print("\nALL SYSTEM-LEVEL BOUNDING TESTS PASSED")
