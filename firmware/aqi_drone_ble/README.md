# AQI Drone BLE Firmware

This sketch is the drone-side BLE contract expected by the Python bridge.

It does three things:

1. Reads ENS160 AQI data plus AHT20/AHT21 temperature and humidity.
2. Publishes telemetry as `JSON|crc32\n` on `TELEMETRY_CHAR_UUID`.
3. Accepts the bridge's 21-byte binary command packet on `COMMAND_CHAR_UUID` and verifies its CRC32 before applying it.

## Required Arduino libraries

- `ArduinoBLE`
- `Adafruit AHTX0`

The repo vendors `ScioSense_ENS160.{h,cpp}` in this folder so the sketch can build without a separate ENS160 library install.

## Wiring assumptions

- ENS160 on I2C address `0x53`
- AHT20/AHT21 on the same I2C bus
- A BLE-capable board such as Nano 33 BLE or ESP32

## Flight-controller integration

`applyControlCommand()` is intentionally isolated in the sketch. Replace that function with the actual PWM, UART, or flight-controller protocol used by your drone. The rest of the BLE and sensor path can remain unchanged.

## Bridge alignment

These values must match `apps/aqi-bridge/aqi_bridge/config.py`:

- Device name: `AQI_Drone`
- Service UUID: `19b10000-e8f2-537e-4f6c-d104768a1214`
- Telemetry characteristic: `19b10011-e8f2-537e-4f6c-d104768a1214`
- Command characteristic: `19b10012-e8f2-537e-4f6c-d104768a1214`
