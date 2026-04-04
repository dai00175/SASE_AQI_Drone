#ifndef BAROMETER_H
#define BAROMETER_H

#include <Arduino.h>
#include <Wire.h>

// I2C address (SDO pin low)
#define LPS28DFW_ADDR      0x5C

// Register map
#define LPS28DFW_WHO_AM_I  0x0F
#define LPS28DFW_CTRL_REG1 0x10
#define LPS28DFW_CTRL_REG2 0x11
#define LPS28DFW_CTRL_REG3 0x12
#define LPS28DFW_PRESS_OUT_XL 0x28

// Expected WHO_AM_I value
#define LPS28DFW_ID        0xB4

// Moving average window size (power of two for faster wrap)
#define BARO_WINDOW_SIZE   16

/**
 * @brief Initialise the LPS28DFW barometer.
 * 
 * Configures the sensor for highest ODR (200 Hz) with 4‑sample averaging.
 * Reads a few samples to fill the moving average buffer before returning.
 * 
 * @return true if initialisation succeeded, false otherwise.
 */
bool initBarometer();

/**
 * @brief Non‑blocking update of pressure and altitude.
 * 
 * Reads the three pressure registers via I2C, converts to hPa,
 * updates the moving average buffer, and computes filtered altitude.
 * 
 * @return true if a new reading was obtained, false if I2C error.
 */
bool updateBarometer();

/**
 * @brief Get the latest filtered altitude in meters.
 * 
 * Assumes standard sea‑level pressure of 1013.25 hPa.
 * 
 * @return Altitude in meters (filtered by moving average).
 */
float getAltitude();

/**
 * @brief Get the latest raw unfiltered pressure in hPa.
 * 
 * @return Pressure in hPa.
 */
float getRawPressure();

/**
 * @brief Get the filtered pressure (moving average) in hPa.
 * 
 * @return Filtered pressure in hPa.
 */
float getFilteredPressure();

#endif