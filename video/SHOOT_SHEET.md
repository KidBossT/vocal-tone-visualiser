# Shoot sheet: the Stage 1 video (one page)

The full plan, with every scene's narration, is in [`demo/DEMO_SCRIPT.md`](../demo/DEMO_SCRIPT.md).
This page covers who does what, and what is already made.

**Dates:** film **Sat 3 or Sun 4 Oct** (the other day is the spare) · demo on camera by **Mon 5 Oct** ·
edit 6 to 20 Oct · submit **Wed 21 Oct** (the deadline is Fri 23 Oct).

## Who does what (put names in)

| Job | Who | Notes |
|---|---|---|
| Client (actor) | | Records the takes, Scene 1's face, and the role-play |
| Trainee (actor) | | Role-play only |
| Supervisor, at the laptop | | Start listening, Recalibrate, N for a note, M for a mark |
| Camera and OBS | | Phone on a tripod, and OBS on the laptop |
| Narration voice | | Recorded at the end, in a quiet room, with the USB microphone |
| Editor and captions | | Clipchamp or DaVinci Resolve |

Everyone who is seen or heard signs a consent form, and anyone under 18 also needs a parent's
signature. Use first names only.

## Already made: no camera needed

Double-click **`make_video_bits.bat`** (about 8 minutes). Nothing pops up and nothing plays aloud. It
writes:

| Scene | File | What it is |
|---|---|---|
| 1 | `video/cards/02_captions_not_voice*.png` | "Captions give the words. Not the voice." (a card, and an overlay for the face) |
| 3 | `video/clips/scene3_demo_live.mp4` | The Start card, then the demo recording on the Live tab, with sound |
| 4 | `video/clips/scene4_compare.mp4` | The same sentence four ways, with sound |
| 7 | `video/clips/scene7_guide.mp4`, `scene7_corner_view.mp4` | Scrolling How it works; the corner view during the demo |
| 8 | `docs/img/failures.png` | Where it goes wrong |
| 9 | `video/cards/03_evidence.png`, `04_end.png` | The evidence card and the end card |
| any | `video/cards/label_*.png` | On-screen labels ("long pause", "quieter"...), with see-through backgrounds |
| all | `video/captions_narration.srt`, `captions_roleplay.srt` | All the spoken words as captions. Timings are rough, so slide them to match. |

**The demo clips use synthetic voices until real takes exist.** Once the client has recorded
the takes (step 1 below), run `make_video_bits.bat` again: the Compare clip then uses the real voice.
Fill in the test results and the team name on the cards with:
`.venv\Scripts\python.exe tools\make_cards.py --team "Our team" --test1 "5 of 6" --test2 "10 of 12"`

## Still needs filming

1. **The real takes (20 min, before filming day).** `run.bat` > Compare > **Record your own takes**.
   This records the baseline plus takes A to D of *"I've been sleeping better, and work has been fine
   this week."*: A even, B slow with long pauses, C fast and loud, D flat and quiet.
2. **The tests with people (1 hour).** Test 1 (sound off, match the four takes) and Test 2 (notice
   changes from the corner of the eye). Their numbers go on the evidence card.
3. **Scene 1 (5 min).** The phone, close on the client's face, saying the B way: *"I'm fine...
   Work's been... fine."*
4. **Scene 5, the role-play (rehearse twice, then 3 or 4 takes).** OBS and the phone at the same
   time. The client says **"ba!"** first, so the recordings can be lined up. The lines are in
   DEMO_SCRIPT.md, Scene 5.
5. **Scene 6, the review (straight after a good role-play).** OBS on the Review tab: the What
   changed list, the mark, then Set as A / Set as B / Compare.
6. **Scene 2 (optional).** A team member on camera, or a quote from Vikram if we can reach him.
7. **Narration.** Read each scene's lines from DEMO_SCRIPT.md, in a quiet room.

## Filming-day checklist

- [ ] Laptop charged, Do not disturb on, every other app closed
- [ ] USB microphone chosen in Setup; "Show numbers" off; the key on
- [ ] Phone landscape at 1080p 30 fps, on a tripod, focus locked on the face
- [ ] A lamp or window **in front of** the actors (for lip reading)
- [ ] Fans off, door shut, phones silent
- [ ] OBS: 1920 × 1080, 30 fps, MP4; a 10-second test recording played back
- [ ] Consent forms signed

## One rule for everything said or written

Describe what the display **shows**, never what the person **feels**. Say "her voice went higher
and quieter", never "she got anxious". Say "take A, take B", never "the calm take".
