"""Render a telemetry side panel (mode, marker lock, offset, altitude, messages) synced to a flight video.

Usage:
  python3 parse_log.py flight.bin                      # writes log.json
  python3 render_log_panel.py --start 2026-11-10T06:36:24+07:00 --duration 54.26
  ffmpeg -i video.mov -i panel.mp4 -filter_complex "[0:v]scale=720:1280[a];[a][1:v]hstack" -map 0:a? out.mp4

--start is the wall-clock time of the first video frame (phone video metadata: creation date).
Check the sync against a clear event, e.g. touchdown or the disarm sound, and adjust with --offset.
"""
import json, datetime, bisect, subprocess, sys, argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

# ---------- data ----------
ap = argparse.ArgumentParser()
ap.add_argument("--log-json", default="log.json")
ap.add_argument("--start", required=True, help="ISO time of the first video frame, with timezone")
ap.add_argument("--duration", type=float, required=True, help="video length in seconds")
ap.add_argument("--offset", type=float, default=0.0, help="shift log vs video in seconds")
ap.add_argument("--out", default="panel.mp4")
args = ap.parse_args()
D = json.load(open(args.log_json))
_st = datetime.datetime.fromisoformat(args.start)
TZ = _st.tzinfo
T0 = _st.timestamp() + args.offset
DUR = args.duration
FPS = 30
NFR = int(DUR * FPS)

def series(name, keys):
    rows = D[name]
    t = np.array([r["_ts"] - T0 for r in rows])
    return t, {k: np.array([r[k] for r in rows]) for k in keys}

tC, C = series("CTUN", ["Alt", "DAlt"])
tP, P = series("PL", ["TAcq", "pX", "pY", "LastMeasMS"])
tB, B = series("BAT", ["Volt", "Curr"])
tA, A = series("ATT", ["Roll", "Pitch"])

MODES = {0: "STABILIZE", 5: "LOITER", 9: "LAND"}
MCOL = {0: "#9aa4b1", 5: "#4ea1ff", 9: "#ffa24c"}
modes = [(r["_ts"] - T0, r["ModeNum"]) for r in D["MODE"]]
arms = [(r["_ts"] - T0, r["ArmState"]) for r in D["ARM"]]
msgs = [(r["_ts"] - T0, r["Message"]) for r in D["MSG"] if "PrecLand" in r["Message"]]
msgs = [m for m in msgs if -5 < m[0] < DUR + 2]

def last(events, t, default):
    v = default
    for et, ev in events:
        if et <= t: v = ev
        else: break
    return v

def at(tarr, arr, t):
    i = bisect.bisect_right(tarr, t) - 1
    return arr[max(i, 0)]

# precland lock segments
lockmask = P["TAcq"] == 1

# ---------- style ----------
BG = "#0f1216"; FG = "#e8ecf1"; MUTED = "#8a94a3"; GRID = "#262c35"; GREEN = "#43d17a"
fm.fontManager.addfont("/usr/share/fonts/opentype/inter/Inter-Regular.otf")
for f in ["Inter-Medium.otf", "Inter-SemiBold.otf", "Inter-Bold.otf"]:
    try: fm.fontManager.addfont("/usr/share/fonts/opentype/inter/" + f)
    except Exception: pass
