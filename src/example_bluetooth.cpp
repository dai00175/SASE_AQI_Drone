#include <ArduinoJson.h>

void setup() {
  Serial.begin(115200);
  Serial1.begin(9600); // Bluetooth Pins 0 & 1
}

void loop() {
  if (Serial1.available()) {
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, Serial1);

    if (!error) {
        Serial.print("New Mission Received: ");
        Serial.println(doc["mission_id"].as<int>());

        // Loop through the sequence of commands
        JsonArray commands = doc["commands"];
        for (JsonObject cmd : commands) {
            const char* action = cmd["action"];
            float duration = cmd["value"];

            // Log to Serial Monitor
            Serial.print("Executing: ");
            Serial.print(action);
            Serial.print(" for ");
            Serial.print(duration);
            Serial.println(" seconds.");

            // Here you would call your actual drone movement functions:
            // moveDrone(action, duration); 
            
            delay(duration * 1000); // Simple block for testing
        }
        Serial.println("Mission Complete.");
    }
  }
}