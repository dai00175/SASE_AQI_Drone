#ifndef BLUETOOTH_H
#define BLUETOOTH_H

#include <Arduino.h>
#include <ArduinoJson.h>

extern bool bluetoothRxReady;
extern String bluetoothRxMessage;
extern bool bluetoothConnected;

void initBluetooth(unsigned long baud = 9600);

void bluetoothResetBuffer();

void bluetoothPoll();

void checkBluetoothTimeout(unsigned long timeoutMs = 5000);

bool bluetoothMessageAvailable();

bool bluetoothReadMessage(String &message);

bool bluetoothPackJson(const JsonDocument &doc, String &out);

bool bluetoothSendJson(const JsonDocument &doc);

bool bluetoothSendJsonString(const String &json);

#endif // BLUETOOTH_H
