# Build log

One dated entry per working session: what was decided, which alternatives were rejected and why,
and what was measured. Written as source material for the Stage 2 design portfolio.

Deadlines: working demo on camera by **5 Oct 2026**; Stage 1 video due **23 Oct 2026**; Stage 2
portfolio due **30 Nov 2026** (if selected); final pitch **12 Dec 2026**.

---

## 2026-09-27: proposal, feasibility checks, step 1 (thin slice: microphone to live pitch line)

### Context
The first session was cut off before anything was written, so this session started from an empty
folder. Agreed plan: three steps, each ending with a stop so the team can run it.
1. Thin slice: microphone in, live pitch line.
2. Loudness, pauses, pace, tension.
3. Calibration, polish, demo material.

### Feasibility checks before proposing (throwaway environment)
- **Pitch tracking cost.** Praat's autocorrelation pitch tracker (via `praat-parselmouth` 0.4.7,
  Praat 6.1.38) took **0.15 to 0.85 ms** per call on 120 to 300 ms windows at 16 kHz (i7-12700H).
  It returned exactly 95, 180 and 310 Hz on synthetic vowels. Computation is therefore not the
  latency problem; buffering and smoothing are.
- **Audio route.** The default Windows input goes through MME, which PortAudio reports at **90 ms**
  input latency. The same device through WASAPI reports about **2 ms**.
- **Test voices.** Windows' built-in voices (David, Zira) honour SSML prosody. The same sentence came
  out at a median of 152 Hz with pitch "-25%" and 223 Hz with "+40%".
- **Wheels.** Every dependency has ready-made wheels for Python 3.10 to 3.14 on Windows and macOS.

### Decisions (and the alternatives rejected)

**1. Window and drawing: PySide6 (Qt) with QPainter.**
- *pygame*, rejected: always-on-top needs SDL workarounds, and it draws thick anti-aliased lines poorly.
- *pyqtgraph*, rejected even though the brief suggested it: its value is axes, ticks and zooming, and
  this display deliberately shows none of those (no numbers for Vikram to read). Step 2's line whose
  thickness follows loudness is easier to draw directly with QPainter than through pyqtgraph's
  one-pen-per-curve model.
- *Full `PySide6` package*, rejected in favour of `PySide6-Essentials`: it contains everything needed
  (Core, Gui, Widgets) and is less than half the download.

**2. Pitch: Praat autocorrelation through parselmouth.**
- *librosa pyin*, rejected: there was no speed need, it would add a heavy numba/LLVM dependency, and
  Praat is the standard tool in voice and speech research, which is easier to defend to judges.
- *A hand-written numpy YIN or autocorrelation*, rejected: it lacks Praat's path-finder, which
  suppresses octave jumps using context.

**3. Streaming design.** Every 20 ms, the newest 200 ms of audio goes to Praat, and only the new
10 ms frames are kept.
- Windows always start on a 20 ms grid, so Praat places frames at identical sample positions on every
  run. The output is therefore bit-identical whatever block size the sound card uses. A test feeds
  1, 37, 160, 441 and 1600-sample blocks and gets the same result each time.
- The newest pitch value describes sound from 25 ms ago: half of Praat's 43 ms window, set by the 70 Hz
  pitch floor.
- Check against Praat analysing the whole file at once: on both sample voices, the median difference
  was **0.01 semitones**, and no frame differed by more than 1 semitone. Streaming costs no accuracy.

**4. One analysis rate (16 kHz) with a hand-written stateful polyphase resampler.**
- It uses the same filter design as `scipy.signal.resample_poly`, and tests show the two agree to
  1e-9 for 8, 22.05, 32, 44.1 and 48 kHz inputs fed in random block sizes.
- *Asking the sound system to convert rates*, rejected: WASAPI does this only with a special flag and
  WDM-KS not at all. Doing it in software gives one code path for every microphone and for files.
- *Resampling each block independently with `resample_poly`*, rejected: it clicks at every block
  boundary.

**5. Latency is measured, not estimated.**
- Each audio block carries a timestamp: when its sound reached the microphone (callback time minus
  the reported device latency), or, for a file, when it will be heard (callback time plus the output
  latency).
- A clock mapping turns stream time into wall-clock time. For microphones it uses the *minimum* recent
  offset, because late callbacks can only make the estimate too large. For playback it uses the
  *maximum*.
- At paint time, each newly visible frame gets latency = paint time minus the time its sound occurred.
  `--debug` prints the median and 95th percentile.
- **Result on the USB microphone: 73 ms median, 85 ms 95th percentile.** File mode: the line trails
  the audible sound by 9 ms median. Not included: the monitor's own lag, roughly 17 to 33 ms, which
  software cannot see.

**6. Display mappings (step 1).**
- **Time:** newest at the right edge, 10 s of history.
- **Height:** semitones from the speaker's median pitch over the last 20 s. The median is provisional;
  step 3 replaces it with calibration.
  - Semitones rather than Hz, because equal musical steps look equal for deep and high voices.
  - A test shows the same melody an octave apart draws the same picture, to within 1 pixel.
  - Two sample voices an octave apart both sit on the centre line (README pictures).
