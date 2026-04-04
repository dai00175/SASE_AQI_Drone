#include <Arduino.h>
#include <Adafruit_BNO08x.h>
#include <math.h>
#include "imu.h"
#include "utils.h"

// --- IMU OBJECTS ---
Adafruit_BNO08x bno08x(BNO08X_RESET);
sh2_SensorValue_t sensorValue;
sh2_SensorValue_t dummy;

// --- IMU STATE VARIABLES ---
float roll_IMU, pitch_IMU, yaw_IMU;
float gyroX, gyroY, gyroZ;
float rollOffset, pitchOffset, yawOffset;

bool initIMU() {
    // 1. Hardware reset
    pinMode(BNO08X_RESET, OUTPUT);
    digitalWrite(BNO08X_RESET, LOW);
    delay(100);
    digitalWrite(BNO08X_RESET, HIGH);
    delay(100);

    // 2. Start SPI (frequency already set to 3 MHz in library)
    if (!bno08x.begin_SPI(BNO08X_CS, BNO08X_INT)) {
        return false; // Initialization failed
    }

    // 3. Enable only Game Rotation Vector for zeroing
    bno08x.enableReport(SH2_GAME_ROTATION_VECTOR, 2500); // 400 Hz

    // 4. Let sensor stabilize and fill its FIFO
    delay(400);

    // 5. Average 20 orientation readings (convert each quaternion to Euler)
    float sumRoll = 0, sumPitch = 0, sumYaw = 0;
    int samples = 0;
    unsigned long startTime = millis();
    
    while (samples < 20) {
        if (bno08x.getSensorEvent(&sensorValue)) {
            if (sensorValue.sensorId == SH2_GAME_ROTATION_VECTOR) {
                float r = sensorValue.un.gameRotationVector.real;
                float i = sensorValue.un.gameRotationVector.i;
                float j = sensorValue.un.gameRotationVector.j;
                float k = sensorValue.un.gameRotationVector.k;
                
                float roll, pitch, yaw;
                quaternionToEuler(r, i, j, k, roll, pitch, yaw);
                
                sumRoll += roll;
                sumPitch += pitch;
                sumYaw += yaw;
                samples++;
            }
        }
    }
    
    // Compute offsets (average Euler angles)
    rollOffset  = sumRoll / 20.0;
    pitchOffset = sumPitch / 20.0;
    yawOffset   = sumYaw / 20.0;

    // 6. Now enable all required reports (no reset!)
    bno08x.enableReport(SH2_GYROSCOPE_CALIBRATED, 2500);   // 400 Hz
    bno08x.enableReport(SH2_LINEAR_ACCELERATION, 5000);    // 200 Hz

    // 7. Drain the FIFO to discard stale data from startup
    sh2_SensorValue_t dummy;
    while (bno08x.getSensorEvent(&dummy)) {
        // just read and discard
    }

    return true; // Initialization successful
}

void readIMU() {
  if (bno08x.getSensorEvent(&sensorValue)) {
    switch (sensorValue.sensorId) {
        case SH2_GAME_ROTATION_VECTOR:
            float r = sensorValue.un.gameRotationVector.real;
            float i = sensorValue.un.gameRotationVector.i;
            float j = sensorValue.un.gameRotationVector.j;
            float k = sensorValue.un.gameRotationVector.k;
            float rawR, rawP, rawY;
            quaternionToEuler(r, i, j, k, rawR, rawP, rawY);
            
            roll_IMU = rawR - rollOffset;
            pitch_IMU = rawP - pitchOffset;
            yaw_IMU = rawY - yawOffset;
            break;

        case SH2_GYROSCOPE_CALIBRATED:
            gyroX = sensorValue.un.gyroscope.x * 180.0 / M_PI;
            gyroY = sensorValue.un.gyroscope.y * 180.0 / M_PI;
            gyroZ = sensorValue.un.gyroscope.z * 180.0 / M_PI;
            break;
        
        case SH2_LINEAR_ACCELERATION:
            float ax = sensorValue.un.linearAcceleration.x;
            float ay = sensorValue.un.linearAcceleration.y;
            float az = sensorValue.un.linearAcceleration.z;
            // Use for velocity estimation or other purposes as needed
            break;
    }
}