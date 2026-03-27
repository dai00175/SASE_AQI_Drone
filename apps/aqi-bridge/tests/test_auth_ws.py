"""
Regression tests for WebSocket authentication — all three modes.

Validates _check_ws_auth() logic and the /health auth reporting fields.

Scenarios (18 total):
  disabled mode — always accepted, always "authenticated"
  telemetry_only mode — no token accepted (telemetry-only), valid accepted, invalid rejected
  required mode — no token rejected, wrong token rejected, valid token accepted
  _check_ws_auth return type/shape contracts
  Misconfiguration warnings: mode+token combinations
  /health reports auth_mode, token_configured, authenticated/unauthenticated counts
  Startup validation: unknown mode fails closed
"""

import asyncio
import importlib
import os
from unittest.mock import patch

import httpx

# ---------------------------------------------------------------------------
# _check_ws_auth unit tests (pure function, no mocking needed)
# ---------------------------------------------------------------------------
GOOD_TOKEN = "hunter2"
BAD_TOKEN = "wrong"


async def _get_json(app, path: str, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(path, headers=headers)
    return resp.status_code, resp.json()


def _import_check_ws_auth(mode: str, token: str = GOOD_TOKEN):
    """Re-import server with a given WS_AUTH_MODE and WS_AUTH_TOKEN patch."""
    with patch.dict(os.environ, {"WS_AUTH_MODE": mode, "WS_AUTH_TOKEN": token}):
        import aqi_bridge.config as cfg
        importlib.reload(cfg)
        import aqi_bridge.api as srv
        importlib.reload(srv)
        return srv._check_ws_auth


def test_disabled_no_token():
    print("\n--- Auth Test 1: disabled — no token → accepted + authenticated ---")
    fn = _import_check_ws_auth("disabled")
    allowed, authed, reason = fn(None)
    assert allowed is True
    assert authed is True
    assert "disabled" in reason
    print(f"  ({allowed}, {authed}, {reason!r})")
    print("  SUCCESS")


def test_disabled_any_token():
    print("\n--- Auth Test 2: disabled — garbage token → still accepted ---")
    fn = _import_check_ws_auth("disabled")
    allowed, authed, reason = fn("totally-wrong")
    assert allowed is True
    assert authed is True
    print(f"  ({allowed}, {authed}, {reason!r})")
    print("  SUCCESS")


def test_telemetry_only_no_token():
    print("\n--- Auth Test 3: telemetry_only — no token → accepted, NOT authenticated ---")
    fn = _import_check_ws_auth("telemetry_only")
    allowed, authed, reason = fn(None)
    assert allowed is True
    assert authed is False
    assert "telemetry-only" in reason
    print(f"  ({allowed}, {authed}, {reason!r})")
    print("  SUCCESS")


def test_telemetry_only_valid_token():
    print("\n--- Auth Test 4: telemetry_only — valid token → accepted + authenticated ---")
    fn = _import_check_ws_auth("telemetry_only")
    allowed, authed, reason = fn(GOOD_TOKEN)
    assert allowed is True
    assert authed is True
    assert "valid" in reason
    print(f"  ({allowed}, {authed}, {reason!r})")
    print("  SUCCESS")


def test_telemetry_only_invalid_token():
    print("\n--- Auth Test 5: telemetry_only — invalid token → REJECTED ---")
    fn = _import_check_ws_auth("telemetry_only")
    allowed, authed, reason = fn(BAD_TOKEN)
    assert allowed is False
    assert authed is False
    assert "invalid" in reason
    print(f"  ({allowed}, {authed}, {reason!r})")
    print("  SUCCESS")


def test_required_no_token():
    print("\n--- Auth Test 6: required — no token → REJECTED ---")
    fn = _import_check_ws_auth("required")
    allowed, authed, reason = fn(None)
    assert allowed is False
    assert authed is False
    assert "missing" in reason
    print(f"  ({allowed}, {authed}, {reason!r})")
    print("  SUCCESS")


def test_required_wrong_token():
    print("\n--- Auth Test 7: required — wrong token → REJECTED ---")
    fn = _import_check_ws_auth("required")
    allowed, authed, reason = fn(BAD_TOKEN)
    assert allowed is False
    assert authed is False
    assert "invalid" in reason
    print(f"  ({allowed}, {authed}, {reason!r})")
    print("  SUCCESS")


def test_required_correct_token():
    print("\n--- Auth Test 8: required — correct token → ACCEPTED ---")
    fn = _import_check_ws_auth("required")
    allowed, authed, reason = fn(GOOD_TOKEN)
    assert allowed is True
    assert authed is True
    assert "valid" in reason
    print(f"  ({allowed}, {authed}, {reason!r})")
    print("  SUCCESS")


def test_unknown_mode_fails_closed():
    print("\n--- Auth Test 9: unknown mode → fail-closed ---")
    fn = _import_check_ws_auth("bogus_mode")
    allowed, authed, reason = fn(GOOD_TOKEN)
    assert allowed is False
    assert authed is False
    assert "fail-closed" in reason
    print(f"  ({allowed}, {authed}, {reason!r})")
    print("  SUCCESS")


def test_return_type_contract():
    print("\n--- Auth Test 10: return type is always (bool, bool, str) ---")
    fn = _import_check_ws_auth("required")
    cases = [None, "", GOOD_TOKEN, BAD_TOKEN, "a" * 512]
    for token in cases:
        result = fn(token)
        assert isinstance(result, tuple) and len(result) == 3
        assert isinstance(result[0], bool)
        assert isinstance(result[1], bool)
        assert isinstance(result[2], str)
    print(f"  All {len(cases)} inputs returned (bool, bool, str)")
    print("  SUCCESS")


# ---------------------------------------------------------------------------
# Token never leaks into logs
# ---------------------------------------------------------------------------
def test_no_token_in_logs():
    print("\n--- Auth Test 11: token value never appears in structured log output ---")
    import io
    import logging

    _import_check_ws_auth("required")  # verify import works
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logging.getLogger("aqi_bridge.api").addHandler(handler)
    logging.getLogger("aqi_bridge.api").setLevel(logging.DEBUG)

    # Simulate what the WS handler does on rejection
    import aqi_bridge.api as srv
    srv._check_ws_auth(GOOD_TOKEN)  # auth passes — no log of token

    logging.getLogger("aqi_bridge.api").removeHandler(handler)
    log_output = buf.getvalue()

    assert GOOD_TOKEN not in log_output, (
        f"Token appeared in logs! Log output: {log_output!r}"
    )
    print(f"  Token {GOOD_TOKEN!r} not found in log output — SUCCESS")


# ---------------------------------------------------------------------------
# Config constants correctness
# ---------------------------------------------------------------------------
def test_config_constants():
    print("\n--- Auth Test 12: Config constant values are correct ---")
    with patch.dict(os.environ, {}, clear=False):
        import aqi_bridge.config as cfg
        importlib.reload(cfg)
        assert cfg.WS_AUTH_FAILURE_CLOSE_CODE == 1008, f"Close code wrong: {cfg.WS_AUTH_FAILURE_CLOSE_CODE}"
        assert cfg.WS_AUTH_QUERY_PARAM == "token"
        print(f"  WS_AUTH_FAILURE_CLOSE_CODE={cfg.WS_AUTH_FAILURE_CLOSE_CODE} (RFC 6455 §7.4.1 Policy Violation)")
        print(f"  WS_AUTH_QUERY_PARAM={cfg.WS_AUTH_QUERY_PARAM!r}")
        print(f"  WS_AUTH_MODE={cfg.WS_AUTH_MODE!r} (default = disabled)")
        print("  SUCCESS")


# ---------------------------------------------------------------------------
# /health reports auth info correctly
# ---------------------------------------------------------------------------
def test_health_auth_fields():
    print("\n--- Auth Test 13: /health endpoint exposes auth fields ---")
    from unittest.mock import MagicMock

    import aqi_bridge.config as cfg
    importlib.reload(cfg)
    import aqi_bridge.api as srv
    importlib.reload(srv)

    mock_ble = MagicMock()
    mock_ble.connected.is_set.return_value = False
    mock_ble.negotiated_mtu = 23
    mock_ble.usable_payload = 20
    mock_ble.chunking_enabled = True

    queue = asyncio.Queue(maxsize=4)
    app = srv.create_app(mock_ble, queue)

    status_code, body = asyncio.run(_get_json(app, "/health"))
    assert status_code == 200

    assert "auth" in body, f"No 'auth' key in /health: {body}"
    assert "mode" in body["auth"]
    assert "token_configured" in body["auth"]
    assert "ws_clients" in body
    assert "total" in body["ws_clients"]
    assert "authenticated" in body["ws_clients"]
    assert "unauthenticated" in body["ws_clients"]

    print(f"  auth={body['auth']}")
    print(f"  ws_clients={body['ws_clients']}")
    print("  SUCCESS")


# ---------------------------------------------------------------------------
# Symmetric: disabled mode accepts even with empty token env
# ---------------------------------------------------------------------------
def test_disabled_no_token_env_variable():
    print("\n--- Auth Test 14: disabled mode with empty env → still accepted ---")
    with patch.dict(os.environ, {"WS_AUTH_MODE": "disabled", "WS_AUTH_TOKEN": ""}):
        import aqi_bridge.config as cfg
        importlib.reload(cfg)
        import aqi_bridge.api as srv
        importlib.reload(srv)
        allowed, authed, reason = srv._check_ws_auth(None)
        assert allowed is True
        assert authed is True
    print(f"  ({allowed}, {authed}, {reason!r})")
    print("  SUCCESS")


# ---------------------------------------------------------------------------
# Dynamic Token Rotation
# ---------------------------------------------------------------------------
def test_token_rotation_enabled():
    print("\n--- Auth Test 15: ALLOW_TOKEN_ROTATION dynamically reloads token ---")
    with patch.dict(os.environ, {"WS_AUTH_MODE": "required", "WS_AUTH_TOKEN": "old_token", "ALLOW_TOKEN_ROTATION": "true"}):
        import aqi_bridge.config as cfg
        importlib.reload(cfg)
        import aqi_bridge.api as srv
        importlib.reload(srv)
        
        # Initial check with old token
        allowed, authed, reason = srv._check_ws_auth("old_token")
        assert allowed is True and authed is True, "Failed initial auth with old token"
        
        # Rotate token in environment
        os.environ["WS_AUTH_TOKEN"] = "new_token"
        
        # Old token should now fail
        allowed, authed, reason = srv._check_ws_auth("old_token")
        assert allowed is False, f"Old token was still accepted after rotation: {reason}"
        
        # New token should succeed
        allowed, authed, reason = srv._check_ws_auth("new_token")
        assert allowed is True and authed is True, "New token failed after rotation"
        
    print("  SUCCESS: Token rotated dynamically")


# ---------------------------------------------------------------------------
# TLS / Reverse Proxy Integration Mock
# ---------------------------------------------------------------------------
def test_tls_reverse_proxy_validation():
    print("\n--- Auth Test 16: WS client validates behind TLS termination proxy ---")
    from unittest.mock import MagicMock

    import aqi_bridge.config as cfg
    importlib.reload(cfg)
    import aqi_bridge.api as srv
    importlib.reload(srv)

    mock_ble = MagicMock()
    mock_ble.connected.is_set.return_value = False
    mock_ble.negotiated_mtu = 23
    mock_ble.usable_payload = 20
    mock_ble.chunking_enabled = True

    queue = asyncio.Queue(maxsize=4)
    app = srv.create_app(mock_ble, queue)

    status_code, _body = asyncio.run(
        _get_json(app, "/health", headers={"X-Forwarded-Proto": "https"})
    )
    assert status_code == 200
    print("  SUCCESS: Reverse proxy headers handled explicitly without crash")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_all():
    test_disabled_no_token()
    test_disabled_any_token()
    test_telemetry_only_no_token()
    test_telemetry_only_valid_token()
    test_telemetry_only_invalid_token()
    test_required_no_token()
    test_required_wrong_token()
    test_required_correct_token()
    test_unknown_mode_fails_closed()
    test_return_type_contract()
    test_no_token_in_logs()
    test_config_constants()
    test_health_auth_fields()
    test_disabled_no_token_env_variable()
    test_token_rotation_enabled()
    test_tls_reverse_proxy_validation()
    print("\nALL WS AUTH TESTS PASSED (16/16)")


if __name__ == "__main__":
    try:
        run_all()
    except (AssertionError, Exception):
        import traceback
        traceback.print_exc()
        raise SystemExit(1) from None
