# Hardware

## Parts

| Part | Used here | Notes |
|---|---|---|
| Frame | F450 quad frame | Red arms = front |
| Flight controller | Pixhawk 2.4.8 (fmuv3, 2 MB) | ArduCopter 4.7.2 |
| GPS + compass | M10 GPS module on a GS1 folding mast | Mount it high, away from power wires |
| Motors | 4 × 2212 920 KV | |
| ESCs | 4 × SimonK ESC | Calibrated to 1000–2000 µs |
| Propellers | 1045 (10 × 4.5"), 2 × CW and 2 × CCW | Check the direction by the blade shape, not the colour (see lessons learned) |
| Battery | 3S LiPo, 5200 mAh | About 12.4 V full, land by about 11.1 V under load |
| Radio | FlySky FS-i6 transmitter + iA6B receiver | PPM into the Pixhawk RC IN |
| Companion computer | Raspberry Pi 4 | With a small 5 V fan |
| Camera | Raspberry Pi camera, OV5647 | Lens pointing straight down |
| Pi power | Hobbywing 3 A UBEC, set to 5 V | Ferrite ring on the output lead |

Total cost was roughly Rp 8 million including spares.

## Wiring

**Plug and unplug every power wire only with the battery disconnected.** The first Raspberry Pi in this build died after the UBEC lead was connected while the battery was plugged in.

### Raspberry Pi 4 GPIO

| Pi pin | Connects to |
|---|---|
| 2 (5 V) | UBEC + (red) |
| 20 (GND) | UBEC − |
| 4 (5 V) and 6 (GND) | Cooling fan |
| 8 (GPIO14, TXD) | Pixhawk TELEM2 RX |
| 10 (GPIO15, RXD) | Pixhawk TELEM2 TX |
| 14 (GND) | Pixhawk TELEM2 GND |

Do **not** connect the 5 V pin of TELEM2 to the Pi. Measure 5.0–5.3 V on the UBEC output with a multimeter before connecting it.

### ESCs to Pixhawk MAIN OUT

Standard ArduCopter quad-X order (motor 1 front-right, 2 back-left, 3 front-left, 4 back-right). On this Pixhawk's servo rail the **signal pin is the bottom row** of the connector; check yours with a multimeter before plugging in.

## Pixhawk parameters (changed from default)

| Parameter | Value | Why |
|---|---|---|
| FRAME_CLASS / FRAME_TYPE | 1 / 1 | Quad, X layout |
| MOT_PWM_MIN / MOT_PWM_MAX | 1000 / 2000 | Matches the ESC calibration |
| BARO_OPTIONS | 1 | This board has an MS5607 barometer chip in place of the MS5611; without this, the board reads half the real air pressure |
| SERIAL2_PROTOCOL | 2 | MAVLink2 on TELEM2 (to the Pi) |
| SERIAL2_BAUD | 921 | 921600 baud |
| PLND_ENABLED | 1 | Precision landing on |
| PLND_TYPE | 1 | Target position comes from the companion computer (MAVLink) |
| PLND_EST_TYPE | 1 | Kalman filter estimator |
| PLND_STRICT | 0 | If the marker is lost, keep landing normally |
| PLND_CAM_POS_X / Y / Z | 0 / −0.13 / 0.045 | Camera position relative to the flight controller, in metres (forward / right / down) |
| FLTMODE (switch C) | Stabilize / Loiter / Land | Three-position switch |
| FS_THR_ENABLE, battery failsafe | Land | |
| LOG_DISARMED | 0 | Only log while armed |

Camera calibration for the OV5647 at 640×480 gave fx ≈ 566, fy ≈ 569 (RMS reprojection error 0.75 px). Run `software/calibrate.py` for your own camera; it saves `camera_calib.npz`.

## Lessons learned during the build

- **Propeller colour labels can be wrong.** The seller's colour coding for CW and CCW props was reversed. The drone wouldn't lift and one prop spun off. Check the direction from the blade shape: the higher leading edge must face the direction of rotation.
- **Check which row of the servo rail is signal.** The first motor test did nothing because the ESC leads were plugged in upside down. A multimeter settles it in a minute.
- **Clone barometers.** Altitude went wild until `BARO_OPTIONS = 1` told ArduPilot the board has an MS5607 chip.
- **Re-seat connectors after a crash or knock.** When the GPS mast was knocked off, the GPS and second compass vanished from the system. The fix was a loose cable plus a compass recalibration.
- **Hot-plugging power kills boards.** See the wiring section above.
- **Wait for the lock before switching to Land.** `PrecLand: Init Failed` means Land was selected before the estimator had locked onto the marker.
