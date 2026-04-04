#include <Arduino.h>
#include "states.h"
#include "motors.h"
#include "pid.h"
#include "main.h"
#include "ultrasonic.h"

// Current state
DroneState currentState = IDLE;

// State-specific variables
unsigned long takeoffStartTime = 0;
const unsigned long takeoffDuration = 4000; // 4 seconds to reach hover
unsigned long landingStartTime = 0;
const unsigned long landingDuration = 4000; // 4 seconds to land
int previousHeightCM = 0;
int takeoffLastHeight = 0;
unsigned long lastDistanceSampleTime = 0;

void initStates() {
    currentState = IDLE;
    // Initialize to idle state
    thro_des = PWM_OFF;
    roll_des = 0;
    pitch_des = 0;
    yaw_des = 0;
}

void updateStates() {
    // Sample ultrasonic distance - more frequently during takeoff/landing
    unsigned long sampleInterval = (currentState == TAKEOFF || currentState == LANDING) ? 100 : 1000;
    if (millis() - lastDistanceSampleTime >= sampleInterval) {
        previousHeightCM = distance_cm; 
        startUltrasonicMeasurement(); // Trigger a new measurement
        lastDistanceSampleTime = millis();
    }

    switch (currentState) {
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
    if (newState != currentState) {
        takeoffStartTime = 0;
        landingStartTime = 0;
        takeoffLastHeight = 0;
    }
    currentState = newState;
}