- **Scale:** ±10 semitones to the edges; everyday speech uses about ±2 to 6.
- **Gaps:** the line breaks wherever there is no voiced sound.

**7. Off-scale pitch is a faint mark on the edge, not a line pinned to the edge.** Found in live testing.
- *Clamping*, rejected: pinning out-of-range values to the edge drew edge-to-edge vertical strokes.
  These are the most eye-catching thing on screen, and in peripheral vision they pull attention
  exactly where the data is least trustworthy.
- The line now breaks, and a dim dash marks the top or bottom edge. The evidence is still shown, but
  quietly.

**8. Voiced stretches shorter than 50 ms are not drawn.** Real syllables last longer. The rule removes
isolated blips from noise at the cost of 40 ms extra delay at the start of each voiced stretch only.

**9. Noise gate: a frame must be 10 dB above an adaptive background estimate.**
- The estimate drops instantly to quieter frames and rises at 1 dB/s.
- Mains hum is perfectly periodic, so Praat alone calls it voiced. With a 6 dB gate, 17% of synthetic
  hum frames were drawn as pitch; with 10 dB, 0%. A test now guards this.
- Frames of exact digital silence are ignored when estimating the background. The laptop's Realtek
  "Microphone Array" outputs pure zeros between sounds (its own noise suppression), which dragged the
  estimate to -120 dB and disabled the gate.

**10. Start the microphone after the window has appeared.**
- While the window is being created, Python is busy and the stream appeared to drop 45 to 105 ms of
  audio, which skewed the latency estimate for the next 3 s.
- Fix: open the device first (so errors are still reported before any window appears), then start it
  200 ms after the window shows. The clock mapping's memory was also shortened from 3 s to 1 s, so any
  later glitch self-corrects within a second.

**11. Test WAVs from Windows text-to-speech.**
- Voices: "David" (about 89 Hz) and "Zira" (about 178 Hz).
- Saved at 22.05 kHz on purpose, so file mode exercises the resampler.
- A -65 dBFS hiss is added, so quiet parts behave like a room rather than digital silence.
- Good for repeatable tests. For the video, the team should record real people with `--record`.

**12. Privacy.** Nothing is written to disk without `--record`. After all the microphone test runs, no
`recordings` folder existed. A 3 s `--record` test went to a scratch folder and was deleted after its
length and format were checked. The diagnostic microphone captures used during development were held
in memory only and analysed for pitch and level statistics only.

### Findings and failures observed

**The pitch line looks spiky at 10 s in 400 px.**
- This is a display problem, not a tracking one: tracking matches whole-file Praat.
- Speech pitch moves roughly 10 to 20 semitones per second within syllables. Squeezing 10 s into
  400 px makes those movements near-vertical.
- It also fragments at every consonant.
- Options for step 2: join short consonant gaps, a thicker line driven by loudness, maybe a shorter
  window. `--seconds` was added so the team can compare 10 s against 5 s.

**Sound from laptop speakers into the USB microphone** (a stand-in for "video call played out loud"):
- The signal was about -80 dBFS, and 39 of 69 voiced frames were an octave too high. Small speakers
  do not reproduce the voice's fundamental, so the tracker latches onto the next harmonic.
- The built-in microphone right beside the speakers (about -43 dBFS) had no octave errors.
- Lesson for video calls: capture the call audio directly. This laptop exposes "Stereo Mix"; untested.

**Real speech in the room on the USB microphone** (in-memory capture, statistics only):
- Most voiced stretches sat at 115 to 160 Hz.
- About 17% of voiced frames were far outside that: some near 400 Hz (about three times the speaker's
  pitch) and some at 70 to 90 Hz.
- Planned fix, step 3: calibration doubles as the first pass of the two-pass pitch-range method from
  prosody research (Hirst; De Looze and Hirst). It sets the pitch floor and ceiling from the speaker's
  own quartiles, roughly 0.75 x Q1 and 1.5 to 2 x Q3.
- *Doing this continuously in step 1*, rejected: without an explicit calibration, the range can lock
  onto the wrong register when speakers change, and a lower voice would then be tracked an octave up.
- *Folding octave errors*, rejected: the errors seen were mostly x3, not x2, and folding could hide
  real extremes.

**One unexplained stall.**
- In the first live test, no new pitch data arrived for the last ~4 s. It did not recur in six more
  runs.
- Added a watchdog ("The microphone stopped sending sound", in the window and the console) and
  diagnostics in `--debug` (audio received, backlog, redraws, window state).
- A likely real-world cause is another app taking exclusive control of the microphone. Voicemod is
  installed on this laptop.

**Windows stops redrawing a minimized window.** This is expected, and analysis continues underneath.
It was mistaken for a freeze until `--debug` showed the window state.

### Deferred
- **Automatic restart of a stalled microphone:** a message is enough for step 1.
- **Speaker-adapted pitch range:** step 3, as above.
- **Mac testing:** needs a teammate's Mac before 5 Oct.

