"""
Centralized configuration for the BLE-to-WebSocket bridge.

Every production-tunable constant lives here and may be overridden via the
environment. This keeps deployment behavior explicit and reproducible.
"""

from __future__ import annotations

import os as _os


def _env_bool(name: str, default: bool) -> bool:
    raw = _os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = _os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = _os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _os.environ.get(name)
    if raw is None:
        return default
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return values or default


# ---------------------------------------------------------------------------
# BLE — Arduino peripheral identifiers
# ---------------------------------------------------------------------------
BLE_DEVICE_NAME: str = _os.environ.get("BLE_DEVICE_NAME", "AQI_Drone")
BLE_SERVICE_UUID: str = _os.environ.get(
    "BLE_SERVICE_UUID",
    "19b10000-e8f2-537e-4f6c-d104768a1214",
)
TELEMETRY_CHAR_UUID: str = _os.environ.get(
    "TELEMETRY_CHAR_UUID",
    "19b10011-e8f2-537e-4f6c-d104768a1214",
)
COMMAND_CHAR_UUID: str = _os.environ.get(
    "COMMAND_CHAR_UUID",
    "19b10012-e8f2-537e-4f6c-d104768a1214",
)

BLE_RECONNECT_DELAY_S: float = _env_float("BLE_RECONNECT_DELAY_S", 2.0)
BLE_SCAN_TIMEOUT_S: float = _env_float("BLE_SCAN_TIMEOUT_S", 10.0)
BLE_CONNECTION_TIMEOUT_S: float = _env_float("BLE_CONNECTION_TIMEOUT_S", 10.0)

# ---------------------------------------------------------------------------
# BLE MTU
# ---------------------------------------------------------------------------
BLE_TARGET_MTU_BYTES: int = _env_int("BLE_TARGET_MTU_BYTES", 247)
BLE_OVERHEAD_BYTES: int = 3
BLE_DEFAULT_MTU_BYTES: int = 23
BLE_DEFAULT_PAYLOAD_BYTES: int = BLE_DEFAULT_MTU_BYTES - BLE_OVERHEAD_BYTES
BLE_MIN_DIRECT_PAYLOAD_BYTES: int = _env_int("BLE_MIN_DIRECT_PAYLOAD_BYTES", 185)

# ---------------------------------------------------------------------------
# Chunked framing protocol
# ---------------------------------------------------------------------------
CHUNK_MAX_MESSAGE_SIZE: int = _env_int("CHUNK_MAX_MESSAGE_SIZE", 2048)
CHUNK_ASSEMBLY_TIMEOUT_S: float = _env_float("CHUNK_ASSEMBLY_TIMEOUT_S", 2.0)
CHUNK_MTU_NEGOTIATION_TIMEOUT_S: float = _env_float(
    "CHUNK_MTU_NEGOTIATION_TIMEOUT_S",
    2.0,
)

# ---------------------------------------------------------------------------
# Command pipeline
# ---------------------------------------------------------------------------
COMMAND_QUEUE_SIZE: int = _env_int("COMMAND_QUEUE_SIZE", 4)
COMMAND_QUEUE_POLICY: str = "drop_oldest"
COMMAND_DROP_LOG_INTERVAL_S: float = _env_float("COMMAND_DROP_LOG_INTERVAL_S", 1.0)
MAX_COMMAND_AGE_MS: float = _env_float("MAX_COMMAND_AGE_MS", 300.0)

# ---------------------------------------------------------------------------
# Deadman safety timer
# ---------------------------------------------------------------------------
DEADMAN_TIMEOUT_MS: float = _env_float("DEADMAN_TIMEOUT_MS", 500.0)
FAILSAFE_EMIT_BUDGET_MS: float = _env_float("FAILSAFE_EMIT_BUDGET_MS", 50.0)
DEADMAN_TIMEOUT_S: float = DEADMAN_TIMEOUT_MS / 1000.0

# ---------------------------------------------------------------------------
# Telemetry broadcast
# ---------------------------------------------------------------------------
TELEMETRY_BROADCAST_HZ: float = _env_float("TELEMETRY_BROADCAST_HZ", 30.0)
MAX_TELEMETRY_MESSAGE_SIZE: int = _env_int("MAX_TELEMETRY_MESSAGE_SIZE", 1024)
MAX_TELEMETRY_BUFFER_SIZE: int = _env_int("MAX_TELEMETRY_BUFFER_SIZE", 4096)
MAX_TELEMETRY_JSON_BYTES: int = _env_int("MAX_TELEMETRY_JSON_BYTES", 1024)

# ---------------------------------------------------------------------------
# Protocol hardening
# ---------------------------------------------------------------------------
BLE_CRC_REQUIRED: bool = _env_bool("BLE_CRC_REQUIRED", True)
BLE_USE_BINARY_COMMANDS: bool = _env_bool("BLE_USE_BINARY_COMMANDS", True)
USE_WRITE_WITH_RESPONSE: bool = _env_bool("USE_WRITE_WITH_RESPONSE", False)

# ---------------------------------------------------------------------------
# WebSocket server
# ---------------------------------------------------------------------------
WS_HOST: str = _os.environ.get("WS_HOST", "0.0.0.0")
WS_PORT: int = _env_int("WS_PORT", 8765)
WS_SEND_TIMEOUT_S: float = _env_float("WS_SEND_TIMEOUT_S", 0.1)
WS_BROADCAST_LOG_INTERVAL_S: float = _env_float("WS_BROADCAST_LOG_INTERVAL_S", 10.0)
WS_ALLOWED_ORIGINS: tuple[str, ...] = _env_csv(
    "WS_ALLOWED_ORIGINS",
    (
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ),
)

# ---------------------------------------------------------------------------
# System-level bounds
# ---------------------------------------------------------------------------
MAX_WS_CLIENTS: int = _env_int("MAX_WS_CLIENTS", 100)
LOOP_STARVATION_THRESHOLD_S: float = _env_float("LOOP_STARVATION_THRESHOLD_S", 0.1)
LOG_RATE_LIMIT_S: float = _env_float("LOG_RATE_LIMIT_S", 1.0)

# ---------------------------------------------------------------------------
# WebSocket authentication policy
# ---------------------------------------------------------------------------
WS_AUTH_MODE: str = _os.environ.get("WS_AUTH_MODE", "disabled")
WS_AUTH_TOKEN: str = _os.environ.get("WS_AUTH_TOKEN", "")
WS_AUTH_QUERY_PARAM: str = _os.environ.get("WS_AUTH_QUERY_PARAM", "token")
ALLOW_TOKEN_ROTATION: bool = _env_bool("ALLOW_TOKEN_ROTATION", False)
WS_AUTH_FAILURE_CLOSE_CODE: int = _env_int("WS_AUTH_FAILURE_CLOSE_CODE", 1008)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FORMAT: str = _os.environ.get("LOG_FORMAT", "text").lower()
LOG_LEVEL: str = _os.environ.get("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# Debugging / reliability testing
# ---------------------------------------------------------------------------
ALLOW_DEBUG_CRASH: bool = _env_bool("ALLOW_DEBUG_CRASH", False)

del _env_bool
del _env_csv
del _env_float
del _env_int
