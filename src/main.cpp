#include <Adafruit_BNO08x.h>
#include <math.h>
#include "main.h"
#include "imu.h"
#include "pid.h"
#include "motors.h"
#include "utils.h"
#include "states.h"
#include "ultrasonic.h"
#include "baromter.h"

// --- TIMING ---
unsigned long current_time, prev_time;
float dt;

void setup() {
	pinMode(LED_BUILTIN, OUTPUT);
	digitalWrite(LED_BUILTIN, HIGH); // Turn on built-in LED to indicate setup start

	// Initialize ultrasonic sensor
    initUltrasonic();
	// Initialize barometer
	if (!initBarometer()) {
		while (1) {
			digitalWrite(LED_BUILTIN, LOW);
			delay(500);
			digitalWrite(LED_BUILTIN, HIGH);
			delay(500);
		}
	}
	// Initialize state machine
	initStates();
	// Initialize IMU
	if (!initIMU()){
		while (1) {
			digitalWrite(LED_BUILTIN, LOW); // Blink built-in LED to indicate IMU init failure
			delay(1000);
			digitalWrite(LED_BUILTIN, HIGH);
			delay(1000);
		}
	}
	// Initialize motors
	initMotors();
	prev_time = micros();
}

void loop() {
	// Calculate delta time
	current_time = micros();
	dt = (current_time - prev_time) / 1000000.0;
	prev_time = current_time;

	// Get latest distance reading (non-blocking)
	getUltrasonicDistanceCM();
	// Update state machine based on sensor readings and time
	updateStates();

	
	readIMU();
	calculatePID();
	mixMotors();

	delay(2); 
}