# Pi software setup

Wiring and Pixhawk parameters are in [`../hardware/README.md`](../hardware/README.md). Run these steps on the Raspberry Pi, from inside this `software` folder.

Files:
- `precland.py`: detects the ArUco marker and sends `LANDING_TARGET` (and optionally `DISTANCE_SENSOR`) to the Pixhawk.
- `calibrate.py`: camera calibration with the checkerboard. Writes `camera_calib.npz`.
- `make_markers.py`: regenerates the marker and checkerboard images in `../markers`.
- `install_service.sh`: makes `precland.py` start at every boot.

## 1. Pi setup (once)

```bash
sudo raspi-config   # Interface Options -> Serial Port
                    #   "login shell over serial?"      -> No
                    #   "serial port hardware enabled?" -> Yes
echo "dtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt   # use the full UART at 921600
sudo systemctl disable hciuart
sudo apt update && sudo apt install -y python3-opencv python3-picamera2 python3-pip
pip install --break-system-packages pymavlink
sudo reboot
```

On older Raspberry Pi OS the config file is `/boot/config.txt`. If `cv2.aruco` is missing, run `pip install --break-system-packages opencv-contrib-python`.

## 2. Camera mount

Lens pointing straight down. **Top edge of the image toward the front (red arms).** If you mount it differently, use `--rotate180`, `--flip-x` or `--flip-y` (see step 6).

## 3. Calibrate the camera

```bash
python3 calibrate.py      # move the printed checkerboard around, 20+ captures, then Ctrl+C
```

## 4. Bench test (PROPS OFF)

```bash
python3 precland.py --bench --save-debug
```

Hold the drone about 1 m above the marker and move the marker:
- Marker **to the right** of the drone should print `x = +` (right).
- Marker **in front of** the drone should print `y = -` (ahead).
- Marker **behind** should print `y = +` (behind).

If left/right is backwards, add `--flip-x`. If front/back is backwards, add `--flip-y`.

Then connect to the Pixhawk:

```bash
python3 precland.py
```

It should print `[mav] heartbeat from system 1`. Arm is not needed. Download the log afterwards: the **PL** messages should show **Heal = 1** while the marker was visible.

## 5. Start automatically at boot (no Wi-Fi needed in the field)

Once the bench test works (and you know whether you need `--flip-x` / `--flip-y`):

```bash
bash install_service.sh            # add your flip options here if you needed them, e.g. --flip-y
```

What happens from then on:
- Plug in the drone battery → the Pi boots (about 30 s) → precland starts by itself.
- **Wi-Fi switches OFF automatically when you arm**, and back ON 10 s after you disarm, so it can't interfere with the radio in flight but you can still SSH in on the ground.
- If it crashes or the Pixhawk isn't ready yet, it restarts by itself every 3 s.
- Everything it prints goes to `precland.log`, so you can check afterwards what it saw.

**Shutdown switch (recommended):** install with `--shutdown-channel 6` to use SwA:

```bash
bash install_service.sh --marker-size 0.15 --shutdown-channel 6
```

After landing and disarming, flip **SwA down and hold it for 3 s**. The Pixhawk buzzer plays a short tune and the Pi shuts down cleanly. Wait about 10 s, then unplug the battery. Flip SwA back up afterwards. Safety rules built in: it only works while **disarmed**, and SwA must have been seen **up** once after boot, so a switch left down won't shut the Pi down at startup.

**Wait about 40 s after plugging in the battery before arming**, so the Pi has finished booting.

To run it by hand again (e.g. `--bench`), stop the service first: `sudo systemctl stop precland`.

## 6. Flight test

1. Place the marker flat on open ground (weigh the corners down so it can't blow away).
2. Start `precland.py` on the Pi (over SSH, or set it to start at boot).
3. Take off in Stabilize, switch to **Loiter**, and move to about **2–3 m** above the marker.
4. Switch to **Land**. The drone should slide over the marker while descending.
5. If it goes the wrong way or wobbles hard, switch back to **Loiter or Stabilize** straight away.

Wait in Loiter until `PrecLand: Init Complete` appears (about 5 s over the marker) before switching to Land. ArduPilot keeps landing with GPS if the marker is lost (`PLND_STRICT = 0`), so it won't drop out of the sky.
