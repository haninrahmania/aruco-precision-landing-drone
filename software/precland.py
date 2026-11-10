#!/usr/bin/env python3
"""
Precision landing companion for ArduPilot (Raspberry Pi 4 + Pi camera + ArUco).

Detects an ArUco marker with a downward-facing camera and sends MAVLink
LANDING_TARGET messages to the Pixhawk over TELEM2. Optionally (Option 2) also
sends DISTANCE_SENSOR messages using the marker's estimated distance, so
ArduPilot can use the camera as a rangefinder while the marker is visible.

Camera mounting assumed (default):
  - lens pointing straight down
  - top edge of the image = FRONT of the drone (red arms)
  - right edge of the image = RIGHT of the drone
Use --flip-x / --flip-y / --rotate180 if your mount differs (see README).

Usage:
  python3 precland.py --bench                 # print only, no MAVLink
  python3 precland.py                         # normal: send LANDING_TARGET
  python3 precland.py --rangefinder           # also send DISTANCE_SENSOR
"""

import argparse
import math
import os
import signal
import sys
import time

import cv2
import numpy as np

# ----------------------------------------------------------------------------
# Arguments
# ----------------------------------------------------------------------------
p = argparse.ArgumentParser(description="ArUco precision landing for ArduPilot")
p.add_argument("--device", default="/dev/serial0", help="serial port to Pixhawk TELEM2")
p.add_argument("--baud", type=int, default=921600, help="must match SERIAL2_BAUD on the Pixhawk")
p.add_argument("--marker-id", type=int, default=0, help="ArUco id of the landing pad marker")
p.add_argument("--marker-size", type=float, default=0.20, help="printed black square edge length in metres")
p.add_argument("--dict", default="DICT_4X4_50", help="ArUco dictionary name")
p.add_argument("--width", type=int, default=640)
p.add_argument("--height", type=int, default=480)
p.add_argument("--calib", default="camera_calib.npz", help="output of calibrate.py (optional but recommended)")
p.add_argument("--hfov", type=float, default=62.2, help="horizontal FOV in deg, used only if no calibration file")
p.add_argument("--vfov", type=float, default=48.8, help="vertical FOV in deg, used only if no calibration file")
p.add_argument("--flip-x", action="store_true", help="invert left/right")
p.add_argument("--flip-y", action="store_true", help="invert front/back")
p.add_argument("--rotate180", action="store_true", help="camera mounted with image top toward the BACK")
p.add_argument("--rangefinder", action="store_true", help="also send DISTANCE_SENSOR from marker pose (Option 2)")
p.add_argument("--rate", type=float, default=20.0, help="max messages per second")
p.add_argument("--bench", action="store_true", help="no MAVLink, just print detections")
p.add_argument("--save-debug", action="store_true", help="save an annotated frame every 2 s to debug.jpg")
p.add_argument("--usb-camera", type=int, default=None, help="use a USB webcam index instead of the Pi camera")
p.add_argument("--shutdown-channel", type=int, default=0,
               help="RC channel (e.g. 6 = SwA) that shuts the Pi down when ON for 3 s while disarmed; 0 = off")
p.add_argument("--wifi-off-when-armed", action="store_true",
               help="turn the Pi's Wi-Fi off while the drone is armed, back on 10 s after disarm (needs root)")
args = p.parse_args()

