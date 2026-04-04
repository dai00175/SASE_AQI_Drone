#ifndef PID_H
#define PID_H

// --- TUNING GAINS ---
extern float Kp_roll, Ki_roll, Kd_roll;
extern float Kp_pitch, Ki_pitch, Kd_pitch;
extern float Kp_yaw, Ki_yaw, Kd_yaw;
extern float i_limit; // Anti-windup limit

// --- PID STATE VARIABLES ---
extern float roll_PID, pitch_PID, yaw_PID;
extern float integral_roll, integral_pitch, integral_yaw;

// --- DESIRED VALUES ---
extern float roll_des, pitch_des, yaw_des;

// --- FUNCTION DECLARATIONS ---
void calculatePID();

#endif