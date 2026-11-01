#!/usr/bin/env python3
"""Measures how smooth a video is from the difference between consecutive frames. Standard library + ffmpeg on the PATH.

Separates the three causes of "choppy", which need different fixes:
  REPEATED  frames identical to the previous one: the render or the encode lost frames
  STILL     a stretch with no motion: the scene itself is static
  JITTER    the amount of motion swings from one frame to the next: irregular motion (noisy camera)

Usage:
  python measure_smoothness.py video.mp4
  python measure_smoothness.py video.mp4 --json
Exits with code 1 if it finds a defect.
"""
import argparse, json, re, subprocess, sys

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("video")
ap.add_argument("--still", type=float, default=.15, help="mean difference below this counts as a frame with no motion (0..255)")
ap.add_argument("--repeated", type=float, default=.03, help="mean difference below this counts as a repeated frame")
ap.add_argument("--min-still", type=float, default=.5, help="consecutive seconds with no motion before a stretch is reported as still")
ap.add_argument("--jitter", type=float, default=.1, help="relative jump above this, per second, counts as jitter")
ap.add_argument("--json", action="store_true")
a = ap.parse_args()

r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", a.video], capture_output=True, text=True, check=True)
n, d = r.stdout.strip().split("/")
fps = float(n) / float(d)
vf = "scale=640:-2,format=gray,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-"
r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", a.video, "-vf", vf, "-f", "null", "-"], capture_output=True, text=True, check=True)
v = [float(x) for x in re.findall(r"YAVG=([\d.]+)", r.stdout)]
if not v:
    sys.exit("could not measure: no frames read")

# stretches with no motion (up to 2 frames above the limit in the middle, caused by the encoder's keyframe, do not break a stretch)
# Alternating frames (half of them still) do not count: that is a repeated frame, not a still scene.
still, start, end, n = [], None, None, 0
for i, x in enumerate(v + [1e9] * 3):
    if x < a.still:
        if start is None: start, n = i, 0
        end, n = i, n + 1
    elif start is not None and i - end > 2:
        total = end + 1 - start
        if total / fps >= a.min_still and n / total >= .8: still.append([round(start / fps, 2), round((end + 1) / fps, 2)])
        start = None
in_still = lambda i: any(p[0] <= i / fps < p[1] for p in still)
rep = [i for i, x in enumerate(v) if x < a.repeated and not in_still(i)]

# relative jump per second: how much the amount of motion changes from one frame to the next.
# Repeated frames are left out (they have their own diagnosis). A scene cut is an isolated spike, hence the median.
per_second, jittery, step = [], [], max(1, round(fps))
for s in range(0, len(v), step):
    j = [x for x in v[s:s + step] if x >= a.repeated]
    if len(j) < 3: continue
    mean = sum(j) / len(j)
    dif = sorted(abs(j[k] - j[k - 1]) for k in range(1, len(j)))
    jump = dif[len(dif) // 2] / mean if mean > a.still else 0
    per_second.append({"s": s // step, "motion": round(mean, 2), "jump": round(jump, 3)})
    if jump > a.jitter and not any(p[0] < s // step + 1 and p[1] > s // step for p in still): jittery.append(s // step)

out = {"fps": round(fps, 3), "frames": len(v) + 1, "mean_motion": round(sum(v) / len(v), 2), "repeated": len(rep),
       "repeated_pct": round(100 * len(rep) / len(v), 1), "still": still, "jittery_seconds": jittery, "per_second": per_second}
if a.json:
    print(json.dumps(out, ensure_ascii=False))
else:
    print(f"{a.video}: {fps:g} fps, {len(v) + 1} frames, mean motion {out['mean_motion']}")
    print(("FAIL" if rep else "PASS"), f"repeated  {len(rep)} frames ({out['repeated_pct']}%)")
    print(("FAIL" if still else "PASS"), "still    ", still or "no stretch")
    print(("FAIL" if jittery else "PASS"), "jitter   ", (f"{len(jittery)} s of {len(per_second)}: {jittery[:20]}") if jittery else "no second")
    worst = sorted(per_second, key=lambda x: -x["motion"])[:3]
    print("busiest:", ", ".join(f"{p['s']}s ({p['motion']})" for p in worst))
sys.exit(1 if rep or still or jittery else 0)
