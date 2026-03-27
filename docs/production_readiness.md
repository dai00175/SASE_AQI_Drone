# Production Readiness Notes

This repository is closer to a production candidate after the current changes, but it is not "flight certified" by code alone.

## Ready In Repo

- Environment-driven bridge configuration
- Queue-bounded command pipeline
- BLE CRC validation and binary command packing
- TLS-ready reverse proxy configuration
- PWA bridge host and token configuration without source edits
- Dedicated BLE firmware for AQI telemetry plus command ingestion

## Still Required Outside Repo

- Install Python and Node dependencies in a clean environment
- Flash and ground-test the BLE firmware on the real board
- Integrate `applyControlCommand()` with the actual ESC or flight controller
- Validate BLE MTU negotiation and RSSI margins on the real airframe
- Provide TLS certificates and a strong `WS_AUTH_TOKEN`
- Run the bridge and PWA verification steps before first field use

## Recommended Release Gate

Do not consider the system field-ready until all of the following pass on target hardware:

1. Bridge test suite, lint, and PWA build/test all pass.
2. `/health` shows stable BLE connectivity and the expected auth mode.
3. The drone keeps publishing valid `aqi`, `tvoc`, `eco2`, `temperature_c`, and `humidity_pct`.
4. Disconnecting the pilot device causes a deterministic failsafe state on the drone.
5. Re-arming requires an explicit neutral re-arm after a failsafe.
