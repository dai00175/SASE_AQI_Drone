#ifndef IMU_H
#define IMU_H

#include <Adafruit_BNO08x.h>

// --- HARDWARE PINS ---
#define BNO08X_CS 10
#define BNO08X_INT 9
#define BNO08X_RESET 8

// --- IMU OBJECTS ---
extern Adafruit_BNO08x bno08x;
extern sh2_SensorValue_t sensorValue;

// --- IMU STATE VARIABLES ---
extern float roll_IMU, pitch_IMU, yaw_IMU;
extern float gyroX, gyroY, gyroZ;
extern float rollOffset, pitchOffset, yawOffset;

// --- FUNCTION DECLARATIONS ---
bool initIMU();
void readIMU();

#endif