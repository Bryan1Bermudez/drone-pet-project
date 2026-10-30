// LED beacon wristband: open cuff, three 5 mm LED pockets, 2xCR2032 holder cradle.
// Print in TPU for a flexible cuff, or PLA and use the strap slots.

wrist_w      = 62;    // inner width (across the wrist)
wrist_h      = 48;    // inner height
band_t       = 2.4;
band_w       = 24;    // band width along the arm
opening_deg  = 70;    // gap on the underside so it slips on
led_d        = 5.2;
led_spacing  = 9;
holder_w     = 22;    // 2xCR2032 holder with switch: ~ 22 x 36 x 7, check yours
holder_l     = 36;
holder_h     = 7.5;

$fn = 96;

module cuff() {
    difference() {
        scale([wrist_w / 2 + band_t, wrist_h / 2 + band_t, 1]) cylinder(r = 1, h = band_w);
        translate([0, 0, -1]) scale([wrist_w / 2, wrist_h / 2, 1]) cylinder(r = 1, h = band_w + 2);
        // opening at the bottom
        rotate([0, 0, -90 - opening_deg / 2])
            rotate_extrude(angle = opening_deg) translate([0, -1]) square([wrist_w, band_w + 2]);
        // strap slots near the opening (for rigid prints)
        for (s = [-1, 1])
            rotate([0, 0, -90 + s * (opening_deg / 2 + 12)])
                translate([wrist_h / 2 - 1, -1.2, band_w / 2 - 6]) cube([band_t + 4, 2.4, 12]);
    }
}

module led_pockets() {
    // three pockets on top, LEDs pointing up/out
    for (i = [-1, 0, 1])
        translate([i * led_spacing, wrist_h / 2 + band_t, band_w / 2]) rotate([-90, 0, 0])
            difference() {
                cylinder(d = led_d + 2.4, h = 5);
                translate([0, 0, -1]) cylinder(d = led_d, h = 7);
            }
}

module holder_cradle() {
    // sits on the top outer face beside the LEDs, open at the top so the holder slides in
    translate([-holder_w / 2 - 1.2, wrist_h / 2 + band_t - 0.5, -holder_l / 2 + band_w / 2])
        difference() {
            cube([holder_w + 2.4, holder_h + 1.7, holder_l + 2.4]);
            translate([1.2, 1.2, 1.2]) cube([holder_w, holder_h + 2, holder_l]);
            // wire channel to the LEDs
            translate([holder_w / 2 - 1, -1, holder_l / 2]) cube([4, 4, 3]);
        }
}

cuff();
led_pockets();
holder_cradle();
