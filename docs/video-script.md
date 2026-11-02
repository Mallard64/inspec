# 3-minute demo video: recording script

Hackathon rules: 3:00 or less, in English, only things built during the hackathon (no slides, no
unbuilt ideas). Open with one line on what existed before and what was built this week, then show
the working flow end to end with live Meta model calls visible.

So the whole video is the running app (`app.py`): no README, no slides, no terminal. Every number
you say must be on screen at that moment.

## Before you record

1. **Reset reviewer decisions.** Every Pass/Reject changes what Muse Spark is shown on later kits,
   and the shots below were tested in this exact order from an empty log:
   `rm -f runs/reviews.jsonl`. Do this before every take, including after the rehearsal.
2. Start the app: `.venv/bin/streamlit run app.py`. Browser at 125% zoom, window about 1440×900,
   bookmarks bar and other tabs hidden. Reload the page at the start of each take.
3. Nothing private on screen: no `.env`, terminal, API key or notifications (turn on Do Not
   Disturb).
4. Rehearse once end to end, then `rm -f runs/reviews.jsonl` again and reload.
5. Record at real speed. In the edit, speed up only the waiting (self-repair, about 2.5 min; each
   live kit, about 30 s) and put a small "sped up" label on those parts.

URLs (paste into the address bar; `live=1` turns on **Live model calls**):

| Shot | URL |
|---|---|
| A | `http://localhost:8501/?kit=Screw%20Bag&show=Wrong%20parts%20or%20amounts&image=029&live=1` |
| B | `http://localhost:8501/?kit=Breakfast%20Box&show=Wrong%20parts%20or%20amounts&image=049&live=1` |
| C | `http://localhost:8501/?kit=Breakfast%20Box&show=Damaged%20or%20contaminated&image=045&live=1` |
| D1 | `http://localhost:8501/?kit=Breakfast%20Box&show=Good%20kit&image=057` (live **off**) |
| D2 | `http://localhost:8501/?kit=Breakfast%20Box&show=Good%20kit&image=046` (live **off**) |
| D3 | `http://localhost:8501/?kit=Breakfast%20Box&show=Good%20kit&image=057&live=1` |

What was checked (Nov 2, against the API):

- **057 without examples** (D1) is REVIEW for "banana chips damaged" in the recorded answer.
  Asked live it was flagged 2 of 3 times, so D1 uses the recorded answer (live off).
- **057 with 046 passed** (D3) came back with no flags 3 of 3 times live.
- **045** (C) must come **before** any decision: with 046 as an example it was flagged only 2 of 3
  times. Don't click Pass or Reject on 045.

## Script

| Time | What to do on screen | What you'll see | Voice-over |
|---|---|---|---|
| 0:00–0:10 | App top, Screw Bag selected. Don't move. | Title, section 1 with the packing list as chips | "Before this week there were Meta's Muse Spark and SAM 3.1 models and a public dataset of kit photos. This week I built Inspec." |
| 0:10–0:20 | Scroll slowly through section 1. | "1 long screw · 1 short screw · 2 nuts · 2 washers" and the checks as sentences | "You type a packing list. Muse Spark compiles it into checks: exactly one long screw, one short screw, two nuts, two washers." |
| 0:20–0:50 | Section 2: click **▶ Run it live**. Wait (sped up, label). When it's done, scroll over "What it learned" and the call table. | Status: compiling, then checking concepts, then self-repair; "Done: … good kits pass"; "What it learned"; a table of Muse Spark and SAM 3.1 calls with times | "Then it runs those checks on 60 photos of good kits, live. A check that fails on a good kit is wrong, so Muse Spark rewrites it and code validates the fix. Here it learned how long each screw is and that a nut's hole is smaller than a washer's. These are the live model calls it made." |
| 0:50–1:15 | Paste **URL A**. Wait (sped up). Scroll: banner, photo and masks, the ✅/❌ list, the call table. | Red **❌ Reject**: two short screws, no long screw. Coloured masks on every part. | "Now a kit from the test set, inspected live. SAM 3.1 finds every part and plain code measures them. Two short screws and no long one, so it's rejected, and you can see why, with a mask on every part it counted." |
| 1:15–1:25 | Scroll to section 4. | Results table: wrong parts caught 137 / 137, Muse Spark alone 130 / 137 | "On the held-out test kits it catches all 137 kits with wrong parts or sizes. Muse Spark looking at the photo alone catches 130." |
| 1:25–1:45 | Paste **URL B**. Scroll up to section 2 "What it learned" first, then down to the result. | "nectarine" → "apple"; granola amount learned. Red **❌ Reject**, granola covers too little. | "Same code, a different kit. SAM didn't know the word 'nectarine', so Muse Spark suggested others and code tested them: 'apple' works. It also learned how much granola a good box holds. This box has too little." |
| 1:45–2:05 | Paste **URL C**. Scroll: yellow banner, "Looked at (Muse Spark)" list, "Your call" form. **Don't click.** | Yellow **👀 Review**: "Tangerines: damaged (Muse Spark)". Almond damage greyed: "not asked, it fired on good kits". | "A mask can't see a bruise, so Inspec asks Muse Spark one damage question per item, and switches off questions that fire on good kits; chipped almonds are normal. A model's judgement isn't a measurement, so this kit goes to a person instead of being rejected." |
| 2:05–2:15 | Paste **URL D1**. Point at the banner. | Yellow **👀 Review**: "Banana chips: damaged (Muse Spark)" on a good kit | "But the model can be wrong too. This is a good kit; it thinks the banana chips look damaged." |
| 2:15–2:30 | Paste **URL D2** (another good kit, same flag). In **Your call**, type the note `broken banana chips are normal`, click **✅ Pass this kit**. | Green "Saved: PASS" | "Here's another one. I'm the reviewer: I pass it, and say why." |
| 2:30–2:45 | Paste **URL D3**. Wait (sped up). Open the **What reviewers taught it** expander. Scroll to the call table. | Green **✅ Pass**. Expander: "1 example photo in use", photo 046 captioned "✅ passed: banana chips · broken banana chips are normal". The Muse Spark call in the table. | "Back to the first kit, asked live. Muse Spark now sees my decision as a labelled example before it looks, and the kit passes. Nothing was retrained." |
| 2:45–2:58 | Scroll to section 4, then the footer. | Breakfast Box results: wrong parts or amounts caught 78 / 83 vs 68 / 83; footer with dataset credit | "Inspec beats the vision model on what can be measured, ties it on damage, shows evidence for every verdict, and learns from the person who checks its work. Built on Muse Spark and SAM 3.1." |

About 2:58. If you run long, cut the section 2 "What it learned" scroll in shot B (1:25) first.

## If something goes differently

- **A live answer differs from this script** (for example, D3 still says Review): say what's on
  screen, not what's written here. To retry: `rm -f runs/reviews.jsonl`, reload, and redo from D1.
  Don't edit the take to hide it.
- **"Run it live" fails** (API error or timeout): retake that shot. Don't show the cached result
  as if it were live.
- **A live kit takes very long:** keep recording and speed it up in the edit, with the label.

## Before you upload

- Under 3:00, English, no slides, nothing private on screen.
- Every number you say is on screen at that moment.
- Sped-up parts are labelled.
- Afterwards: `rm -f runs/reviews.jsonl`, so the app is back to its default state.
- Don't commit the video file: it shows dataset images (CC BY-NC-SA). `out/` is gitignored if you
  save it there.