# ----------------------------------------------------------------------------
# Camera
# ----------------------------------------------------------------------------
class Camera:
    def __init__(self, w, h, usb_index=None):
        self.picam = None
        self.cap = None
        if usb_index is None:
            try:
                from picamera2 import Picamera2
                self.picam = Picamera2()
                cfg = self.picam.create_video_configuration(
                    main={"size": (w, h), "format": "RGB888"},
                    buffer_count=2,
                )
                self.picam.configure(cfg)
                self.picam.start()
                time.sleep(1.0)
                print(f"[cam] Pi camera started at {w}x{h}")
                return
            except Exception as e:
                print(f"[cam] picamera2 not available ({e}); falling back to OpenCV device 0")
                usb_index = 0
        self.cap = cv2.VideoCapture(usb_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        if not self.cap.isOpened():
            sys.exit("[cam] could not open camera")
        print(f"[cam] OpenCV camera {usb_index} started")

    def read(self):
        if self.picam is not None:
            frame = self.picam.capture_array()  # RGB888 from picamera2 is BGR order for OpenCV
            return frame
        ok, frame = self.cap.read()
        return frame if ok else None

    def close(self):
        if self.picam is not None:
            self.picam.stop()
        if self.cap is not None:
            self.cap.release()


# ----------------------------------------------------------------------------
# Camera intrinsics
# ----------------------------------------------------------------------------
def load_intrinsics(w, h):
    if os.path.exists(args.calib):
        d = np.load(args.calib)
        K, dist = d["K"], d["dist"]
        cw, ch = d["size"]
        if (int(cw), int(ch)) != (w, h):
            sx, sy = w / cw, h / ch
            K = K.copy()
            K[0, 0] *= sx; K[0, 2] *= sx
            K[1, 1] *= sy; K[1, 2] *= sy
            print(f"[cal] calibration was {cw}x{ch}, scaled to {w}x{h}")
        print(f"[cal] loaded {args.calib}: fx={K[0,0]:.1f} fy={K[1,1]:.1f}")
        return K, dist, True
    fx = (w / 2) / math.tan(math.radians(args.hfov) / 2)
    fy = (h / 2) / math.tan(math.radians(args.vfov) / 2)
    K = np.array([[fx, 0, w / 2], [0, fy, h / 2], [0, 0, 1]], dtype=np.float64)
    print(f"[cal] no calibration file, using FOV {args.hfov}x{args.vfov} deg (less accurate)")
    return K, np.zeros(5), False


# ----------------------------------------------------------------------------
# ArUco detector (works with OpenCV 4.6 and 4.7+ APIs)
# ----------------------------------------------------------------------------
aruco = cv2.aruco
dictionary = aruco.getPredefinedDictionary(getattr(aruco, args.dict))
if hasattr(aruco, "ArucoDetector"):
    params = aruco.DetectorParameters()
    params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
    _detector = aruco.ArucoDetector(dictionary, params)
    def detect(gray):
        return _detector.detectMarkers(gray)
else:
    params = aruco.DetectorParameters_create()
    params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
    def detect(gray):
        return aruco.detectMarkers(gray, dictionary, parameters=params)

# 3D corners of the marker (for distance via solvePnP)
s = args.marker_size / 2
OBJ_PTS = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], dtype=np.float64)


# ----------------------------------------------------------------------------
# MAVLink
# ----------------------------------------------------------------------------
master = None
if not args.bench:
    os.environ.setdefault("MAVLINK20", "1")
    from pymavlink import mavutil
    print(f"[mav] connecting to {args.device} @ {args.baud} ...")
    master = mavutil.mavlink_connection(args.device, baud=args.baud,
                                        source_system=1, source_component=197)
    master.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                              mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    hb = master.wait_heartbeat(timeout=15)
    if hb is None:
        sys.exit("[mav] no heartbeat. Check wiring (TX<->RX), SERIAL2_PROTOCOL=2, SERIAL2_BAUD, and Pi UART setup.")
    print(f"[mav] heartbeat from system {master.target_system}")
    if args.shutdown_channel:
        master.mav.command_long_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
            65, 500000, 0, 0, 0, 0, 0)   # RC_CHANNELS at 2 Hz
        print(f"[sw] watching RC channel {args.shutdown_channel} for shutdown")

boot = time.time()
def time_usec():
    return int((time.time() - boot) * 1e6)
def time_ms():
    return int((time.time() - boot) * 1e3) & 0xFFFFFFFF


def send_landing_target(ax, ay, dist_m, sx, sy):
    master.mav.landing_target_send(
        time_usec(),
        0,                                  # target_num
        mavutil.mavlink.MAV_FRAME_BODY_FRD,
        ax, ay,                             # angle_x, angle_y [rad]
        dist_m,                             # distance [m] (0 if unknown)
        sx, sy,                             # size_x, size_y [rad]
    )


def send_distance(dist_m):
    cm = int(max(0, min(dist_m * 100, 1000)))
    master.mav.distance_sensor_send(
        time_ms(),
        20,                                 # min distance cm
        800,                                # max distance cm
        cm,
        mavutil.mavlink.MAV_DISTANCE_SENSOR_UNKNOWN,
        1,                                  # sensor id
        mavutil.mavlink.MAV_SENSOR_ROTATION_PITCH_270,  # pointing down
        0,                                  # covariance
    )


import subprocess
wifi_blocked = False
armed = False
last_armed = 0.0

def set_wifi(block):
    global wifi_blocked
    if block == wifi_blocked:
        return
    try:
        subprocess.run(["rfkill", "block" if block else "unblock", "wifi"], check=True)
        wifi_blocked = block
        print(f"[wifi] {'OFF (armed)' if block else 'ON (disarmed)'}")
    except Exception as e:
        print(f"[wifi] could not change Wi-Fi: {e}")


rc_pwm = 0                 # last value of the shutdown channel
sw_seen_low = False        # switch must be seen OFF once after boot before it can trigger
sw_high_since = None


def request_rc_stream():
    """Ask the autopilot to send RC_CHANNELS (msg id 65) at 2 Hz."""
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
        65, 500000, 0, 0, 0, 0, 0)


def play_tune(tune):
    try:
        master.mav.play_tune_send(master.target_system, master.target_component,
                                  tune.encode(), b"")
    except Exception:
        pass


