# Anchors: how to pick them, and how wrong the answer is

`geometry.md` §10 solves the camera position when you have ≥4 points **with elevations** and `pose.py` is available. This file is for the commoner, nastier situation: **2–3 anchors, no heights, no redundancy** — a beach, a promenade, a row of hotels along a shore. There is no residual to lean on and nothing to cross-check, so every rule below is about not fooling yourself.

The one-line version: **an anchor you have not identified is worse than no anchor**, because it produces a confident, self-consistent, wrong answer.

## 0. The most expensive mistake: assuming what a structure is

Real case (run19, Yantai). The frame had one tall thin column against the sky on the right. It *looked* like a landmark tower. The city has a famous 50 m white scenic tower, so: "6.3° tall ⇒ 50 m tower at 450 m" — a clean number, three other angles closed on it, and the card shipped. It was a **street lamp**: 8 m tall, 43 m away.

What should have caught it:

- **Aspect ratio.** The column was 257 px tall and 13 px wide — 1:20. A lamp post, a chimney and a landmark tower all read as "thin", but a 50 m scenic tower with a 30 m circular shell cannot silhouette as 1:20 from any angle.
- **Implied height vs. common sense.** Convert the angular height to metres at the assumed distance and ask what the object *is*: lamp 6–10 m, storey 2.8–3 m, hotel storey 3.2–3.6 m, residential tower 50–100 m, industrial chimney 80–240 m. If the number lands 2× outside every category, the anchor is wrong, not the world.
- **The name search is the trap.** Searching "<place> landmark tower" always returns *something*, and that something will be a real tower in the right city. That is confirmation, not evidence: it proves the tower exists, not that it is in your frame.

**Rule.** Before an object becomes an anchor, name a class it belongs to and check that its angle-derived size fits that class at a plausible distance. If the class is uncertain, it is not an anchor — it is a shape.

## 1. An anchor must be findable on the map *uniquely*, and pointed at by the photo *uniquely*

Two failure modes, both silent:

- **Same-name POIs.** Asked for a "瞭望台" (watchtower), a keyword search returned "金沙滩海滨公园-观景台" 3 km west — a different POI with a near-identical name. Using it moved the camera 2.6 km and still produced a tight residual. **Take the coordinate from an identifier, not a name**: an AMap share link resolves to a POI id (`surl.amap.com/xxxx` → `p=B0FFG233M2,<lat>,<lon>,<name>`), which is unambiguous. Keyword search is for finding candidates, never for picking one.
- **The user's mark vs. the user's coordinate.** When someone draws a line on the photo and separately gives you a coordinate, the line is *their* reading of which building it is and the coordinate is a fact. Solve with the coordinate; if the two disagree, the line is what's wrong — say so instead of silently averaging.

Also: a low-rise hotel 5 km out and a lamp post 40 m out can sit within 10 px of each other. Always confirm *which* pixel column belongs to *which* object before solving.

## 2. Bearing-only solve with 2–3 anchors

No elevations, no FOV: solve `lat, lon, heading` and the pixel scale together. Three unknowns, three anchors given as "this object is at pixel x".

```python
# for each candidate (lat, lon):
#   bearings b_i to the anchors, then  bs_i = wrap(b_i - b_0)
#   pixel offsets xs_i = x_i - W/2
#   closed-form scale: s = (xs · bs) / (xs · xs)      # deg per px
#   residual:          R = |bs - s*xs|²
# grid-search (lat, lon) at 1e-4 deg, keep the minimum R; heading = b_0 - xs_0*s
```

- The scale is **derived, not assumed** — do not preset FOV and then fit positions. In run19 the solve returned 0.0415 deg/px = 53° horizontal, i.e. a phone main camera cropped to 16:9, which independently explained why the sun disc measured only 13 px. A preset 40° had produced a 1.6 km position error.
- Only anchors 1 and 2 are independent equations; the third is a check. **Look at the per-anchor prediction error**, not just the total: run19 predicted x = 640.0 / 735.6 / 905.2 against observed 642 / 736 / 905 — a 2 px miss on one anchor and 0.4 px on the others is the signature of a correct solve.
- Beware the degenerate "anchor 1 defines heading" branch: moving anchor 1 alone barely moves the camera (it just rotates the frame). Sensitivity that looks like zero is a hint you are fitting heading, not position.

