# Flight log → video panel

Makes the telemetry side panel used in the demo video: flight mode, marker lock, the EKF's estimate of where the marker is, altitude, battery and precision-landing messages, synced to a phone video.

```bash
pip install pymavlink matplotlib numpy     # plus ffmpeg
python3 parse_log.py 2026-11-10_06-33-58.bin          # → log.json
python3 render_log_panel.py --start 2026-11-10T06:36:24+07:00 --duration 54.26   # → panel.mp4
ffmpeg -i IMG_3264.mov -i panel.mp4 \
  -filter_complex "[0:v]scale=720:1280,setsar=1,fps=30[a];[1:v]setsar=1[b];[a][b]hstack" \
  -map 0:a:0 -c:a aac out.mp4
```

`--start` is the time the phone started recording (the video's creation date). To check the sync, compare a clear moment in both: touchdown, or the sound of the motors stopping, against the disarm event in the log. Use `--offset` to correct it.
