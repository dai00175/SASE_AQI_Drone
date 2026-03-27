#include <ArduinoBLE.h>
#include <Adafruit_AHTX0.h>
#include <Wire.h>

#include "ScioSense_ENS160.h"

#define BLE_SERVICE_UUID "19b10000-e8f2-537e-4f6c-d104768a1214"
#define TELEMETRY_CHAR_UUID "19b10011-e8f2-537e-4f6c-d104768a1214"
#define COMMAND_CHAR_UUID "19b10012-e8f2-537e-4f6c-d104768a1214"

static const unsigned long TELEMETRY_PERIOD_MS = 200;
static const unsigned long COMMAND_FRESH_MS = 750;
static const size_t TELEMETRY_BUFFER_BYTES = 192;

struct __attribute__((packed)) ControlCommand {
  float vx;
  float vy;
  float vz;
  float yaw;
  uint8_t arm;
  uint32_t crc32;
};

BLEService droneService(BLE_SERVICE_UUID);
BLECharacteristic telemetryChar(TELEMETRY_CHAR_UUID, BLERead | BLENotify, 244);
BLECharacteristic commandChar(COMMAND_CHAR_UUID, BLEWrite | BLEWriteWithoutResponse, sizeof(ControlCommand));

Adafruit_AHTX0 aht;
ScioSense_ENS160 ens160(ENS160_I2CADDR_1);

ControlCommand lastCommand = {0.0f, 0.0f, 0.0f, 0.0f, 0, 0};
unsigned long lastTelemetryMs = 0;
unsigned long lastCommandMs = 0;
bool ahtReady = false;
bool ensReady = false;
bool failsafeApplied = true;

uint32_t crc32_update(uint32_t crc, uint8_t data) {
  crc ^= data;
  for (uint8_t bit = 0; bit < 8; ++bit) {
    if (crc & 1U) {
      crc = (crc >> 1) ^ 0xEDB88320UL;
    } else {
      crc >>= 1;
    }
  }
  return crc;
}

uint32_t crc32_bytes(const uint8_t* data, size_t len) {
  uint32_t crc = 0xFFFFFFFFUL;
  for (size_t i = 0; i < len; ++i) {
    crc = crc32_update(crc, data[i]);
  }
  return ~crc;
}

String formatHex32(uint32_t value) {
  char out[9];
  snprintf(out, sizeof(out), "%08lx", static_cast<unsigned long>(value));
  return String(out);
}

void zeroCommand(ControlCommand& cmd) {
  cmd.vx = 0.0f;
  cmd.vy = 0.0f;
  cmd.vz = 0.0f;
  cmd.yaw = 0.0f;
  cmd.arm = 0;
  cmd.crc32 = 0;
}

bool commandIsFresh() {
  return lastCommandMs != 0 && (millis() - lastCommandMs) <= COMMAND_FRESH_MS;
}

void applyControlCommand(const ControlCommand& cmd) {
  // Replace this serial-only sink with your actual ESC or flight-controller bridge.
  Serial.print("cmd vx=");
  Serial.print(cmd.vx, 3);
  Serial.print(" vy=");
  Serial.print(cmd.vy, 3);
  Serial.print(" vz=");
  Serial.print(cmd.vz, 3);
  Serial.print(" yaw=");
  Serial.print(cmd.yaw, 3);
  Serial.print(" arm=");
  Serial.println(cmd.arm ? "true" : "false");
}

void commandWrittenCallback(BLEDevice, BLECharacteristic characteristic) {
  if (characteristic.valueLength() != sizeof(ControlCommand)) {
    Serial.print("Rejecting malformed command length=");
    Serial.println(characteristic.valueLength());
    return;
  }

  ControlCommand cmd;
  memcpy(&cmd, characteristic.value(), sizeof(ControlCommand));

  const uint32_t expected = crc32_bytes(reinterpret_cast<const uint8_t*>(&cmd), sizeof(ControlCommand) - sizeof(uint32_t));
  if (expected != cmd.crc32) {
    Serial.println("Rejecting command due to CRC32 mismatch");
    return;
  }

  lastCommand = cmd;
  lastCommandMs = millis();
  failsafeApplied = false;
  applyControlCommand(cmd);
}

