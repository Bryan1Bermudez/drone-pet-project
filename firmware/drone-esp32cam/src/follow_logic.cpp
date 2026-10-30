#include "follow_logic.h"

#include <math.h>

namespace {
float clampf(float v, float lo, float hi) { return v < lo ? lo : v > hi ? hi : v; }
int rc_round(float v) { return static_cast<int>(floorf(v + 0.5f)); }
float sign_of(float v) { return v < 0 ? -1.0f : 1.0f; }
}  // namespace

const char *follow_state_name(FollowState s) {
  switch (s) {
    case FollowState::IDLE: return "IDLE";
    case FollowState::TAKEOFF: return "TAKEOFF";
    case FollowState::FOLLOW: return "FOLLOW";
    case FollowState::SEARCH: return "SEARCH";
    case FollowState::LAND: return "LAND";
  }
  return "?";
}

void VisualFollower::enter(FollowState s, float t) {
  if (s == FollowState::LAND && have_height_) land_target_h_ = last_height_;
  state_ = s;
  t_state_ = t;
}

void VisualFollower::disarm() {
  state_ = FollowState::IDLE;
  throttle_ = RC_MIN;
  i_term_ = 0.0f;
}

void VisualFollower::track_height(const Observation &o, float dt) {
  if (!o.height_valid) return;
  if (have_height_ && dt > 0.0f) {
    const float raw_rate = (o.height_m - last_height_) / dt;
    height_rate_ += 0.3f * (raw_rate - height_rate_);
  }
  last_height_ = o.height_m;
  have_height_ = true;
  t_last_height_ = o.t;
}

float VisualFollower::height_loop(float target, float dt) {
  const float h = have_height_ ? last_height_ : target;
  const float err = target - h;
  i_term_ = clampf(i_term_ + err * dt, -cfg_.i_limit, cfg_.i_limit);
  const float u = cfg_.hover_throttle + cfg_.kp_height * err - cfg_.kd_height * height_rate_ +
                  cfg_.ki_height * i_term_;
  return clampf(u, cfg_.throttle_min, cfg_.throttle_max);
}

RcOut VisualFollower::update(const Observation &o) {
  float dt = 0.0f;
  if (have_last_t_) dt = clampf(o.t - last_t_, 0.0f, 0.2f);
  last_t_ = o.t;
  have_last_t_ = true;

  track_height(o, dt);
  if (o.blob_found) t_last_seen_ = o.t;

  // --- state transitions ---------------------------------------------------
  if (state_ == FollowState::IDLE) {
    if (o.button_long && height_ok(o.t)) {
      enter(FollowState::TAKEOFF, o.t);
      t_armed_ = o.t;
      throttle_ = cfg_.throttle_min;
      i_term_ = 0.0f;
    }
  } else {
    if (o.button_short || o.button_long) {
      enter(FollowState::LAND, o.t);
    } else if (o.t - t_armed_ > cfg_.flight_time_limit_s) {
      enter(FollowState::LAND, o.t);
    } else if (!height_ok(o.t) && state_ != FollowState::LAND) {
      enter(FollowState::LAND, o.t);
    }
  }

  if (state_ == FollowState::TAKEOFF) {
    if (have_height_ && last_height_ > 0.8f * cfg_.target_height_m) {
      enter(o.blob_found ? FollowState::FOLLOW : FollowState::SEARCH, o.t);
    }
  } else if (state_ == FollowState::FOLLOW) {
    if (o.t - t_last_seen_ > cfg_.lost_search_after_s) enter(FollowState::SEARCH, o.t);
  } else if (state_ == FollowState::SEARCH) {
    if (o.blob_found) {
      enter(FollowState::FOLLOW, o.t);
    } else if (o.t - t_last_seen_ > cfg_.lost_land_after_s) {
      enter(FollowState::LAND, o.t);
    }
  }

  // --- outputs ---------------------------------------------------------------
  RcOut out;
  out.state = state_;
  if (state_ == FollowState::IDLE) return out;

  out.arm = RC_MAX;

  if (state_ == FollowState::TAKEOFF) {
    throttle_ = fminf(throttle_ + cfg_.takeoff_ramp_us_per_s * dt, cfg_.throttle_max);
    const float h = have_height_ ? last_height_ : 0.0f;
    if (h > 0.3f * cfg_.target_height_m) throttle_ = height_loop(cfg_.target_height_m, dt);
    out.throttle = static_cast<int>(throttle_);
    return out;
  }

  if (state_ == FollowState::LAND) {
    if (height_ok(o.t) && have_height_) {
      land_target_h_ = fmaxf(0.0f, land_target_h_ - cfg_.land_descent_mps * dt);
      throttle_ = height_loop(land_target_h_, dt);
      if (last_height_ < cfg_.land_cutoff_height_m && land_target_h_ <= 0.0f) {
        disarm();
        RcOut idle;
        return idle;
      }
    } else {
      throttle_ -= cfg_.land_ramp_us_per_s * dt;
      if (throttle_ <= cfg_.throttle_min) {
        disarm();
        RcOut idle;
        return idle;
      }
    }
    out.throttle = static_cast<int>(throttle_);
    return out;
  }

  // FOLLOW or SEARCH: hold height.
  throttle_ = height_loop(cfg_.target_height_m, dt);
  out.throttle = static_cast<int>(throttle_);

  if (state_ == FollowState::SEARCH) {
    out.yaw = RC_MID + cfg_.search_yaw;
    return out;
  }

  if (fabsf(o.cx) > cfg_.yaw_deadband) {
    const float yaw = cfg_.kp_yaw * (o.cx - sign_of(o.cx) * cfg_.yaw_deadband);
    out.yaw = rc_round(RC_MID + clampf(yaw, -cfg_.yaw_max, cfg_.yaw_max));
  }

  if (o.area_frac > 0.0f) {
    const float e = logf(cfg_.target_area_frac / o.area_frac);
    if (fabsf(e) > cfg_.pitch_deadband) {
      const float pitch = cfg_.kp_pitch * (e - sign_of(e) * cfg_.pitch_deadband);
      out.pitch = rc_round(RC_MID + clampf(pitch, -cfg_.pitch_max, cfg_.pitch_max));
    }
  }
  return out;
}
