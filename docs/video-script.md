# 3-minute demo video: script and shot list

Target 2:50, so there's slack. Screen recording of `streamlit run app.py`. Every number spoken
is from the README; don't round them up.

Dataset images (MVTec LOCO, CC BY-NC-SA 4.0) may appear in the video for this non-commercial
entry, with attribution on the end card. Don't commit screenshots of them to the repo.

## Before recording

- `.venv/bin/streamlit run app.py`, browser at 125% zoom.
- Each shot has a URL that opens the right kit and image (below). Open each one once before
  recording so every answer is cached and nothing waits on an API call.
  - A: `http://localhost:8501/?kit=Screw%20Bag&show=Wrong%20parts%20or%20amounts&image=029&compare=1`
  - B: `http://localhost:8501/?kit=Breakfast%20Box&show=Wrong%20parts%20or%20amounts&image=049`
  - C: `http://localhost:8501/?kit=Breakfast%20Box&show=Damaged%20or%20contaminated&image=045&compare=1`
- Images, all from the held-out (odd) half. Check each in the app before recording; the
  baseline panel and the failed check must show what the voice-over says:
  - Screw Bag `test/logical_anomalies/029.png`: `screw_too_short`, the 3-ref + size-guide
    baseline passes it; Inspec reports "long_screw_count: found 0" and "short_screw_count: found
    2" (also 039; `1_very_short_screw`: 101).
  - Breakfast Box `test/logical_anomalies/049.png`: `underflow`; Inspec reports "granola_area:
    found 326007, expected 375230..481162". Not 071: it fails because SAM finds no granola at all.
  - Breakfast Box `test/structural_anomalies/045.png`: `fruit_damaged`, caught by
    `tangerines_damaged` ("torn peel"; also 047, 049).

## Script

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:15 | URL A, scrolled to the photo in section 3 | "Kits like this ship with one long screw, one short screw, two nuts, two washers. A wrong-length screw looks almost right. Can a model check a kit from the packing list alone?" |
| 0:15–0:35 | URL A, top: section 1, the packing list chips and the checks under them | "Inspec takes the packing list as text. Muse Spark compiles it into a check program: the parts, the SAM concept for each, and count checks. No training, no labelled defects." |
| 0:35–1:05 | Section 2: "60 / 60 → 2 / 60" and "What it learned" | "The first program rejects every good kit: SAM ignores size words and calls washers nuts. So Inspec runs the program on known-good kits and Muse Spark repairs whatever fails. From 60 good kits it learns that nuts have smaller holes than washers and how long a long screw is. Every repair is checked in code before it's kept." |
| 1:05–1:35 | Section 3 of URL A: red Reject banner, masks, then the "Muse Spark alone" box saying Pass | "This kit has two short screws. Inspec fails it and shows why: neither screw reaches the long-screw length it learned, so it counts zero long screws and two short ones. Muse Spark looking at the photo alone says the kit is fine." |
| 1:35–1:50 | Section 4: the results table | "On the MVTec LOCO test set Inspec catches all 137 logical defects. The best vision-only baseline catches 130, and only after we gave it the size ratio Inspec measured. For damage, a vision model is the better judge, so Inspec asks it: measure what can be measured, ask the model about the rest." |
| 1:50–2:25 | URL B: packing list, "What it learned" (apple, granola amount), then the Reject banner for too little granola | "Same code, a different kit. SAM didn't know 'nectarine', so a concept-repair step had Muse Spark suggest other words and tried each on good kits: 'apple' works. Calibration learned how much granola a good box holds, so this box, with too little, fails on area. 78 of 83 logical defects caught, with no false alarms from the part checks." |
| 2:25–2:40 | URL C: Reject "Tangerines: damaged", the "Looked at (Muse Spark)" list with almonds switched off | "A mask can't see a bruise, so for surface damage Inspec asks Muse Spark, one question per item on the list. Calibration switches off any question that fires on good kits: chipped almonds are normal, so that one goes, but the fruit questions stay. On damage it ties the vision model; on what you can measure it wins, on both kits." |
| 2:40–2:50 | README top, repo URL | "Packing list in, checks out, evidence for every verdict. Inspec, on Muse Spark and SAM 3.1." End card: "Images: MVTec LOCO AD, CC BY-NC-SA 4.0." |

## Before upload

- Every number spoken matches the README on the submitted commit.
- No `.env`, API key or shell history on screen.
- Under 3:00.
