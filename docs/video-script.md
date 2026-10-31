# 3-minute demo video: script and shot list

Target 2:50, so there's slack. Screen recording of `streamlit run app.py`. Every number spoken
is from the README; don't round them up.

Dataset images (MVTec LOCO, CC BY-NC-SA 4.0) may appear in the video for this non-commercial
entry, with attribution on the end card. Don't commit screenshots of them to the repo.

## Before recording

- `.venv/bin/streamlit run app.py`, browser at 125% zoom, sidebar open.
- Warm the caches: open every image used below once in the app with the damage check and the
  baseline both on, so nothing waits on an API call while recording.
- Images, all from the held-out (odd) half. Check each in the app before recording; the
  baseline panel and the failed check must show what the voice-over says:
  - Screw Bag `test/logical_anomalies/029.png`: `screw_too_short`, the 3-ref + size-guide
    baseline passes it, Inspec fails it (also 039; `1_very_short_screw`: 101).
  - Breakfast Box `test/logical_anomalies/071.png`: `wrong_ratio`, caught by the part checks
    (also 073, 075; `underflow`: 049).
  - Breakfast Box `test/structural_anomalies/045.png`: `fruit_damaged`, missed (also 047, 049). Confirm the baseline flags the one you use.

## Script

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:15 | Screw Bag photo, full screen | "Kits like this ship with one long screw, one short screw, two nuts, two washers. A wrong-length screw looks almost right. Can a model check a kit from the packing list alone?" |
| 0:15–0:35 | Sidebar packing list, then section 1 (compiled JSON, expanded) | "Inspec takes the packing list as text. Muse Spark compiles it into a check program: the parts, the SAM concept for each, and count checks. No training, no labelled defects." |
| 0:35–1:05 | Section 2: calibration rounds (round 0, then the last), then "Measure checks added by calibration" | "The first program rejects every good kit: SAM ignores size words and calls washers nuts. So Inspec runs the program on known-good kits and Muse Spark repairs whatever fails. From 60 good kits it learns that nuts have smaller holes than washers and how long a long screw is. Every repair is checked in code before it's kept." |
| 1:05–1:35 | Section 3: the `screw_too_short` kit, mask overlay, failed length check; then the baseline panel saying PASS | "This kit has two short screws. Inspec fails it and shows why: no screw is in the long-screw range of 396 to 441 pixels. Muse Spark looking at the photo alone says the kit is fine." |
| 1:35–1:50 | README results table | "On the MVTec LOCO test set Inspec catches all 137 logical defects. The best vision-only baseline catches 130, and only after we gave it the size ratio Inspec measured. For damage, a vision model is the better judge, so Inspec asks it: measure what can be measured, ask the model about the rest." |
| 1:50–2:25 | Switch run to `bb4`; packing list changes; calibration; then a `wrong_ratio` kit failing the granola area check | "Same code, a different kit. SAM didn't know 'nectarine', so a concept-repair step had Muse Spark suggest other words and tried each on good kits: 'apple' works. Calibration learned how much granola a good box holds, so a box with too little fails on area. 78 of 83 logical defects caught, with no false alarms from the part checks." |
| 2:25–2:40 | The missed `fruit_damaged` kit, PASS; then the baseline panel on the same kit | "Where it loses: bruised fruit. A mask doesn't show bruises, and the damage question was too noisy on good trays, so calibration switched it off. Muse Spark on its own catches 25 of 31 of these. Inspec catches 1." |
| 2:40–2:50 | README top, repo URL | "Packing list in, checks out, evidence for every verdict. Inspec, on Muse Spark and SAM 3.1." End card: "Images: MVTec LOCO AD, CC BY-NC-SA 4.0." |

## Before upload

- Every number spoken matches the README on the submitted commit.
- No `.env`, API key or shell history on screen.
- Under 3:00.
