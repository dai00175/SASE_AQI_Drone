#include "bluetooth.h"
#include <ArduinoJson.h>

static bool bluetoothRxReady = false;
static String bluetoothRxMessage;
static unsigned long lastBluetoothSendTime = 0;

bool bluetoothConnected = true;

static void bluetoothResetBuffer() {
    bluetoothRxReady = false;
    bluetoothRxMessage = String();
}

void initBluetooth(unsigned long baud) {
    Serial1.begin(baud);
    bluetoothResetBuffer();
}

void bluetoothPoll() {
    while (Serial1.available() > 0) {
        char c = (char)Serial1.read();
        lastBluetoothSendTime = millis();
        if (c == '\r') {
            continue;
        }
        if (c == '\n') {
            bluetoothRxMessage += c;
            bluetoothRxReady = true;
        }
        else {
            bluetoothRxMessage += c;
        }
    }
    checkBluetoothTimeout(500);
}


void checkBluetoothTimeout(unsigned long timeoutMs) {
    if (millis() - lastBluetoothSendTime > timeoutMs) {
        bluetoothConnected = false;
    }
}

bool bluetoothReadMessage(String &message) {
    if (!bluetoothRxReady) {
        return false;
    }
    message = bluetoothRxMessage;
    bluetoothResetBuffer();
    return true;
}


bool bluetoothPackJson(const JsonDocument &doc, String &out) {
    out = String();
    serializeJson(doc, out);
    out += '\n';
    return true;
}

bool bluetoothSendJson(const JsonDocument &doc) {
    String payload;
    if (!bluetoothPackJson(doc, payload)) {
        return false;
    }
    bluetoothConnected = true;
    lastBluetoothSendTime = millis();
    Serial1.print(payload);
    return true;
}

bool bluetoothSendJsonString(const String &json) {
    if (json.length() == 0) {
        return false;
    }
    bluetoothConnected = true;
    lastBluetoothSendTime = millis();
    Serial1.print(json);
    if (!json.endsWith("\n")) {
        Serial1.print('\n');
    }
    return true;
}
