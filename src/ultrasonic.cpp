#include <Arduino.h>
#include "ultrasonic.h"

// Global variables (volatile because accessed in ISR)
volatile unsigned long echo_start_us = 0;
volatile unsigned long echo_end_us = 0;
volatile bool echo_received = false;
volatile bool measurement_in_progress = false;
volatile unsigned long trigger_time_us = 0;


int distance_cm = 0; // Latest valid distance reading in cm

// Timeout in microseconds (e.g., 30ms = 30000 µs)
const unsigned long ECHO_TIMEOUT_US = 30000;

// Call this once in setup()
void initUltrasonic() {
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    attachInterrupt(digitalPinToInterrupt(ECHO_PIN), echoISR, CHANGE);
}

// ISR – must be very fast, no Serial.print, no delay
void echoISR() {
    if (digitalReadFast(ECHO_PIN) == HIGH) {
        // Rising edge – start of echo
        echo_start_us = micros();
        measurement_in_progress = true;
    } else {
        // Falling edge – end of echo
        echo_end_us = micros();
        measurement_in_progress = false;
        echo_received = true;
    }
}

// Non‑blocking trigger function – call it when you want a new reading
void startUltrasonicMeasurement() {
    if (measurement_in_progress) return; // still waiting for previous echo
    
    // Reset flags
    echo_received = false;
    echo_start_us = 0;
    echo_end_us = 0;
    trigger_time_us = micros();
    
    // Send trigger pulse (10 µs)
    digitalWriteFast(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWriteFast(TRIG_PIN, LOW);
    
    // Measurement is now in progress; ISR will catch the echo
    measurement_in_progress = true;
}

// Call this in your main loop (or at 100‑200 Hz) to get the latest distance
void getUltrasonicDistanceCM() {
    // Check if a new measurement is ready
    if (!echo_received) {
        // Also check for timeout: if measurement started but echo never fell
        if (measurement_in_progress && (micros() - trigger_time_us) > ECHO_TIMEOUT_US) {
            // Timeout – abort this measurement
            measurement_in_progress = false;
            echo_received = false;
            distance_cm = DIST_NA; // Set to invalid reading
        }
        return;
    }
    
    // Compute pulse width in microseconds
    unsigned long pulse_width = echo_end_us - echo_start_us;
    // Convert to cm (speed of sound ~343 m/s → 1µs = 0.01715 cm round trip)
    // For round trip: distance = pulse_width * 0.01715 / 2? Actually:
    // Speed = 343 m/s = 0.0343 cm/µs. Time for round trip = pulse_width.
    // Distance = (0.0343 * pulse_width) / 2 = 0.01715 * pulse_width.
    distance_cm = pulse_width * 0.01715;
    
    // Reset for next measurement
    echo_received = false;
    measurement_in_progress = false;
}