plt.rcParams.update({"font.family": "Inter", "text.color": FG, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": GRID})

W, H = 720, 1280
fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=BG)

def T(x, y, s, **kw):
    return fig.text(x / W, 1 - y / H, s, **kw)

# header
T(36, 52, "Precision landing test", fontsize=22, weight="bold")
T(36, 84, "ArUco marker · Raspberry Pi 4 → Pixhawk (ArduCopter 4.7.2)", fontsize=11.5, color=MUTED)
T(36, 106, f"{_st:%d %b %Y} · flight log synced to video", fontsize=11.5, color=MUTED)
clock = T(36, 150, "", fontsize=15, family="DejaVu Sans Mono", color=FG)

# status tiles
def tile_label(x, y, s): T(x, y, s, fontsize=10, color=MUTED, weight="medium")
tile_label(36, 196, "FLIGHT MODE"); tile_label(270, 196, "MOTORS"); tile_label(470, 196, "MARKER")
mode_t = T(36, 232, "", fontsize=24, weight="bold")
arm_t = T(270, 232, "", fontsize=24, weight="bold")
pl_t = T(470, 232, "", fontsize=24, weight="bold")

# target view
axT = fig.add_axes([36 / W, 1 - 655 / H, 360 / W, 360 / H], facecolor=BG)
T(36, 250 + 20, "", fontsize=1)
tv_title = T(36, 280, "Marker position relative to drone (EKF estimate)", fontsize=11, color=MUTED)
R = 60
for rr in (10, 25, 50):
    axT.add_patch(plt.Circle((0, 0), rr, fill=False, color=GRID, lw=1))
    axT.text(rr * 0.707 + 1, rr * 0.707 + 1, f"{rr} cm", fontsize=8.5, color=MUTED)
axT.axhline(0, color=GRID, lw=0.8); axT.axvline(0, color=GRID, lw=0.8)
axT.set_xlim(-R, R); axT.set_ylim(-R, R); axT.set_aspect("equal")
axT.set_xticks([]); axT.set_yticks([])
for s in axT.spines.values(): s.set_color(GRID)
axT.text(0, R - 6, "N", ha="center", fontsize=9, color=MUTED)
axT.text(R - 6, 0, "E", va="center", fontsize=9, color=MUTED)
axT.plot([0], [0], marker="+", ms=18, mew=2, color=FG)  # drone
trail, = axT.plot([], [], color=GREEN, lw=1.5, alpha=0.45)
dot, = axT.plot([], [], "s", ms=13, color=GREEN, mec="white", mew=1)
nolock = axT.text(0, -R + 10, "", ha="center", fontsize=11, color=MUTED)

# numbers beside target view
T(440, 330, "HORIZONTAL OFFSET", fontsize=10, color=MUTED, weight="medium")
off_t = T(440, 372, "", fontsize=30, weight="bold")
T(440, 430, "ALTITUDE", fontsize=10, color=MUTED, weight="medium")
alt_t = T(440, 472, "", fontsize=30, weight="bold")
T(440, 530, "BATTERY", fontsize=10, color=MUTED, weight="medium")
bat_t = T(440, 566, "", fontsize=20, weight="bold")
T(440, 608, "TILT", fontsize=10, color=MUTED, weight="medium")
tilt_t = T(440, 640, "", fontsize=16, weight="bold")

# altitude timeline
axA = fig.add_axes([86 / W, 1 - 960 / H, 600 / W, 250 / H], facecolor=BG)
T(36, 690, "Altitude (m) and flight mode over the whole flight", fontsize=11, color=MUTED)
mt = [m for m in modes]
edges = [(t, n) for t, n in mt]
for i, (t, n) in enumerate(edges):
    t2 = edges[i + 1][0] if i + 1 < len(edges) else DUR + 5
    lo, hi = max(t, -2), min(t2, DUR)
    if hi > lo:
        axA.axvspan(lo, hi, color=MCOL.get(n, MUTED), alpha=0.10, lw=0)
        if hi - lo > 6:
            axA.text((lo + hi) / 2, 2.62, MODES.get(n, str(n)), ha="center", fontsize=9, color=MCOL.get(n, MUTED))
# lock band
lk = tP[lockmask]
if len(lk):
    axA.axvspan(lk.min(), lk.max(), ymin=0, ymax=0.04, color=GREEN, lw=0)
    axA.text((lk.min() + lk.max()) / 2, 0.16, "marker locked", ha="center", fontsize=8.5, color=GREEN)
m = (tC > -2) & (tC < DUR)
axA.plot(tC[m], C["Alt"][m], color=FG, lw=1.8)
axA.set_xlim(-1, DUR); axA.set_ylim(-0.4, 2.9)
axA.grid(color=GRID, lw=0.6); axA.tick_params(labelsize=9)
axA.set_xlabel("video time (s)", fontsize=9)
cursor = axA.axvline(0, color="white", lw=1.2)
cdot, = axA.plot([], [], "o", color="white", ms=6)

# event log
T(36, 1030, "Precision landing messages", fontsize=11, color=MUTED)
log_lines = [T(36, 1066 + i * 28, "", fontsize=12.5, family="DejaVu Sans Mono") for i in range(6)]
T(36, 1250, "Data: Pixhawk DataFlash log (CTUN, PL, MODE, MSG, BAT). Offset = PL.pX/pY.", fontsize=8.5, color=MUTED)

def mcolor(s):
    if "Complete" in s or "Found" in s: return GREEN
    if "Failed" in s or "Lost" in s: return "#ff6b6b"
    return FG

proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                         "-pix_fmt", "yuv420p", "-crf", "18", args.out], stdin=subprocess.PIPE)