## 3. Collinearity: 3 anchors in a narrow fan cannot fix distance

Three anchors that all lie along nearly the same sight line are, geometrically, one anchor repeated.

run19: bearings 84.3° / 88.2° / 95.3° — a **11° fan**. Result: σ ≈ 125 m along the line of sight, σ ≈ 45 m across it. The answer is "a point on this stretch of beach", not "this square metre".

| azimuth spread of the anchors | typical along-sight σ (3 anchors, ±8 px, ±30 m POI) |
|---|---|
| 10–15° | 120–150 m |
| 30° | 60–80 m |
| 60°+ | 25–40 m |

- **Always report the anisotropy**, not a single ±R: "±150 m along the beach / ±45 m across it" is honest and useful; "±60 m" is neither. A radial figure invites the reader to walk to a spot that the geometry never supported.
- If a sideways anchor exists — anything 30°+ off the current fan, even outside the frame — its position alone will do more for the answer than a fourth anchor inside the fan.

## 4. Run the error budget; don't estimate it

Two numbers, both cheap (a few seconds of compute), both of which changed the conclusion in run19:

**Single-factor sensitivity** — nudge one input, re-solve, measure how far the camera moves:

| perturbation | camera displacement |
|---|---|
| pixel x of anchor at 5.9 km, +5 px | ≈ 0 m (it only rotates the frame) |
| pixel x of anchor at 1.2 km, +5 px | 268 m |
| pixel x of anchor at 0.12 km, +5 px | 186 m |
| nearest anchor's coordinate, +30 m east | 63 m |
| nearest anchor's coordinate, +30 m north | 69 m |

The lesson is not the numbers — it is that **the nearest anchor dominates**, because a 30 m coordinate error at 120 m is a 14° error. Cheap anchors near the camera are seductive and dangerous: verify them first, and prefer anchors 1–3 km out if you can identify them.

**Monte-Carlo** — perturb all inputs at their real uncertainty, re-solve 150+ times, report quantiles:

- pixel σ from how the anchors were marked: hand-drawn line ±4–6 px, an arrow tip ±10 px, a clicked point ±3 px.
- POI σ: 20 m for a surveyed building footprint, 30–50 m for a hotel/attraction POI (they are often placed at the gate).
- Report 68% and 95% radial, plus the two axis σ. Do not report the solver's residual as the error — a low residual means "consistent", not "accurate" (the wrong-POI solve in §1 had rms 0.06°).

## 5. Before quoting anything

- Does the implied height of *every* anchor fit a real object class? (§0)
- Is every anchor's coordinate from an identifier rather than a name? (§1)
- Is the azimuth fan wide enough for the radius you are about to quote? (§3)
- Did you re-solve under perturbation, or are you guessing the radius? (§4)
- Sanity check the FOV the solve produced: 50–60° is a phone main camera at 16:9, 70–80° is 1× full-frame, 25–35° is a 2–3× crop. A derived FOV outside these bands usually means one anchor is misidentified.

## 6. Delivery checks that this run got wrong first

- **Satellite and road base must share zoom, centre and sector radius.** A z17 road base (1.2 km) paired with a z15 satellite (4.8 km) cannot be compared — two anchors fell outside the road image and the reader has no way to line them up. Use the same `--center`/`--zoom`/sector for both.
- **Crop boundaries are computed from anchor pixel positions, not chosen by eye.** Cropping "the empty sea" cut the camera marker itself out of the road base once; compute the crop from `y(camera) - margin`.
- **Labels collide when two anchors are close.** The camera and a watchtower 120 m away are 16 px apart at z15; offset one label below-left and the other above-right, or number them and use a legend.
- **Never ship the user's own annotated image.** Redraw with your own marker style (numbered disc + short leader, details in a legend box); the user's marks are input, not artwork.
