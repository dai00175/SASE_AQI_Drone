#include <Arduino.h>
#include "motors.h"
#include "pid.h"

class ESC {
private:
    int _pin;
    int _min_us;
    int _max_us;
    float _freq_hz;
    float _period_us;
    float _max_duty;
    
    int usToAnalogWrite(int microseconds) {
        float dutyCycle = microseconds / _period_us;
        return (int)(dutyCycle * _max_duty);
    }
    
public:
    ESC() : _pin(-1), _min_us(1000), _max_us(2000), _freq_hz(400) {
        _period_us = 1000000.0 / _freq_hz;
        _max_duty = 4096.0;
    }
    
    void attach(int pin, int min_us = 1000, int max_us = 2000) {
        _pin = pin;
        _min_us = min_us;
        _max_us = max_us;
        
        pinMode(_pin, OUTPUT);
        analogWriteFrequency(_pin, _freq_hz);
        analogWriteResolution(12);
    }
    
    void writeMicroseconds(int microseconds) {
        if (_pin == -1) return;
        microseconds = constrain(microseconds, _min_us, _max_us);
        int analogValue = usToAnalogWrite(microseconds);
        analogWrite(_pin, analogValue);
    }
    
    void write(int percent) {
        // percent from 0 to 100
        int us = map(percent, 0, 100, _min_us, _max_us);
        writeMicroseconds(us);
    }
    
    void setFrequency(float freq_hz) {
        _freq_hz = freq_hz;
        _period_us = 1000000.0 / _freq_hz;
        if (_pin != -1) {
            analogWriteFrequency(_pin, _freq_hz);
        }
    }
};

// --- MOTOR PINS ---
const int motorPins[4] = {2, 3, 4, 5}; // Front Right, Back Right, Back Left, Front Left

// --- CREATE ESC OBJECTS ---
ESC escs[4];

// --- PWM CONSTANTS ---
const int PWM_OFF = 1000;
const int PWM_MAX = 2000;

// --- REFRESH RATE ---
const int PWM_REFRESH_HZ = 300;  // 300 Hz refresh rate response

// --- THROTTLE ---
int thro_des = 0;

void initMotors() {
    for (int i = 0; i < 4; i++) {
        escs[i].attach(motorPins[i], PWM_OFF, PWM_MAX);
        escs[i].setFrequency(PWM_REFRESH_HZ);
        escs[i].writeMicroseconds(PWM_OFF);
    }
    delay(2000);
}

void mixMotors() {
    int base = PWM_OFF + thro_des;
    int motorOutputs[4];
    motorOutputs[0] = base + roll_PID - pitch_PID + yaw_PID; // Front Right
    motorOutputs[1] = base + roll_PID + pitch_PID - yaw_PID; // Back Right
    motorOutputs[2] = base - roll_PID + pitch_PID + yaw_PID; // Back Left
    motorOutputs[3] = base - roll_PID - pitch_PID - yaw_PID; // Front Left

    for (int i = 0; i < 4; i++) {
        escs[i].writeMicroseconds(constrain(motorOutputs[i], PWM_OFF, PWM_MAX));
    }
}