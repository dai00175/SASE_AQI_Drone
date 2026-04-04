#include "baromter.h"

// Moving average buffers (static inside this file)
static float pressureBuffer[BARO_WINDOW_SIZE];
static int bufferIndex = 0;
static float runningSum = 0.0f;
static bool bufferFull = false;

// Latest values
static float rawPressure = 0.0f;
static float filteredPressure = 0.0f;
static float altitude = 0.0f;

// Helper: write a register
static bool writeReg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(LPS28DFW_ADDR);
    Wire.write(reg);
    Wire.write(val);
    return (Wire.endTransmission() == 0);
}

// Helper: read a single byte
static bool readReg(uint8_t reg, uint8_t &val) {
    Wire.beginTransmission(LPS28DFW_ADDR);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(LPS28DFW_ADDR, (uint8_t)1) != 1) return false;
    val = Wire.read();
    return true;
}

bool initBarometer() {
    Wire.begin(); // Ensure Wire is started (call once in main setup)
    
    // Check WHO_AM_I
    uint8_t whoami = 0;
    if (!readReg(LPS28DFW_WHO_AM_I, whoami)) return false;
    if (whoami != LPS28DFW_ID) return false;
    
    // Configure for highest ODR (200 Hz) + 4‑sample averaging
    // CTRL_REG1: ODR = 200 Hz (0x70), AVG = 4 samples (0x30) → total 0x70? Wait, datasheet:
    // Bits 7:4 ODR selection: 0x7 = 200 Hz (111), Bits 3:2 AVG: 11 = 4 samples.
    // So CTRL_REG1 = (0x7 << 4) | (0x3 << 2) = 0x70 | 0x0C = 0x7C.
    // But earlier code used 0x30 (10 Hz, 4 samples). We want maximum speed.
    if (!writeReg(LPS28DFW_CTRL_REG1, 0x7C)) return false;
    
    // CTRL_REG2: Mode 1 (1260 hPa range) + BDU enabled (block data update)
    // BDU = bit 2, Mode1 = bit 3? Actually: bit 3 = 1 for Mode1, bit 2 = 1 for BDU.
    // So 0x0C (binary 1100) is correct: Mode1 (bit3) + BDU (bit2).
    if (!writeReg(LPS28DFW_CTRL_REG2, 0x0C)) return false;
    
    // Optional: CTRL_REG3 (interrupts) – leave default (0x00)
    
    // Fill the moving average buffer by taking several readings
    // Sensor may need a few ms to start. Read up to WINDOW_SIZE times.
    for (int i = 0; i < BARO_WINDOW_SIZE; i++) {
        updateBarometer();     // reads and updates buffer
        delay(5);              // 5 ms between readings (still > 200 Hz)
    }
    
    return true;
}

bool updateBarometer() {
    // Read 3 pressure registers (XL, L, H) – little endian, 24‑bit two's complement
    Wire.beginTransmission(LPS28DFW_ADDR);
    Wire.write(LPS28DFW_PRESS_OUT_XL);
    if (Wire.endTransmission(false) != 0) return false;
    
    if (Wire.requestFrom(LPS28DFW_ADDR, (uint8_t)3) != 3) return false;
    
    uint32_t raw24 = 0;
    raw24 |= Wire.read();         // XL
    raw24 |= (Wire.read() << 8);  // L
    raw24 |= (Wire.read() << 16); // H
    
    // Convert 24‑bit signed to int32_t
    int32_t pressure_raw = (int32_t)raw24;
    if (pressure_raw & 0x800000) {
        pressure_raw |= 0xFF000000; // sign extend
    }
    
    // Convert to hPa (resolution = 4096 LSB/hPa)
    rawPressure = (float)pressure_raw / 4096.0f;
    
    // --- Moving average update (non‑blocking, fast) ---
    runningSum -= pressureBuffer[bufferIndex];
    pressureBuffer[bufferIndex] = rawPressure;
    runningSum += rawPressure;
    bufferIndex = (bufferIndex + 1) % BARO_WINDOW_SIZE;
    if (bufferIndex == 0) bufferFull = true;
    
    int samples = bufferFull ? BARO_WINDOW_SIZE : bufferIndex;
    filteredPressure = runningSum / (float)samples;
    
    // --- Altitude calculation (standard barometric formula) ---
    // Sea level pressure = 1013.25 hPa
    const float SEA_LEVEL_HPA = 1013.25f;
    // Formula: altitude = 44330 * (1 - (P/P0)^0.1903)
    float ratio = filteredPressure / SEA_LEVEL_HPA;
    altitude = 44330.0f * (1.0f - powf(ratio, 0.1903f));
    
    return true;
}

float getAltitude() {
    return altitude;
}

float getRawPressure() {
    return rawPressure;
}

float getFilteredPressure() {
    return filteredPressure;
}