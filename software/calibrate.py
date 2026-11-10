#!/usr/bin/env python3
"""
Camera calibration with a printed checkerboard.

1. Print checkerboard.png (made by make_markers.py) on A4, glue it flat on card.
2. Run:  python3 calibrate.py
3. Hold the board in front of the camera at different angles and distances.
   The script grabs a frame every ~1.5 s when it sees the board (aim for 20+).
4. Press Ctrl+C when done. It writes camera_calib.npz.
"""
import sys
import time

import cv2
import numpy as np

COLS, ROWS = 9, 6          # inner corners of the checkerboard
SQUARE = 0.025             # square size in metres (25 mm when printed at 100%)
W, H = 640, 480

objp = np.zeros((ROWS * COLS, 3), np.float32)
objp[:, :2] = np.mgrid[0:COLS, 0:ROWS].T.reshape(-1, 2) * SQUARE

try:
    from picamera2 import Picamera2
    cam = Picamera2()
    cam.configure(cam.create_video_configuration(main={"size": (W, H), "format": "RGB888"}))
    cam.start(); time.sleep(1)
    grab = cam.capture_array
except Exception:
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    grab = lambda: cap.read()[1]

objpoints, imgpoints = [], []
last = 0
print("Show the checkerboard to the camera. Ctrl+C when you have 20+ captures.")
try:
    while True:
        frame = grab()
        if frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        ok, corners = cv2.findChessboardCorners(gray, (COLS, ROWS), None)
        if ok and time.time() - last > 1.5:
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
                                       (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
            objpoints.append(objp); imgpoints.append(corners)
            last = time.time()
            print(f"captured {len(objpoints)}")
except KeyboardInterrupt:
    pass

if len(objpoints) < 10:
    sys.exit("Need at least 10 captures. Try again.")

rms, K, dist, _, _ = cv2.calibrateCamera(objpoints, imgpoints, (W, H), None, None)
np.savez("camera_calib.npz", K=K, dist=dist, size=np.array([W, H]))
print(f"Saved camera_calib.npz  (RMS reprojection error {rms:.3f} px; under 0.5 is good, under 1.0 is OK)")
print(K)