for f in range(NFR):
    t = f / FPS
    wall = datetime.datetime.fromtimestamp(T0 + t, TZ)
    clock.set_text(f"T+{t:05.1f}s   {wall:%H:%M:%S}")
    mn = last(modes, t, 0)
    mode_t.set_text(MODES.get(mn, str(mn))); mode_t.set_color(MCOL.get(mn, FG))
    armed = last(arms, t, 0)
    arm_t.set_text("ARMED" if armed else "DISARMED"); arm_t.set_color("#ff6b6b" if armed else MUTED)

    acq = at(tP, P["TAcq"], t)
    lm = at(tP, P["LastMeasMS"], t)
    i = bisect.bisect_right(tP, t) - 1
    # seeing marker = measurement updated within last 0.5 s
    fresh = False
    if i > 5:
        j = bisect.bisect_right(tP, t - 0.5) - 1
        fresh = P["LastMeasMS"][i] != P["LastMeasMS"][max(j, 0)]
    if acq == 1:
        pl_t.set_text("LOCKED"); pl_t.set_color(GREEN)
    elif fresh:
        pl_t.set_text("SEEN"); pl_t.set_color("#ffd166")
    else:
        pl_t.set_text("—"); pl_t.set_color(MUTED)

    # target view (N = pX, E = pY), cm
    if acq == 1:
        j0 = max(0, bisect.bisect_right(tP, t - 3.0))
        sl = slice(j0, i + 1)
        ok = lockmask[sl]
        xs = (P["pY"][sl][ok]) * 100; ys = (P["pX"][sl][ok]) * 100
        trail.set_data(xs, ys)
        dot.set_data([P["pY"][i] * 100], [P["pX"][i] * 100])
        d = np.hypot(P["pX"][i], P["pY"][i]) * 100
        off_t.set_text(f"{d:4.0f} cm"); off_t.set_color(GREEN)
        nolock.set_text("")
    else:
        trail.set_data([], []); dot.set_data([], [])
        off_t.set_text("—"); off_t.set_color(MUTED)
        nolock.set_text("marker seen, lock not yet confirmed" if fresh else "no marker lock")

    alt = at(tC, C["Alt"], t)
    alt_t.set_text(f"{max(alt,0):.2f} m")
    v = at(tB, B["Volt"], t); c = at(tB, B["Curr"], t)
    bat_t.set_text(f"{v:.1f} V · {c:.0f} A")
    r = at(tA, A["Roll"], t); p = at(tA, A["Pitch"], t)
    tilt_t.set_text(f"roll {r:+.0f}°  pitch {p:+.0f}°")

    cursor.set_xdata([t, t]); cdot.set_data([t], [alt])

    shown = [mm for mm in msgs if mm[0] <= t][-6:]
    for k, ln in enumerate(log_lines):
        if k < len(shown):
            mt_, s = shown[k]
            ln.set_text(f"{mt_:5.1f}s  {s.replace('PrecLand: ','')}"); ln.set_color(mcolor(s))
        else:
            ln.set_text("")

    fig.canvas.draw()
    proc.stdin.write(fig.canvas.buffer_rgba().tobytes())
    if f % 300 == 0: print(f, flush=True)

proc.stdin.close(); proc.wait()
print("done")
