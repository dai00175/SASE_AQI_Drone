#include <Arduino.h>
#include <ArduinoJson.h>
#include "states.h"
#include "motors.h"
#include "pid.h"
#include "main.h"
#include "ultrasonic.h"
#include "bluetooth.h"

// Current state
DroneState State = IDLE;

// State-specific variables
unsigned long takeoffStartTime = 0;
const unsigned long takeoffDuration = 4000; // 4 seconds to reach hover
unsigned long landingStartTime = 0;
const unsigned long landingDuration = 4000; // 4 seconds to land
int previousHeightCM = 0;
int takeoffLastHeight = 0;
unsigned long lastDistanceSampleTime = 0;

void initStates() {
    State = IDLE;
    // Initialize to idle state
    thro_des = PWM_OFF;
    roll_des = 0;
    pitch_des = 0;
    yaw_des = 0;
}

void updateStates() {
    // Sample ultrasonic distance - more frequently during takeoff/landing
    unsigned long sampleInterval = (State == TAKEOFF || State == LANDING) ? 100 : 1000;
    if (millis() - lastDistanceSampleTime >= sampleInterval) {
        previousHeightCM = distance_cm; 
        startUltrasonicMeasurement(); // Trigger a new measurement
        lastDistanceSampleTime = millis();
    }
    
    if (bluetoothRxReady) {
        JsonDocument doc;
        DeserializationError error = deserializeJson(doc, bluetoothRxMessage);
        if (!error) {
            // Process the command in doc and update state variables as needed
            // For example, you might check for a "command" field and switch states
            const int missionId = doc["mission_id"].as<int>();
            JsonArray commands = doc["commands"];
            for (JsonObject cmd : commands) {
                const char* action = cmd["action"];
                
                if (State == IDLE && strcmp(action, "takeoff") != 0) {
                    continue;
                }
                else setState(TAKEOFF);
                
                if (!bluetoothConnected) setState(LANDING);
                
                if (strcmp(action, "cancel") == 0) {
                    setState(USERCNTRL);
                }
                else if (strcmp(action, "program_control") == 0) {
                    setState(PRGMCNTRL);
                }
                else if (strcmp(action, "land") == 0) {
                    setState(LANDING);
                }

                if (strcmp(action, "land") == 0) {
                    setState(LANDING);
                }

                bluetoothRxReady = false; // Mark message as processed
            }
        }
        else {
            // TODO: Send error response back over Bluetooth if needed
        }
        bluetoothResetBuffer();
    }

    switch (State) {
        case IDLE:
            // Motors off, wait for takeoff command
            thro_des = PWM_OFF;
            roll_des = 0;
            pitch_des = 0;
            yaw_des = 0;
            // TODO: Check for takeoff command from controller
            break;

        case TAKEOFF:
            break;
        case USERCNTRL:
            break;
        case PRGMCNTRL:
            break;
        case LANDING:
            break;
    }
}

void setState(DroneState newState) {
    // Reset state-specific variables when changing states
    if (newState != State) {
        takeoffStartTime = 0;
        landingStartTime = 0;
        takeoffLastHeight = 0;
    }
    State = newState;
}