### Tested environment
- Windows 11 Home 10.0.26200, Intel i7-12700H, 16 GB.
- Python 3.12.7 with numpy 2.5.3, scipy 1.18.1, sounddevice 0.5.6 (PortAudio V19.7.0-devel),
  soundfile 0.14.0, praat-parselmouth 0.4.7 (Praat 6.1.38), PySide6-Essentials 6.11.2 and pytest 9.1.1.
- 36 tests pass.

### Next: step 2
- **Loudness:** line thickness and brightness.
- **Pauses:** join gaps under 250 ms; long pauses of 1 s or more highlighted, growing while they last.
- **Pace:** syllables per second of speaking time, as a bar plus syllable dots.
- **Tension:** a comparison of jitter, shimmer and spectral tilt for real-time stability, with numbers.
- Tests for each.

---

## 2026-09-27 (session 2): steps 2 and 3, the other four signals, calibration, polish, demo

### Context
The team said "carry on through the plan, and make it cooler and better, with more features".
- "More features" was read through the brief's own rule: *optimise for what runs and reads clearly
  on video, not for feature count*.
- Additions were chosen to serve peripheral reading and the Stage 1 video: a side-by-side comparison
  view, a help overlay, freeze, recalibrate, and a soft glow on the line.
- Nothing moves toward labelling emotion.

### The tension proxy: measured, not assumed
The brief asked for "the one that stays most stable in real time". `tools/tension_bakeoff.py` measures
each candidate over 1 s windows (every 0.25 s) on two neutral readings (about 23 s each; 127 windows),
then on copies changed in ways that *should not* move a tension measure, and ways that *should*.

The effect size is d = median shift ÷ window-to-window wobble.

| Measure | Wobble | Quieter | Noise | Room echo | Intonation | Pressed | Breathy | Average nuisance | Wanted |
|---|---|---|---|---|---|---|---|---|---|
| Jitter | 0.35 % | 0.00 | 0.02 | 1.98 | 0.86 | -0.17 | 0.20 | 0.71 | 0.18 |
| Shimmer | 1.50 % | 0.00 | -0.01 | **3.90** | 0.07 | 0.37 | -0.23 | 0.99 | 0.30 |
| Tilt, median of frames | 2.36 dB | 0.00 | 0.68 | 1.05 | -0.06 | 2.10 | -0.81 | 0.45 | 1.46 |
| **Tilt, pooled spectrum** | **2.04 dB** | 0.00 | 0.16 | 0.22 | -0.10 | 2.21 | -1.65 | **0.12** | **1.93** |

**Decision: spectral tilt, pooling the spectrum of the last 1.5 s of voiced sound.** This is the
eGeMAPS "alpha ratio": energy 1-5 kHz relative to 50-1000 Hz.
- *Shimmer*, rejected: an ordinary echoey room shifts it by 3.9 of its own wobbles. It would read a
  voice as "tense" because of the room.
- *Jitter*, rejected: it shifts with room echo (2.0) and with livelier intonation (0.9). An animated
  speaker would look "tense". Jitter and shimmer are defined for sustained vowels, not running speech.
- *Pooled tilt*: ignores volume, barely notices echo or noise, responds most to voice quality.
  Pooling the spectra (rather than taking the median of per-frame values) cut the nuisance
  sensitivity from 0.45 to 0.12.

**Honest caveat.** The "pressed" and "breathy" test voices were made by reshaping the spectrum, which
favours a spectral measure by construction. The decision therefore rests on the nuisance columns,
which involve no such bias. The script accepts any WAV files: re-run it on real "relaxed" and
"strained" recordings when the team has them.

### Decisions (and the alternatives rejected)

**1. Loudness: line thickness *and* brightness.**
- Smoothed with a fast attack (20 ms) and a slower release (150 ms), so each syllable reads as one shape.
- Scaled from 15 dB below to 12 dB above the speaker's typical level.
- Encoded twice on purpose: peripheral vision is far better at brightness than at hue.

**2. Speech versus silence is anchored to voicing.** Found live, not planned.
- The laptop's Realtek mic lets bursts of room noise through its noise suppression.
- The first version counted any sound above threshold as "speaking". It calibrated on a quiet room,
  learned a pace of 1.0 syllables/s, and pinned the pace bar at maximum.
- Now unvoiced sound counts as speech only within 0.3 s after real voicing (consonants), and voicing
  must last 30 ms.
- Cost: a pause's end is logged 20 ms late.
- Rejected: pure level thresholds (noise breaks pauses), and pure voicing (long voiceless consonant
  clusters would read as pauses).

