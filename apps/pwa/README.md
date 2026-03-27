# SASE AQI Drone PWA

The PWA provides joystick controls and an AQI telemetry dashboard for the bridge.

## Runtime Configuration

You can configure the bridge connection in two ways:

1. Build-time defaults via `.env.example`
2. Runtime inputs in the UI for bridge host and token

Supported Vite variables:

- `VITE_BRIDGE_WS_PROTOCOL=ws|wss`
- `VITE_BRIDGE_WS_PORT=8765`
- `VITE_BRIDGE_WS_TOKEN=`

## Development

From `apps/pwa/`:

```bash
npm install
npm run build
npm run lint
npm test
```

To run the app locally:

```bash
npm run dev
```

## Connecting To The Bridge

- On a trusted LAN with bridge auth disabled, leave the token blank.
- In production, set the bridge host and the same token configured on the bridge.
- If the bridge rejects the connection with policy code `1008`, the UI now surfaces that as an auth/configuration error.

## Mobile Testing

- Use `npm run dev -- --host` or `npm run preview -- --host`
- Open the app from a phone on the same network
- For a full installable PWA experience, serve the app over HTTPS
