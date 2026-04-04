#include <Arduino.h>
#include "pid.h"
#include "imu.h"
#include "main.h"
#include "motors.h"

// --- TUNING GAINS ---
float Kp_roll = 1.5, Ki_roll = 0.5, Kd_roll = 0.05;
float Kp_pitch = 1.5, Ki_pitch = 0.5, Kd_pitch = 0.05;
float Kp_yaw = 2.0, Ki_yaw = 0.0, Kd_yaw = 0.05;
float i_limit = 200.0; // Anti-windup limit

// --- PID STATE VARIABLES ---
float roll_PID = 0, pitch_PID = 0, yaw_PID = 0;
float integral_roll = 0, integral_pitch = 0, integral_yaw = 0;

// --- DESIRED VALUES ---
float roll_des = 0, pitch_des = 0, yaw_des = 0;

void calculatePID() {
    // --- ROLL ---
    float error_roll = roll_des - roll_IMU;
    if (thro_des >= PWM_MIN + 50) {
        integral_roll += error_roll * dt;
    }
    integral_roll = constrain(integral_roll, -i_limit, i_limit);
    roll_PID = (Kp_roll * error_roll) + (Ki_roll * integral_roll) - (Kd_roll * gyroX);

    // --- PITCH ---
    float error_pitch = pitch_des - pitch_IMU;
    if (thro_des >= PWM_MIN + 50) {
        integral_pitch += error_pitch * dt;
    }
    integral_pitch = constrain(integral_pitch, -i_limit, i_limit);
    pitch_PID = (Kp_pitch * error_pitch) + (Ki_pitch * integral_pitch) - (Kd_pitch * gyroY);

    // --- YAW ---
    float error_yaw = yaw_des - yaw_IMU; 
    if (thro_des >= PWM_MIN + 50) {
        integral_yaw += error_yaw * dt;
    }
    integral_yaw = constrain(integral_yaw, -i_limit, i_limit);
    yaw_PID = (Kp_yaw * error_yaw) + (Ki_yaw * integral_yaw) - (Kd_yaw * gyroZ);
}