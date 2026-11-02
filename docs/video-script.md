# 3-minute demo video: script and shot list

Rules (from the hackathon): 3:00 or less, in English, only things built during the hackathon (no
slides, no unbuilt ideas). Open with one line on what existed before and what was built this
week, then show the working flow end to end with live Meta model calls visible.

So the whole video is the running app (`app.py`). No README, no slides. Every number spoken
must be on screen at that moment or in the app's results table.

## Before recording

- `.venv/bin/streamlit run app.py`, browser at 125% zoom.
- URLs for the shots. `live=1` turns on "Live model calls (skip cache)", so SAM 3.1 and Muse
  Spark are called on the spot and listed under the result with their timings.
  - A: `http://localhost:8501/?kit=Screw%20Bag&show=Wrong%20parts%20or%20amounts&image=029&live=1`
  - B: `http://localhost:8501/?kit=Breakfast%20Box&show=Wrong%20parts%20or%20amounts&image=049&live=1`
  - C: `http://localhost:8501/?kit=Breakfast%20Box&show=Damaged%20or%20contaminated&image=045&live=1`
- Do one full rehearsal. Live answers can differ from run to run; if one does, say what's on
  screen, not what this script says.
- Live inspection of one kit takes about 25–35 s; the live self-repair run about 2.5 min. Record
  in real time and speed up only the waiting in the edit, with an on-screen "sped up" label.
- Don't turn on "Compare with Muse Spark alone" during live shots: asked live, it sometimes
  catches kit 029 and sometimes doesn't. The results table (section 4) is the fair comparison.
- No `.env`, API key or shell history on screen.

## Script

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:12 | App top, Screw Bag selected | "Before this week there were Meta's Muse Spark and SAM 3.1 models and a public dataset of kit photos. This week I built Inspec: it turns a packing list into checks, fixes them itself, and inspects kits with them." |
| 0:12–0:30 | Section 1: packing list chips. Section 2: click "▶ Run it live". The status shows Muse Spark compiling, then "Compiled: Exactly 1 × long screw · …" | "Here's the packing list. I press run, and Muse Spark compiles it, live, into checks: exactly one long screw, one short screw, two nuts, two washers." |
| 0:30–1:00 | Same status, waiting sped up (label on screen) until "Done: … good kits pass"; the "What it learned" lines; the call table | "Then Inspec runs those checks on 60 photos of known-good kits. Any check that fails on a good kit is wrong, so Muse Spark rewrites it and code validates the fix. It learns that a nut has a smaller hole than a washer and how long each screw is. Here are the Meta model calls it made." |
| 1:00–1:30 | URL A: red Reject banner, the masks, the ✅/❌ list, the call table (SAM 3.1 segmentations, Muse Spark damage check) | "Now a kit from the test set, inspected live. SAM 3.1 finds every part; plain code measures them. Two short screws and no long one: rejected, and the reason is right there, with a mask on every part it counted." |
| 1:30–1:45 | Section 4: the results table for Screw Bag | "On held-out test kits, Inspec catches all 137 kits with wrong parts or sizes. Muse Spark looking at the photo alone catches 130." |
| 1:45–2:15 | Switch to Breakfast Box. Section 2 "What it learned" (SAM didn't know "nectarine", uses "apple"; granola amount), then URL B: Reject "Granola covers … measured 326,007", call table | "Same code, a different kit. SAM didn't know the word 'nectarine', so Inspec had Muse Spark suggest others and tested them: 'apple' works. It also learned how much granola a good box holds, so this box, with too little, is rejected." |
| 2:15–2:40 | URL C: yellow "Review" banner, "Tangerines: damaged (Muse Spark)", the "Looked at (Muse Spark)" list with almond damage not asked, the model's note | "A mask can't see a bruise, so for damage Inspec asks Muse Spark one question per item, and switches off questions that fire on good kits: chipped almonds are normal. A model's judgement isn't a measurement, so this kit goes to a person for review instead of being rejected outright." |
| 2:40–2:55 | Section 4 for Breakfast Box, then the footer | "Inspec beats the vision model on what can be measured, and ties it on damage, with evidence for every verdict. Built on Muse Spark and SAM 3.1. Images: MVTec LOCO." |

## Before upload

- Under 3:00, English, no slides.
- Every number spoken is on screen at that moment or in section 4.
- Sped-up parts are labelled.
