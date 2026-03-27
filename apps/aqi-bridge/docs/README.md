# AQI Bridge

`aqi_bridge` is the process that sits between the drone's BLE peripheral and the pilot-facing WebSocket clients.

## Responsibilities

- Discover and reconnect to the BLE device named by `BLE_DEVICE_NAME`.
- Parse telemetry notifications and expose the latest snapshot over `/health` and `/ws`.
- Accept control commands from authenticated WebSocket clients.
- Serialize all BLE writes through a single queue-backed consumer.

## Runtime Requirements

- Python 3.12 or newer
- A working BLE adapter on the host
- A BLE peripheral exposing the UUIDs configured in `aqi_bridge/config.py`

## Local Development

From `apps/aqi-bridge/`:

```bash
python3 -m aqi_bridge
```

Default mode is local and permissive:

- `WS_AUTH_MODE=disabled`
- `WS_AUTH_TOKEN=""`

Health check:

```bash
curl -s http://127.0.0.1:8765/health
```

## Production Deployment

Use environment variables instead of source edits. Start with `.env.example` and set:

- `WS_AUTH_MODE=required`
- `WS_AUTH_TOKEN=<random secret>`
- `WS_ALLOWED_ORIGINS=https://your-pwa-host`
- `BLE_CRC_REQUIRED=true`
- `BLE_USE_BINARY_COMMANDS=true`

For containerized deployment, `docker-compose.yml` expects:

- BLE access via host networking and `/var/run/dbus`
- TLS termination via the included Nginx config
- `nginx/certs/fullchain.pem`
- `nginx/certs/privkey.pem`

## Related Docs

- `architecture.md`
- `protocol.md`
- `field_readiness.md`
- `PERFORMANCE_QUALIFICATION.md`
- `end_to_end_test_guide.md`
