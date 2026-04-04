#ifndef ULTRASONIC_H
#define ULTRASONIC_H

// Ultrasonic Pins (HC-SR04)
#define TRIG_PIN 14
#define ECHO_PIN 15

// Parameters
#define TAKEOFF_HEIGHT_CM 200  // 2 meters in cm
#define MAX_HEIGHT_CM 400      // 4 meters max sensor range
#define DIST_NA 9999          // Value to indicate no valid reading
#define LANDING_THRESHOLD_CM 20 // Close to ground for landing complete

extern int distance_cm; // Latest valid distance reading in cm

void initUltrasonic();
void startUltrasonicMeasurement();
void getUltrasonicDistanceCM();

#endif