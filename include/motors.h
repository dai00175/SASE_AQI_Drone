#ifndef MOTORS_H
#define MOTORS_H

// --- MOTOR PINS ---
extern const int motorFR; // Front Right
extern const int motorBR; // Back Right
extern const int motorBL; // Back Left
extern const int motorFL; // Front Left

// --- PWM CONSTANTS ---
extern const int PWM_OFF; // Keeps it off.
extern const int PWM_MIN; // Turns it on. Not flying. Hopefully.
extern const int PWM_LOW;
extern const int PWM_TAKEOFF; // Might be a take off speed with 4 motors
extern const int PWM_HOVER;
extern const int PWM_MID;
extern const int PWM_MAX;

// --- THROTTLE ---
extern int thro_des;

// --- FUNCTION DECLARATIONS ---
void initMotors();
void mixMotors();

#endif