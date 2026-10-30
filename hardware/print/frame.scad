// 100 mm brushed X-frame with prop guards, ESP32-CAM tray and VL53L0X slot.
// Units: mm. Print flat. See README.md in this folder.

// ---- parameters -----------------------------------------------------------
diag          = 100;    // motor-to-motor diagonal distance
motor_d       = 8.6;    // 8.5 mm coreless motor, slight press fit
motor_wall    = 1.4;
holder_h      = 9;
arm_w         = 5;
arm_h         = 3.5;
prop_d        = 65;
guard_gap     = 3;      // clearance between prop tip and guard
guard_t       = 1.0;    // guard ring thickness
guard_h       = 4;
plate_d       = 34;     // centre plate diameter
plate_t       = 2;
fc_hole_pitch = 25.5;   // whoop FC pattern
fc_hole_d     = 2.2;    // for M2 screws or press pins
cam_w         = 27.5;   // ESP32-CAM board 27 x 40.5
cam_l         = 40.5;
cam_tilt      = 10;     // degrees nose-down
tof_w         = 11;     // VL53L0X breakout ~ 11 x 25 (check yours)
tof_l         = 25;
strap_w       = 10.5;

$fn = 64;

half = diag / 2;                 // distance centre -> motor along the X arm
guard_r = prop_d / 2 + guard_gap;

module motor_holder() {
    difference() {
        cylinder(d = motor_d + 2 * motor_wall, h = holder_h);
        translate([0, 0, -1]) cylinder(d = motor_d, h = holder_h + 2);
        // wire exit slot
        translate([-1.2, 0, 1.5]) cube([2.4, motor_d, holder_h]);
    }
}

module arm(angle) {
    rotate([0, 0, angle]) {
        // arm beam from centre to motor
        translate([0, -arm_w / 2, 0]) cube([half - 2, arm_w, arm_h]);
        translate([half, 0, 0]) motor_holder();
        // prop guard ring, open on the inner side where it meets the arm
        translate([half, 0, 0]) difference() {
            cylinder(r = guard_r + guard_t, h = guard_h);
            translate([0, 0, -1]) cylinder(r = guard_r, h = guard_h + 2);
        }
        // two spokes to stiffen the ring
        for (a = [-50, 50])
            translate([half, 0, 0]) rotate([0, 0, a])
                translate([motor_d / 2 + motor_wall - 0.5, -1, 0])
                    cube([guard_r - motor_d / 2 - motor_wall + 0.5, 2, arm_h]);
    }
}

module centre_plate() {
    difference() {
        cylinder(d = plate_d, h = plate_t);
        // FC mounting holes
        for (x = [-1, 1], y = [-1, 1])
            translate([x * fc_hole_pitch / 2, y * fc_hole_pitch / 2, -1])
                cylinder(d = fc_hole_d, h = plate_t + 2);
        // battery strap slots
        for (y = [-1, 1])
            translate([-strap_w / 2, y * 11 - 1, -1]) cube([strap_w, 2, plate_t + 2]);
        // lightening hole
        translate([0, 0, -1]) cylinder(d = 9, h = plate_t + 2);
    }
}

module cam_tray() {
    // Posts rise from the plate; the tray sits above the FC and leans the camera down.
    post_h = 12;
    for (x = [-1, 1], y = [-1, 1])
        translate([x * (cam_w / 2 - 2), y * (cam_l / 2 - 4), plate_t])
            cylinder(d = 3.5, h = post_h);
    translate([0, 0, plate_t + post_h]) rotate([cam_tilt, 0, 0]) difference() {
        translate([-cam_w / 2 - 1.5, -cam_l / 2 - 1.5, 0]) cube([cam_w + 3, cam_l + 3, 1.6]);
        translate([-cam_w / 2 + 2, -cam_l / 2 + 2, -1]) cube([cam_w - 4, cam_l - 4, 4]);
    }
    // side rails to hold the board
    translate([0, 0, plate_t + post_h]) rotate([cam_tilt, 0, 0])
        for (x = [-1, 1])
            translate([x * (cam_w / 2 + 0.75) - 0.75, -cam_l / 2 - 1.5, 1.6])
                cube([1.5, cam_l + 3, 4]);
}

module tof_slot() {
    // Underside cradle for the rangefinder, sensor window facing down.
    translate([-tof_w / 2 - 1.5, -tof_l / 2 - 1.5, -5]) difference() {
        cube([tof_w + 3, tof_l + 3, 5]);
        translate([1.5, 1.5, -1]) cube([tof_w, tof_l, 7]);
        translate([(tof_w + 3) / 2 - 3, (tof_l + 3) / 2 - 3, -1]) cube([6, 6, 7]); // window
    }
}

module frame() {
    for (a = [45, 135, 225, 315]) arm(a);
    centre_plate();
    cam_tray();
    tof_slot();
}

frame();