def poll_armed():
    """Read waiting messages from the autopilot: armed state and the shutdown switch."""
    global armed, last_armed, rc_pwm
    while True:
        m = master.recv_match(type=["HEARTBEAT", "RC_CHANNELS"], blocking=False)
        if m is None:
            break
        if m.get_type() == "RC_CHANNELS":
            if args.shutdown_channel:
                rc_pwm = getattr(m, f"chan{args.shutdown_channel}_raw", 0)
            continue
        if m.get_srcComponent() != 1 or m.type == mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER:
            continue
        armed = bool(m.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        if armed:
            last_armed = time.time()


def check_shutdown_switch(now):
    """Shut the Pi down if the switch is ON for 3 s while disarmed."""
    global sw_seen_low, sw_high_since
    if not args.shutdown_channel or rc_pwm == 0:
        return
    if rc_pwm < 1300:
        if not sw_seen_low:
            print(f"[sw] shutdown switch ready (ch{args.shutdown_channel}={rc_pwm})")
        sw_seen_low = True
        sw_high_since = None
        return
    if rc_pwm > 1700 and sw_seen_low and not armed:
        if sw_high_since is None:
            sw_high_since = now
            print("[sw] shutdown switch ON, hold 3 s ...")
        elif now - sw_high_since >= 3.0:
            print("[sw] shutting down the Pi")
            play_tune("MFT240L8 O5 C E G >C")
            time.sleep(1.0)
            subprocess.run(["shutdown", "now"])
            sys.exit(0)
    else:
        sw_high_since = None


def send_heartbeat():
    master.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                              mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)


# ----------------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------------
running = True
def _stop(*_):
    global running
    running = False
signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

cam = Camera(args.width, args.height, args.usb_camera)
K, DIST, calibrated = load_intrinsics(args.width, args.height)
fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]

period = 1.0 / args.rate
last_send = last_hb = last_print = last_dbg = 0.0
frames = hits = 0
t0 = time.time()

print("[run] running. Ctrl+C to stop.")
while running:
    frame = cam.read()
    if frame is None:
        continue
    frames += 1
    if args.rotate180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detect(gray)

    now = time.time()
    if master and now - last_hb > 1.0:
        send_heartbeat()
        last_hb = now
        poll_armed()   # also drains incoming data from the Pixhawk
        check_shutdown_switch(now)
        if args.wifi_off_when_armed:
            if armed:
                set_wifi(True)
            elif wifi_blocked and now - last_armed > 10:
                set_wifi(False)

    found = False
    if ids is not None:
        for c, i in zip(corners, ids.flatten()):
            if i != args.marker_id:
                continue
            found = True
            hits += 1
            pts = c.reshape(4, 2).astype(np.float64)

            # undistort the centre point, then convert pixel offset to angles
            if calibrated:
                und = cv2.undistortPoints(pts.reshape(-1, 1, 2), K, DIST, P=K).reshape(4, 2)
            else:
                und = pts
            u, v = und.mean(axis=0)
            ax = math.atan((u - cx) / fx)   # + = target to the RIGHT
            ay = math.atan((v - cy) / fy)   # + = target BEHIND (image down)
            if args.flip_x:
                ax = -ax
            if args.flip_y:
                ay = -ay

            # angular size of the marker
            w_px = np.linalg.norm(und[0] - und[1])
            h_px = np.linalg.norm(und[1] - und[2])
            sx = 2 * math.atan((w_px / 2) / fx)
            sy = 2 * math.atan((h_px / 2) / fy)

            # distance from pose
            dist_m = 0.0
            ok, rvec, tvec = cv2.solvePnP(OBJ_PTS, pts, K, DIST, flags=cv2.SOLVEPNP_IPPE_SQUARE)
            if ok:
                dist_m = float(np.linalg.norm(tvec))

            if master and now - last_send >= period:
                send_landing_target(ax, ay, dist_m, sx, sy)
                if args.rangefinder and dist_m > 0:
                    send_distance(dist_m)
                last_send = now

            if now - last_print > 0.5:
                side = "right" if ax > 0 else "left"
                fb = "behind" if ay > 0 else "ahead"
                print(f"[tgt] x={math.degrees(ax):+6.1f} deg ({side})  "
                      f"y={math.degrees(ay):+6.1f} deg ({fb})  dist={dist_m:5.2f} m")
                last_print = now

            if args.save_debug and now - last_dbg > 2.0:
                dbg = frame.copy()
                aruco.drawDetectedMarkers(dbg, [c], np.array([[i]]))
                cv2.circle(dbg, (int(cx), int(cy)), 6, (0, 0, 255), 2)
                cv2.imwrite("debug.jpg", dbg)
                last_dbg = now
            break

    if not found and now - last_print > 2.0:
        fps = frames / (now - t0)
        print(f"[run] no marker. {fps:.1f} fps, {hits} detections so far")
        last_print = now

cam.close()
if args.wifi_off_when_armed and wifi_blocked:
    set_wifi(False)
print("[run] stopped")