void setupSensors() {
  Wire.begin();

  ahtReady = aht.begin();
  if (!ahtReady) {
    Serial.println("AHT20 not detected");
  }

  ens160.begin();
  ensReady = ens160.available();
  if (!ensReady) {
    Serial.println("ENS160 not detected");
    return;
  }

  ens160.setMode(ENS160_OPMODE_STD);
}

void setupBle() {
  if (!BLE.begin()) {
    Serial.println("BLE init failed");
    while (true) {
      delay(1000);
    }
  }

  BLE.setLocalName("AQI_Drone");
  BLE.setAdvertisedService(droneService);
  droneService.addCharacteristic(telemetryChar);
  droneService.addCharacteristic(commandChar);
  BLE.addService(droneService);
  commandChar.setEventHandler(BLEWritten, commandWrittenCallback);
  BLE.advertise();
}

String currentStatus() {
  if (!commandIsFresh()) {
    return "failsafe";
  }
  return lastCommand.arm ? "armed" : "disarmed";
}

void sendTelemetry() {
  sensors_event_t humidityEvent;
  sensors_event_t tempEvent;
  float temperatureC = 0.0f;
  float humidityPct = 0.0f;

  if (ahtReady) {
    aht.getEvent(&humidityEvent, &tempEvent);
    temperatureC = tempEvent.temperature;
    humidityPct = humidityEvent.relative_humidity;
  }

  uint16_t tvoc = 0;
  uint16_t eco2 = 0;
  uint8_t aqi = 0;
  if (ensReady) {
    ens160.set_envdata(static_cast<int>(temperatureC), static_cast<int>(humidityPct));
    ens160.measure(true);
    ens160.measureRaw(true);
    aqi = ens160.getAQI();
    tvoc = ens160.getTVOC();
    eco2 = ens160.geteCO2();
  }

  char payload[TELEMETRY_BUFFER_BYTES];
  snprintf(
    payload,
    sizeof(payload),
    "{\"status\":\"%s\",\"aqi\":%u,\"tvoc\":%u,\"eco2\":%u,\"temperature_c\":%.1f,\"humidity_pct\":%.1f,\"timestamp_ms\":%lu}",
    currentStatus().c_str(),
    static_cast<unsigned int>(aqi),
    static_cast<unsigned int>(tvoc),
    static_cast<unsigned int>(eco2),
    static_cast<double>(temperatureC),
    static_cast<double>(humidityPct),
    static_cast<unsigned long>(millis())
  );

  const uint32_t crc = crc32_bytes(reinterpret_cast<const uint8_t*>(payload), strlen(payload));
  String frame = String(payload) + "|" + formatHex32(crc) + "\n";
  telemetryChar.writeValue(reinterpret_cast<const uint8_t*>(frame.c_str()), frame.length());
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) {
    delay(10);
  }

  zeroCommand(lastCommand);
  setupSensors();
  setupBle();
  Serial.println("AQI drone BLE firmware ready");
}

void loop() {
  BLE.poll();

  BLEDevice central = BLE.central();
  if (central) {
    Serial.print("Connected to central: ");
    Serial.println(central.address());

    while (central.connected()) {
      BLE.poll();

      if (!commandIsFresh() && !failsafeApplied) {
        ControlCommand safe;
        zeroCommand(safe);
        applyControlCommand(safe);
        failsafeApplied = true;
      }

      const unsigned long now = millis();
      if (now - lastTelemetryMs >= TELEMETRY_PERIOD_MS) {
        lastTelemetryMs = now;
        sendTelemetry();
      }
    }

    ControlCommand safe;
    zeroCommand(safe);
    applyControlCommand(safe);
    failsafeApplied = true;

    Serial.print("Disconnected from central: ");
    Serial.println(central.address());
  }
}