**3. Pauses.**
- A pause is silence of 0.25 s or more (Goldman-Eisler's cut-off). Silence means within 6 dB of the
  background, or 25 dB below the speaker's typical level, which covers breaths, as in de Jong & Wempe.
- Pauses of 1 s or more get a shaded column across the whole height. It darkens at 2 s and 3 s, and
  grows live at the right edge while the pause lasts.
- Gaps in the line shorter than 0.25 s inside speech (consonants) are joined by a thin, dim line, so
  that every visible gap is a real pause. This fixes the "row of short strokes" look from step 1.
- A finished file's trailing silence is not shown as a pause.

**4. Pace.**
- Syllable nuclei after de Jong & Wempe (2009): voiced loudness peaks standing 2 dB above the dips
  on either side.
- Articulation rate: syllables per second of speaking time over the last 4 s of speech. Pauses are
  excluded, so they aren't counted twice. A test confirms that pauses do not slow it down.
- Threshold checked on the test voices: a 2 dB dip gave a total counting error of 3 syllables across
  six sentences; 1.5 dB gave 7 and 1 dB gave 12. So the published value stays.
- Known limit: in very fast speech, syllables merge. The fast take counted 11 of 13 and read ×1.14
  instead of about ×1.4.
- Display: a bar on the right, which goes up for faster than usual, with a notch at the usual pace
  and a faded fill during a pause.
- Plus one tick per syllable in a lane under the line, which reads like a rhythm barcode.
- *Dots on the line*, rejected: light dots on a light line had too little contrast.
- *A flashing pulse*, rejected: flicker in peripheral vision pulls the eye off the client's lips.

**5. Tension colour.**
- Blue (softer or breathier) ← neutral white → amber (more pressed).
- Changes under 1 dB from the baseline stay neutral, which absorbs vowel-to-vowel wobble. The colour
  is full at 5 dB.
- Blue and amber survive the common colour-vision deficiencies.
- *Red*, rejected: it reads as "angry", a verdict smuggled in through colour.

**6. Calibration.**
- Uses the first 15 s of the person actually speaking (voicing-anchored), usually 20 to 25 s of
  conversation.
- Learns their median pitch, quartiles, usual range (10th to 90th percentile, shown as a faint band),
  typical loudness, pace and tilt.
- The baseline then stays fixed until R is pressed. *A slowly adapting baseline*, rejected: it would
  hide a client getting steadily quieter or slower across a session.
- Before calibration the line is grey, with a small progress ring and "calibrating…". There is no
  pace bar and no tension colour until there is a baseline to compare against.
- Calibration also sets the pitch tracker's search range: 0.75 × lower quartile to 2 × upper
  quartile, after Hirst's two-pass method.
  - This cuts octave errors and stray voices.
  - Side effect: a narrower range means Praat's analysis window is shorter, and measured latency
    fell from 72 ms to 63 ms.
- After calibration, voiced sound more than 30 dB below the speaker's typical level is treated as
  background.
- `--baseline FILE` takes the baseline from a recording instead; the demo uses this.

**7. A bug the test recordings exposed: DC offset.**
- The text-to-speech voices carry a small DC offset. Praat's resynthesis removes the overall mean,
  which leaves the "silent" breaks sitting at a constant -41 dB, so no pauses were detected in the
  hesitant take.
- Real microphones can have DC offset too. The fix is in the app, not only the test material: a
  50 Hz high-pass at the start of the analysis, which also removes rumble below the lowest voice pitch.
- A test feeds a 0.05 DC offset and checks that silence stays below -80 dB.

**8. Comparison view** (`--compare`, `run_demo.bat`).
- Up to four recordings side by side, measured against one baseline, each filling in while it plays.
- Recordings shown whole are drawn from the left like a pen, on **one shared time scale**.
  *A per-panel time scale*, rejected: it would make a slow take look as dense as a fast one.
- Panels are labelled only A to D; the take names stay in the console, so no word like "calm"
  appears on screen.

**9. Polish for peripheral vision and camera.**
- A soft glow behind the line.
- The oldest 12% of the window fades out.
- A glowing dot marks "now".
- Space freezes the display, for supervision debriefs.
- H shows a plain-English legend.
- R recalibrates.

### Test material (text-to-speech plus Praat edits; replace with real voices for the video)
The four takes of the demo sentence, against the neutral Zira baseline (174 Hz, 4.8 syllables/s,
tilt -12.5 dB):

| Take | How it was made | Measured against baseline |
|---|---|---|
| A: calm, even | 8% slower | pitch +0.5 st, loudness +0.8 dB, pace ×0.92, tilt -0.6 dB |
| B: rising, hesitant | +2 st, word-final pitch rises, five 1-2 s breaks, "um" | pitch +3.1 st, 5 pauses ≥ 1 s (longest 2.0 s), pace ×0.86 |
| C: fast, loud | 28% faster, pitch range ×1.3, +8 dB, upper harmonics +6 dB | loudness +8.5 dB, tilt +4.9 dB, pace ×1.14 (undercounted) |
| D: flat, quiet | pitch range ×0.25, -10 dB, breathy | pitch spread 1.8 st (A: 7.1), loudness -9.6 dB, tilt -2.4 dB |

### Failures, measured and shown (README, section 7)
- **Two voices at once:**
  - The pitch line mostly stays on the calibrated voice, because the other voice fell outside the
    calibrated pitch range.
  - Loudness and pace mix both voices; pace read ×0.69.
- **A voice through a tiny speaker** (350 Hz to 4 kHz):
  - Pitch is still right.
  - But tilt reads +6.3 dB, so the whole line turns amber (a false "pressed").
  - Lesson: calibrate through the same audio path you will use.
- **Whisper:** no real pitch. The tracker still produced two junk strokes, and a 1.2 s stretch
  registered as a pause.
- **Video calls through "Stereo Mix":** the device opens, but it heard nothing, because it is
  disabled in this laptop's Windows sound settings. Enabling it is a system setting for the owner.
  Untested beyond that.

### Measured performance
- Latency, microphone to screen: 71-73 ms median before calibration, 63-64 ms after; 95th percentile
  83-85 ms. The monitor adds roughly 17-33 ms that software cannot see.
- CPU: about 15% of one core (up from 9% with the plain line). Memory: about 190 MB.
- 74 tests pass. Every visual mapping in the README has a pixel-level test (for example "louder is
  thicker", "a short gap is joined but a pause is not", "pace bar goes up when faster").
- Writing the "now dot" test caught a real flaw: the dot sat on the plot's right edge and was clipped
  in half. The clipping area now extends into the gap before the pace bar.

### Still open
- Real recordings for the video (see DEMO_SCRIPT.md).
- Mac testing.
- Call audio: Stereo Mix, or a WASAPI loopback library, is a later step.
- In a two-person role-play, the calibration learns whoever speaks first. The README tells the team
  to press R when the client starts talking.

---

## 2026-09-29 (session 3): the dashboard (entry written afterwards, from the code)

**This session ended without writing its log entry.** Session 4 wrote this one from what the
session left behind: the code, its comments, the tests and the pictures in `docs/img`.
- A reason is given only where it was written down somewhere; each is marked with where.
- Where no reason was recorded, the entry says so rather than inventing one.

### What was built
- **A dashboard around the display, now what `run.bat` opens.** Five tabs:
  - **Live:** the display large; each signal on its own row for the last minute; the whole
    session in one strip.
  - **Review:** the whole session; what changed; any stretch summarised in words; two stretches
    compared; marks with notes; save, open and export.
  - **Compare:** the four-take comparison.
  - **Guide:** how to read it.
  - **Setup:** microphone, calibration and baselines, display, privacy.
- **The original small window** survives two ways:
  - as the dashboard's **corner view** (always on top; Space, M, R, T, H);
  - on its own with `--corner`.
- **`session.py`:**
  - keeps every 10 ms measurement of a session (the live views keep only the last seconds);
  - summarises any stretch against the baseline in plain words about the voice;
  - finds "what changed";
  - saves sessions as `.tonevis` files: compressed numbers plus a JSON header, **never sound**.
- **`engine.py`:** runs one listening run at a time (microphone or file). Runs are laid end to
  end in one session, with a 1 s gap, by offsetting their times.
- **Baselines** can be saved as JSON (numbers only) and loaded later, so a second session with
  the same person starts calibrated. They can also be learned from a recording.
- **`demo/wavs/session_demo.wav`** (about 57 s): the neutral synthetic reading, then the four
  takes, for trying the Review tab.

### Decisions visible in the code
**1. Evidence in words: how far from usual counts as different.** A stretch needs 2 s of speech
before anything is said about it. It is then described if its:
- median pitch is 1.5 semitones or more from the usual middle (higher or lower);
- pitch spread is under 0.7 or over 1.3 times the usual range (flatter, or more up-and-down);
- median loudness is 4 dB or more from usual (louder or quieter);
- pace is under 0.87 or over 1.15 times usual (slower or faster);
- voice quality is 1.5 dB or more from usual (more pressed, or softer or breathier).

Recorded reason (`config.py`): each threshold "sits well above that measure's ordinary wobble",
so steady speech reads "much as usual". The words describe the voice, never a feeling.

**2. "What changed", the review's list of changes.**
- Every second, it looks back over the last **3 s of speaking**, reaching back at most 15 s so
  that halting speech is still judged on enough voice.
- For pace it looks back over **6 s**. Recorded reason: syllable counts in 3 s wobble by about
  20%.
- A change is reported only when **3 windows in a row agree**.
- The run of windows is then:
  - split at pauses of 3 s or more;
  - narrowed to the one-second slices that really differ (recorded reason: looking back several
    seconds would otherwise smear a change backwards in time);
  - trimmed to the speech;
  - confirmed by summarising exactly that stretch.
- Pauses of 3 s or more are listed on their own.

**3. Drawing is rationed, because it competes with the analysis for Python's attention**
(recorded in the code):
- the big view and the corner view redraw 30 times a second while listening;
- the signal rows 10 times a second;
- next to nothing when idle;
- the soft glow is off on the big view ("on this big view it doubles the cost").

**4. A guard for the core rule.** A test scans every string the app can show, and every sentence
the review can generate, for a list of feeling words.
- Tests: 74 → 98.

### Not recorded
- Why five tabs, and this particular split of the work between them.
- **Numbers appeared in the Review, Compare and Setup tabs and the status bar.** The brief had
  kept numbers to `--debug`, and no reason for the change was recorded. Session 4 put them behind
  a switch that is off unless ticked (below).

---

## 2026-09-29 (session 4): making it explain itself, recording takes in the app, a filming plan

### Context
The team asked for:
- the demo script turned into exact scenes, with how to film each one;
- a dashboard that looks better and explains itself (how the app works, what the features are),
  and is easier to understand and use;
- ideas for further changes to the look and the interface;
- a justification for building a Python desktop app rather than a web page.

Three problems turned up first and were fixed.

**1. The instructions for recording takes had quietly stopped working.**
- Since `run.bat` opens the dashboard, `.\run.bat --record demo\takes\a.wav` opened the dashboard,
  ignored the file name, and saved to `recordings\` instead. Q no longer stopped it.
- The team would have found this out on recording day.
- Fixed: the dashboard now saves the first listening run to the named file. Then replaced for
  everyday use by a recording window (decision 8).

**2. The H legend said "amber = more pressed *or edgy*".**
- "Edgy" is a feeling word, and the guard test's list missed it.
- It is gone, and the list gained 20 more words (edgy, tense, worried, tired, relaxed, confident,
  hesitant...).

**3. One display test depended on the font's height.**
- It passed with the test suite's own settings. It failed when Windows' fonts were loaded,
  because the dim centre line then falls exactly on one pixel row, at a lightness of 63, and the
  test's limit was 60.
- The test now looks past the centre line.

### Decisions (and the alternatives rejected)
**1. A key that is always there, beside the live view.** Each row has a tiny drawing in the
display's own colours and one line of meaning: higher line, band, thickness, colour, grey, gap,
ticks, bar, dot.
- *The H overlay alone*, rejected:
  - it covers the display;
  - nobody finds it (the dashboard's big view didn't even respond to H);
  - a key that is visible from the first second teaches by being glanced at.
- *A guided tour*, rejected: it is skipped once and then gone for good.
- H hides the key once it has been learned.
- Found while building it: the key must stay one line per row. A wrapped line anywhere in that
  column made Qt share the column's height out evenly and squash the key. The column now scrolls
  instead, on a short window.

**2. A "Start here" card over the empty live view.** Three numbered steps, a Start listening
button and **Try the demo recording**.
- *A first-run dialog*, rejected: it is dismissed without being read, and never seen again.

**3. The demo plays in a session of its own, with no baseline.** Anything real afterwards starts
fresh.
- Otherwise the demo voice would be measured against the user's baseline, or the other way
  round: a silent, wrong comparison.

**4. The How it works page's pictures are drawn by the display's own code, from made-up
measurements.**
- *Screenshots*, rejected: they drift out of date the moment a colour or a thickness changes, and
  no test can check them.
- A test now checks that every picture draws and shows what it claims (for example: the "faster"
  example has more than twice as many syllable ticks as the "slower" one).

**5. Numbers behind a switch that is off unless ticked.** "Show numbers" is in Review, Compare
and Setup (one switch, three places). This follows the brief.
- The words are the same either way; only the measurements in brackets come and go.
- The live views never show numbers.
- The on-screen delay stays, because it describes the app, not the voice.
- *Awaiting the team's confirmation.*

**6. Hovering over the live view explains the part under the mouse:** the line, the ticks or
the bar.

**7. Notes without looking away from the display.** N drops a mark and puts the cursor in a note
line beside the display; Enter saves it; the display keeps running.
- *A pop-up dialog*, rejected: it covers the display at exactly the moment worth watching.

**8. "Record your own takes": the takes, recorded without any typing.**
- The directions describe how to speak ("slowly, with long pauses"), never a feeling to act. The
  feeling-word test covers them too.
- It records through the same engine as live listening, so each take is shown against the
  baseline while it is recorded. A take that didn't come out can be spotted and re-recorded on
  the spot.
- Recording the baseline starts a fresh session, so the voice is learned from it.
- Takes under 1.5 s are flagged as probable slips.
- *Command line only*, rejected: the team are not programmers, and it had already broken once
  without anyone noticing.

**9. Choices are remembered in `settings.ini` beside the app:** microphone, display lengths, the
key, numbers, window size.
- *The Windows registry (Qt's default)*, rejected: it is invisible and awkward to reset. The file
  can be seen and deleted, and it holds no sound and no measurements.
- The microphone is stored by name, because device numbers change when devices are plugged in.

**10. The look.**
- Dark, calm, like an instrument panel.
- Panels ("cards"), each with a title and one line on what it is for.
- **One interface colour (periwinkle) that the display never uses**, so no part of the frame can
  be mistaken for a measurement.
- The font is 10 pt Segoe UI Variable (Windows 11's own interface font), picked by name from the
  installed fonts. Asking Qt for a font that is missing fell back, off-screen, to "Agency FB".
- Icons are drawn in code:
  - no image files or icon fonts;
  - the same on a Mac;
  - sharp at any screen scaling.
- The minimum window is 1140 × 700, the narrowest at which every toolbar label fits. At 1000 px,
  "Start listening" was clipped.

**11. Pictures made by a script.** `tools/dashboard_screenshots.py` remakes every dashboard
picture from the demo recording, off-screen, so the README and portfolio images can be refreshed
after any change.

### Why a Python desktop app and not a web page
**Not mainly speed.** Both could be fast enough: the heavy work runs in compiled code (Praat in
C++, numpy, Qt's drawing). The reasons, in order of weight:

1. **The pitch tracker.** Praat's own algorithm runs through parselmouth, and Praat is the
   standard tool in voice and speech research.
   - A browser would need a JavaScript or WebAssembly re-implementation (YIN, McLeod...).
   - It would lose the check against Praat (0.01 semitones median difference) that session 1
     measured.
2. **The raw sound.**
   - By default, browsers pass the microphone through echo cancellation, noise suppression and
     automatic gain. Automatic gain would flatten the loudness signal.
   - They can be turned off, but the desktop app owns the whole path and time-stamps every block,
     which is how the delay was measured in the first place.
3. **A real always-on-top window.** A browser offers this only through Chrome's Document
   Picture-in-Picture, and not in Firefox or Safari.
4. **Offline and private by construction.** There is no server and no network code, so "nothing
   leaves the laptop" is simple to show.
5. **One code path for everything.** Live listening, recordings, the tension bake-off, the
   review and the tests all reuse the same analysis.

What it costs, which the pitch should admit:
- an install step (450 MB);
- no phones or tablets;
- the Mac is untested;
- judges cannot simply open a link.

A web version of the *display*, fed by the same analysis, is a reasonable later step for reach.

### Measured (development laptop, off-screen)
- **Delay inside the dashboard:** 69 ms median, 94 ms 95th percentile, from the sound being
  handed over to it being drawn.
  - Measured with a recording standing in for the microphone.
  - The same with the corner view open.
  - The microphone's own 20 ms buffer comes on top.
- **CPU:** 33% of one core with the Live tab showing, 50% with the corner view as well.
  - That is analysis and drawing together, about 2 to 3% of the whole machine.
- **Tests:** 98 → 122. New ones cover:
  - the start card;
  - hiding the key;
  - numbers on and off;
  - notes from the Live tab;
  - the demo's own session;
  - recording takes, with a stand-in microphone;
  - `--record FILE`;
  - remembered settings;
  - the hover explanations;
  - every How it works picture.

### Filming plan
`demo/DEMO_SCRIPT.md` is rewritten scene by scene:
- 9 scenes, about 4:50, each with its purpose, shot, steps and narration;
- how to set up OBS, the phone and the lighting;
- a "ba!" to line up the recordings (a clap has no pitch, so the display does not show it);
- three quick tests with people, whose numbers go in the video;
- consent;
- editing with burned-in captions, and a final "sound off" check, because the challenger is deaf;
- a timeline to submission on 21 Oct.

### Open
- **Numbers:** keep them behind the switch (off unless ticked), or show them by default in
  Review?
- **Access to Vikram,** or any deaf or hard-of-hearing person, before filming or before Stage 2.
- **Who films and who acts,** and the consent rules for team members under 18.
- **Mac test.**

## 2026-10-02 (session 5): GitHub, and the video's ready-made parts

### What and why
The team needs the code somewhere they can all reach it, and the video due on 23 Oct had a plan
but nothing made yet. Most of the video is the app's own screen, and that part can be made
without a camera, OBS or anyone at the laptop. Only the people (the face, the role-play, the
narration) need filming.

- **Git and GitHub.** The folder is now a git repository, public on GitHub. `.gitattributes`
  keeps the Mac `.command` launchers at Unix line endings, because bash refuses Windows ones.
  Real voices (`demo/takes/`) and the generated clips stay out of git.
- **`tools/record_clips.py`** (or `make_video_bits.bat`) records the app's own scenes to MP4: the demo
  on the Live tab, the corner view, the Compare tab and a scroll through How it works.
  - It runs the real dashboard, with the real analysis, off-screen and silent.
  - The sound in each clip is exactly what the app analysed, so picture and sound match.
  - It draws at 150% scaling (a 1280 × 720 window filmed as 1920 × 1080) so the text is
    readable in a video.
  - With real takes in `demo/takes`, the Compare clip uses them.
- **`tools/make_cards.py`** makes the title, "Captions give the words. Not the voice.",
  evidence and end cards, plus see-through labels ("long pause", "quieter"...). It uses the
  app's colours and font. Missing test results show as `__ of __` in amber, so they can't be
  forgotten.
- **Captions:** `video/captions_narration.srt` (all the narration, timed to the plan's scene
  slots) and `video/captions_roleplay.srt` (the role-play lines, to be retimed).
- **`video/SHOOT_SHEET.md`:** one page covering who does what, what is already made, what still
  needs filming, and the checklist.

### Rejected alternatives
- **Filming the screen with OBS for every scene.** This needs a person at the laptop, it can
  catch notifications, and it has to be redone by hand whenever the app changes. OBS is still
  the plan for the live role-play and the review, because those need a real microphone.
- **Grabbing frames in real time.** Grabbing a whole 1080p window, with the corner view as
  well, only managed 11 new frames a second, so the line looked jerky. Instead the app runs in
  slow motion while it is filmed: `time.perf_counter` is replaced by a clock running at a third
  of the speed, and the silent file player waits on the same clock. That gives 27 to 29 new
  frames a second in clips that play at normal speed. Analysis, calibration and drawing are
  unchanged; only the wall clock they read is slowed.
- **Upscaling a 1920 × 1080 window.** The text came out too small to read in a video, and
  upscaling a smaller window blurs it. Qt's own scaling (`QT_SCALE_FACTOR=1.5`) draws sharp text
  at the larger size.

### Checked
- 122 tests pass before the commit.
- Stills from each clip: the Start card, then the grey line, then white after calibration, pauses
  shaded, amber in take C. At 50 s into the demo clip the session chip reads 0:47, which matches
  the 3-second lead-in, so the sound lines up with the picture.

### Open
- The real takes, the tests with people, consent, and who does each job are still not done or
  decided. `video/SHOOT_SHEET.md` has a table for the names.
- The team name and the test results, for the cards.


## 2026-10-10 (session 6): a walk-and-talk video script, and one clean screen

### The video
The team changed the format. Instead of a narrated screen recording, three presenters walk and
talk around school, straight to a phone camera, with the app recordings and labels laid on top in
the edit.
- **The script, shot list and filming notes** are in a shared Claude Doc, *Tone Visualiser: Stage
  1 video script*. It has ten scenes and about 600 words, so about 4 min 45 s.
- **Re-read the competition pages** (5 Oct update):
  - Stage 1 is a video explaining a conceptual design, judged by an expert panel, due Fri 23 Oct.
  - The site stresses co-design ("with disabled people, not for them"). So the script says plainly
    that the next step is to test it with Vikram and change it based on what he says.
  - The official length and format limits are not on the public pages (they may be behind the
    registered-user login). The doc asks the team to check.
- **Vikram's own words** from the Q&A, about clinical training relying on "verbal, tonal and
  auditory cues", anchor the barrier scene.

### Why the app felt hard to use
The user said it was "very difficult and weird to use", and the worst part was clutter. Looking at
the Live tab with fresh eyes showed:
- **The same voice drawn three times** (the display, the last minute per signal, the whole
  session), beside a 9-row key, a marks panel, 5 tabs, 9 buttons and 3 status chips.
- **Jargon:** baseline, recalibrate, freeze, corner view.
- **Twenty silent seconds after Start.** The app was learning the voice, but only a 12-pixel ring
  and the word "calibrating…" said so.
- **The line looked like scribbles on a big screen.** With 10 semitones filling half of a
  700-pixel plot, one semitone was about 34 px tall, while a syllable was only about 14 px wide
  (15 s across). Ordinary pitch movement inside a syllable became a tall vertical stroke.

### What changed
- **One clean Live screen:**
  - Start, the microphone and its level, then **Learn voice again**, **Mark** and **Mini window**.
  - Everything else is in one **More** menu: the demo, sound files, sessions, pause, the key, and
    the details.
  - The per-signal rows and the whole-session strip are now opt-in "details" (More, or Settings).
  - The key is cut to the five rows a first-time viewer needs. The full nine are in Help.
  - The marks panel appears only once there is a mark.
- **Three steps above the display:** *1 Start listening*, *2 Learning their usual voice… 40%*,
  *3 Watch how their voice changes*. The current step is outlined. While the voice is still being
  learned, a banner on the display says "keep talking normally", with a bar that fills.
- **Plain words:**
  - Review → **Look back**, Setup → **Settings**.
  - Recalibrate → **Learn voice again**, Freeze → **Pause the picture**, Corner view → **Mini
    window**.
  - Baseline → **usual voice** in the interface. "Baseline" stays in the code and in the
    glossary.
  - Help and Settings became icon tabs.
  - Every message, the Help page, the README and the command-line hints were updated to match.
- **An easier line** (main view only, so the mini window and the tests' views are unchanged):
  - At most 16 px per semitone (`MAX_PX_PER_SEMITONE`).
  - 10 s across instead of 15, so syllables are wider.
  - Smoothing over about 0.1 s (`LINE_SMOOTHING`) instead of a 3-point average.
  - Brighter, thicker joins inside phrases, so a phrase reads as one line.
  - A bigger "now" dot.
  - "↑ higher than usual / ↓ lower than usual" written beside the middle line.
  - Slightly lighter pause shading.

### Rejected alternatives
- **Hiding Look back and Compare behind a "simple mode" switch.** Two modes means two sets of
  instructions in the README and the video. One clean default, with opt-in details, is simpler.
- **Removing the per-signal rows altogether.** Supervisors may want them. They are kept, but off by
  default.
- **Words on the display, such as "louder" or "pause".** The brief says the live view is read from
  the corner of the eye, with no text while watching. The only words added are the two fixed axis
  labels and the temporary learning banner.

### Checked
- 129 tests pass (7 new: the clean default screen, the steps, the marks card, plain words, the
  capped scale, smoothing very short runs, the banner and axis words).
- Screenshots off-screen of the start, the learning state and a calibrated session: the line reads
  as curves rather than vertical scribbles.
- The classic `--file` window, `run_demo.py` and the README pictures (`tools/dashboard_screenshots.py`)
  were re-run. The video clips were re-recorded with the new screen.

### Open
- Someone who has not seen it before should try the new screen. The user's own verdict decides
  whether it is "easy" now.
- The official video length and format, from the registered-user area.
