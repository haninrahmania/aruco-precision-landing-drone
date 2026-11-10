#!/usr/bin/env python3
"""
Makes printable files:
  landing_marker.png : ArUco DICT_4X4_50 id 0, sized to print at 20 cm on A4/A3
  checkerboard.png   : 10x7 squares (9x6 inner corners), 25 mm squares on A4
Print at 100% / "actual size" (not "fit to page"), then MEASURE the black square
and pass the real size to precland.py with --marker-size.
"""
import cv2
import numpy as np

DPI = 300
mm = lambda x: int(round(x / 25.4 * DPI))

# ArUco marker: 200 mm black square + white border on A4 (210 x 297 mm)
aruco = cv2.aruco
d = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
side = mm(200)
gen = aruco.generateImageMarker if hasattr(aruco, "generateImageMarker") else aruco.drawMarker
marker = gen(d, 0, side)
page = np.full((mm(297), mm(210)), 255, np.uint8)
y0, x0 = (page.shape[0] - side) // 2, (page.shape[1] - side) // 2
page[y0:y0 + side, x0:x0 + side] = marker
cv2.putText(page, "ArUco 4x4_50 id 0 - black square = 200 mm", (mm(15), mm(20)),
            cv2.FONT_HERSHEY_SIMPLEX, 2.2, 0, 4)
cv2.imwrite("landing_marker.png", page)

# Checkerboard 10 x 7 squares, 25 mm each
sq = mm(25)
board = np.full((mm(210), mm(297)), 255, np.uint8)   # A4 landscape
bw, bh = 10 * sq, 7 * sq  # 10 across, 7 down -> 9x6 inner corners
oy, ox = (board.shape[0] - bh) // 2, (board.shape[1] - bw) // 2
for r in range(7):
    for c in range(10):
        if (r + c) % 2 == 0:
            board[oy + r * sq: oy + (r + 1) * sq, ox + c * sq: ox + (c + 1) * sq] = 0
cv2.imwrite("checkerboard.png", board)
print("wrote landing_marker.png and checkerboard.png (print at 100%, 300 dpi)")
