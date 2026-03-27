# SASE AQI Drone

This repository contains a three-part AQI drone stack:

1. `firmware/aqi_drone_ble/`: BLE firmware for the drone-side sensor and command link.
2. `apps/aqi-bridge/`: Python bridge that connects to the BLE peripheral and exposes telemetry plus control over WebSocket.
3. `apps/pwa/`: React PWA for pilot controls and AQI telemetry display.

## What Is Production-Ready Now

- The bridge has an explicit environment-driven configuration surface.
- WebSocket auth, queue bounds, CRC enforcement, and health reporting are implemented in code.
- Docker Compose now includes a real Nginx config instead of placeholder references.
- The PWA can be pointed at a real bridge host and token without source edits.
- The repo now includes a dedicated BLE firmware sketch that publishes AQI telemetry in the format the bridge expects.

## What Still Requires Physical Validation

- BLE MTU negotiation and link stability on the actual board and radio environment.
- Sensor calibration and warm-up behavior for the ENS160/AHT20-AHT21 package.
- Your real flight-controller integration inside `applyControlCommand()` in the firmware.
- End-to-end fail-safe verification on the ground before any flight.

## Recommended Bring-Up Order

1. Flash `firmware/aqi_drone_ble/aqi_drone_ble.ino` onto a BLE-capable board mounted on the drone.
2. Start the bridge from `apps/aqi-bridge/` with a real `WS_AUTH_TOKEN`.
3. Confirm `/health` shows `ble_connected=true` and inspect `negotiated_mtu`.
4. Start the PWA from `apps/pwa/`, set the bridge host and token, and verify telemetry updates.
5. Ground-test arming, disarming, disconnect fail-safe, and stale-command behavior before any rotor spin-up.

## Key Documentation

- Bridge service: `apps/aqi-bridge/docs/README.md`
- Bridge architecture: `apps/aqi-bridge/docs/architecture.md`
- Field checklist: `apps/aqi-bridge/docs/field_readiness.md`
- PWA usage: `apps/pwa/README.md`
- Drone firmware contract: `firmware/aqi_drone_ble/README.md`

## GitHub Pages Deployment

The PWA deployment workflow in `.github/workflows/deploy-pwa.yml` publishes with GitHub Pages.

Before the workflow can succeed, the repository must be configured one of these two ways:

1. In GitHub repository settings, set `Settings > Pages > Build and deployment > Source` to `GitHub Actions`.
2. Or add a repository secret named `PAGES_ENABLEMENT_TOKEN` with permission to enable Pages, then let the workflow auto-enable it.

The workflow is already updated for Node 24-capable action runtimes.
