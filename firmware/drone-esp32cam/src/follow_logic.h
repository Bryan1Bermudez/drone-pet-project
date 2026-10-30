// Port of firmware/companion/follow/visual.py. Keep the two in sync; the Python file
// has the tests.
#pragma once

#include <stdint.h>

static const int RC_MIN = 1000;
static const int RC_MID = 1500;
static const int RC_MAX = 2000;

enum class FollowState : uint8_t { IDLE, TAKEOFF, FOLLOW, SEARCH, LAND };

struct VisualConfig {
  float target_height_m = 1.2f;
  int hover_throttle = 1450;
  float kp_height = 300.0f;
  float kd_height = 150.0f;
  float ki_height = 60.0f;
  float i_limit = 0.5f;
  int throttle_min = 1100;
  int throttle_max = 1750;
  float takeoff_ramp_us_per_s = 250.0f;
  float land_descent_mps = 0.35f;
  float land_cutoff_height_m = 0.12f;
  float land_ramp_us_per_s = 150.0f;

  float kp_yaw = 250.0f;
  float yaw_deadband = 0.10f;
  int yaw_max = 180;
  int search_yaw = 60;

  float target_area_frac = 0.004f;
  float kp_pitch = 120.0f;
  float pitch_deadband = 0.25f;
  int pitch_max = 110;

  uint32_t min_blob_pixels = 6;
  float lost_search_after_s = 0.5f;
  float lost_land_after_s = 10.0f;
  float height_timeout_s = 0.5f;
  float flight_time_limit_s = 240.0f;
};

struct Observation {
  float t;
  bool blob_found;
  float cx;
  float cy;
  float area_frac;
  bool height_valid;
  float height_m;
  bool button_long;
  bool button_short;
};

struct RcOut {
  int roll = RC_MID;
  int pitch = RC_MID;
  int throttle = RC_MIN;
  int yaw = RC_MID;
  int arm = RC_MIN;
  FollowState state = FollowState::IDLE;
};

class VisualFollower {
 public:
  explicit VisualFollower(const VisualConfig &cfg) : cfg_(cfg) {}
  RcOut update(const Observation &o);
  FollowState state() const { return state_; }
  float last_height() const { return last_height_; }

 private:
  void enter(FollowState s, float t);
  void disarm();
  bool height_ok(float t) const { return t - t_last_height_ <= cfg_.height_timeout_s; }
  void track_height(const Observation &o, float dt);
  float height_loop(float target, float dt);

  VisualConfig cfg_;
  FollowState state_ = FollowState::IDLE;
  float t_state_ = 0.0f;
  float t_armed_ = 0.0f;
  float t_last_seen_ = 0.0f;
  float t_last_height_ = -1e9f;
  bool have_height_ = false;
  float last_height_ = 0.0f;
  float height_rate_ = 0.0f;
  float i_term_ = 0.0f;
  float throttle_ = RC_MIN;
  bool have_last_t_ = false;
  float last_t_ = 0.0f;
  float land_target_h_ = 0.0f;
};

const char *follow_state_name(FollowState s);
