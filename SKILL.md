---
name: smooth-animation
description: Use when a video or animation made in code (HyperFrames, Remotion, canvas, three.js) looks choppy, stuttery, jittery or not smooth, when a scene sits still, when rain or spokes flicker or spin backwards, when someone asks to fill in frames, interpolate (RIFE, minterpolate, anime.js) or go to 60 fps, or before delivering an animation where smoothness was requested.
---

# Smooth animation

When a frame is a pure function of time, the in-between frames are **actually drawn**, not guessed. Choppy output is rarely a lack of frames: it is almost always irregular motion or low sampling. So the order is: measure, fix the motion, and only then raise the frame rate.

Out of scope: footage that is already recorded, without the code that generated it. There, interpolating with RIFE or similar does make sense.

## Recipe

**1. Measure the current file and keep the result** (with ffmpeg on the PATH; adjust the path to where the skill is installed):
```bash
python .claude/skills/smooth-animation/scripts/measure_smoothness.py video.mp4
```

| Result | Cause | Fix |
|---|---|---|
| `repeated` FAIL | the render or encode lost frames | check the render `fps` and the capture; then the content |
| `still` FAIL | the scene is static | step 2 |
| `jitter` FAIL | irregular motion, usually a noisy camera | step 3 |
| all PASS, but it still looks choppy | low sampling (30 fps) or the player | steps 4 to 6 |

If the complaint persists with everything on PASS, try the file in an external player (VLC, mpv) before rendering again: high bitrate on fine line art makes players stutter.

**2. No still scenes.** Every shot has a camera moving at a speed that never reaches zero and at least one material in motion (sea, sky, rain, hair). Scene changes overlap, with both scenes still moving during the transition.

**3. Camera on smooth curves only.** Replace frame-by-frame noise with a sum of low-frequency sines:
```js
const sway = (t, f, ph) => Math.sin(t * f + ph) * .6 + Math.sin(t * f * 1.73 + ph * 2.1) * .4;
const hx = sway(t, .55, 1.1) * 9 + sway(t, 3.1, .4) * shake * 1.1;   // f in rad/s: slow drift + 0.5 to 0.9 Hz sway
```
A strong shake means more amplitude, never more frequency. These values come from the demo film, tested with `shake` from 2 to 4.

**4. Render at a real 60 fps.** It is the default, not the last resort. Measure the cost on a stretch (`hyperframes render . --start 19 --end 22 --fps 60`; in Remotion, the composition's `fps` and `--frames=a-b`) and deliver at 60. If that misses the deadline, cut back in this order: blur only on fast scenes, then 2 samples. Keep the 60 fps.

**5. Motion blur from samples.** Start with 3 samples in a 180° shutter and go higher only if there is still strobing. The function that draws the frame receives `t` and calls the scene several times: in HyperFrames, inside the `hf-seek` handler; in Remotion, with `frame / fps + offset`. Average **before** any step that hardens edges:
```js
const SAMPLES = 3, SHUTTER = .5 / 60;
for (let s = 0; s < SAMPLES; s++) {
  composeSample(t + (s / SAMPLES) * SHUTTER);          // draws the scene at that instant
  acc.globalAlpha = 1 / (s + 1); acc.drawImage(sample, 0, 0);   // running average
}
acc.globalAlpha = 1;                                   // captions go on afterwards, sharp
```
A threshold, posterization or "print" step after the average erases the blur. Soften the threshold or average after that step. In your own shader: `smoothstep(.5 - w, .5 + w, m)` with `w` near .4 (the edge stays sharp, because only the averaged pixels land in the middle). `step()` or a small `w` erases the blur.

**Filters too slow to run per sample** (a stroke tracer, a stylizer over a 3D render, anything taking seconds per image): don't quantize the look to its own rate, because every recut becomes a jump in the motion. Keep the filter at a low rate (12 per second worked), cache each result as a layer, and draw every frame as a blend of the two nearest results, with the camera moving on top of them:
```js
const f = t * CUT_FPS, i = Math.floor(f), a = f - i;                // CUT_FPS = 12
const A = cut(key, i / CUT_FPS), B = cut(key, (i + 1) / CUT_FPS);    // cached layers, small LRU
g.globalCompositeOperation = 'lighter';
g.globalAlpha = 1 - a; g.drawImage(A, 0, 0);
g.globalAlpha = a;     g.drawImage(B, 0, 0);
```
The blend costs about the same as drawing one layer, so the filter still runs only at its own rate. Expect a slightly softer, greyer image while a blend is halfway. Text-only cards also need something moving: a slow camera alone can still read as `still`, so add drifting specks or similar.

**6. Fast elements.** Avoid the wagon-wheel effect:
- Repeating patterns (spokes, fences): at most 40% of the spacing per frame. With 48 spokes the spacing is 7.5°, so up to 3° per frame, or 180°/s at 60 fps. Above that, slow it down and say so, or raise samples and shutter until it blends into a disc.
- Streaks (rain): longer than the distance travelled per frame.

**7. Prove it on the final file.** Run the meter again on the delivered file, after the encode, and report the before and after numbers. Say what the number does not prove: how it feels to the viewer, and stretches that are busy on purpose (see `busiest`).

## How to read the numbers
`jump` compares the amount of motion from one frame to the next. Measured in tests: smooth videos stay between 0.003 and 0.04, and videos with camera jitter between 0.27 and 0.6; the limit is 0.1. `still` reports at least 0.5 s with a mean difference below 0.15 (scale 0 to 255); a small element moving on a still background can pass, so look at the scenes too. Compare the same scene before and after. `motion` changes with the content, so fine lines advancing fast give a high number without being a defect.

## Common mistakes
- Blaming missing frames without measuring.
- Pixel-interpolating a video generated in code: it creates ghosts on fine lines, and the code can draw the right frame.
- Using anime.js for smoothness: it animates properties, it does not create video frames. It only works as a swap of the animation engine, with `autoplay: false` and `seek` per frame.
- Starting with 8 to 16 samples: 3 were enough on fine line art at 60 fps, and the cost goes up for nothing.
- Judging playback from a draft-quality render: its bitrate and profile differ from the final's.
