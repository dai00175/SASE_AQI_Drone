#ifndef STATE_MACHINE_H
#define STATE_MACHINE_H

enum DroneState {
    IDLE,
    TAKEOFF,
    USERCNTRL,
    PRGMCNTRL,
    LANDING
};

extern DroneState currentState;

void initStates();
void updateStates();
void setState(DroneState newState);

#endif