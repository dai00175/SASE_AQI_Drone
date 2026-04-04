#include <math.h>

void quaternionToEuler(float r, float i, float j, float k, float &roll, float &pitch, float &yaw) {
  float sinr_cosp = 2 * (r * i + j * k);
  float cosr_cosp = 1 - 2 * (i * i + j * j);
  roll = atan2(sinr_cosp, cosr_cosp) * 180.0 / M_PI;
  float sinp = 2 * (r * j - k * i);
  pitch = (abs(sinp) >= 1) ? copysign(M_PI / 2, sinp) * 180.0 / M_PI : asin(sinp) * 180.0 / M_PI;
  float siny_cosp = 2 * (r * k + i * j);
  float cosy_cosp = 1 - 2 * (j * j + k * k);
  yaw = atan2(siny_cosp, cosy_cosp) * 180.0 / M_PI;
}