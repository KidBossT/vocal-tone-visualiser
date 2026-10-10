# Filming plan: the Stage 1 video (about 5 minutes)

> **Replaced on 10 Oct 2026.** The video is now a walk-and-talk around school, presented by the team. The current script, shot list and filming notes are in the shared doc *Tone Visualiser: Stage 1 video script* (the link is in the team WhatsApp group). This file is kept for its background: the tests with people, consent and editing notes still apply.

**Deadlines.** Our own milestone: the demo filmed by **Mon 5 Oct**. Stage 1 video due **Fri 23 Oct**
(aim to submit by Wed 21 Oct).

**Stage 1 is judged as "conceptual design": the judges want the idea explained.** A working
prototype is not required, and ours works, so the video shows it working, live, early on.

**What the video has to show, in this order:**
1. The barrier (Vikram cannot hear tone of voice).
2. The idea: evidence, not a verdict.
3. How to read it (the same sentence spoken four ways).
4. That it really works, live, in a role-play, and afterwards in supervision.
5. That it was designed for a deaf user.
6. That it is honest about what it cannot do.
7. Evidence and next steps.

**One rule for everything anyone says or writes in the video:** describe what the display
*shows*, never what the person *feels*.

| Say | Never say |
|---|---|
| "her voice went higher and quieter" | "she got anxious" |
| "a long pause before she answered" | "she was hiding something" |
| "faster, louder, more pressed" | "she was angry" |
| "the app shows the evidence; Vikram decides what it means" | "the app detects / reads emotions" |
| "take A, take B" | "the calm take, the nervous take" |

---

## 1. Before filming day

### 1a. Record the real takes (about 20 minutes)
The synthetic voices sound robotic on camera. Record one real person (the "client" actor):
- one microphone, about 50 cm from their mouth;
- a quiet room;
- a USB or plug-in microphone if you have one (better than the laptop's own).

1. Double-click `run.bat`, open the **Compare** tab, press **Record your own takes…**
2. Choose the microphone. Say something: the level bar should reach the lighter zone.
3. Record each row. Press **Record**, the actor speaks, press **Stop**:

| Take | What they say | How they say it (the row in the app says the same) | Acting hint, for the actor only |
|---|---|---|---|
| **Baseline** | About 30 seconds about their week: college or work, travel, food, the weekend | Their ordinary way of talking | Relaxed and natural. Everything else is compared with this. |
| **A** | *"I've been sleeping better, and work has been fine this week."* | Even and steady | Just saying it. |
| **B** | the same sentence | Slowly, with long pauses (count to two in your head); let the ends of phrases rise, maybe an "um" | Unsure of what to say. |
| **C** | the same sentence | Fast and loud, pushing the words out | Irritated. |
| **D** | the same sentence | Flat and quiet, very little up and down | Worn out. |

4. Watch the display while each take records. Check:
   - B has shaded pause columns;
   - C has a thick line and the pace bar up;
   - D has a thin line hugging the middle.

   If a take doesn't show its difference, record it again and exaggerate a little. Recording
   again replaces the file.
5. Press **Compare them now**. From now on `run_demo.bat` and the Compare tab's **Use my
   recordings** use these files. They are saved in `demo\takes`.

### 1b. Test it with people, for numbers to put in the video (about 1 hour)
Judges trust "we tested it, and here is what happened" more than any claim. Use classmates or
family. Get their permission, and write down only first names or nothing. The app saves no
sound unless you record on purpose.

**Test 1: sound off, can you tell the takes apart?**
1. Open Compare with your real takes and press **Show all at once**. No sound.
2. Give the person four cards: *"even"*, *"slow, with long pauses"*, *"fast and loud"*, *"flat and
   quiet"*.
3. Show them the **How it works** tab for 2 minutes first, or nothing (note which).
4. Ask them to put each card on a panel.
5. Record how many they get right out of 4, and how long they took.

**Test 2: from the corner of the eye**
1. Someone reads a short passage aloud. They change their voice at moments you planned in secret:
   a 3-second pause, suddenly louder, speeding up, going quiet.
2. The tester sits facing them, wears earplugs, and watches their face, with the corner view on a
   laptop to one side.
3. The tester raises a hand whenever they notice a change on the display.
4. Record how many of the planned changes they caught.

**Test 3: any voice**
1. A deep voice and a high voice each record a baseline and the same take.
2. After each has calibrated, the shapes should look alike.
3. Screenshot both.

**Results table (copy it into the video and the Stage 2 portfolio):**

| Test | People | Result | Notes |
|---|---|---|---|
| 1 Sound off (no guide) | | __ of __ matched all 4 | |
| 1 Sound off (2 min with the guide) | | __ of __ matched all 4 | |
| 2 Corner of the eye | | __ of __ changes noticed | |
| 3 Any voice | 2 | shapes alike? yes / no | |

**If you can reach Vikram, or any deaf or hard-of-hearing person, even 15 minutes with the corner
view is worth more than any feature.** Hackcessible is about designing *with* the challenger.
Ask:
- what they can read from the corner of their eye;
- what is confusing;
- what they would change.

Write their words down exactly, with permission.

### 1c. Consent
- Everyone who appears or is heard in the video agrees in writing.
- Anyone under 18 needs a parent or guardian's consent too.
- Check the competition's rules about filming people and sharing the video.
- Use first names only.

### 1d. Equipment checklist

| Item | Why |
|---|---|
| The laptop, charged, with the app set up (`setup.bat`) | Everything runs on it |
| USB or plug-in microphone | Cleaner sound than the laptop's own microphone |
| Phone and tripod (or a stack of books) | The camera for faces |
| A lamp or a window **in front of** the actors | Faces must be well lit for lip reading |
| OBS Studio (free, obsproject.com), installed and tested | Records the laptop screen |
| Clipchamp (built into Windows 11) or DaVinci Resolve (free) | Editing and captions |
| A quiet room: fans off, door shut, phones on silent | Noise adds stray strokes |
| Printed copies of this plan and the role-play lines | Everyone knows their part |

---

## 2. Setting up on filming day

**Laptop (15 minutes before):**
1. Windows: turn on **Do not disturb** (Settings > System > Notifications). Close every other app,
   especially call apps and voice changers: they can grab the microphone.
2. Double-click `run.bat`. In **Setup**, choose the USB microphone. The app remembers it.
3. Check:
   - **Show numbers** is off;
   - **Show the key and marks** is on (it helps viewers learn the display);
   - the live view shows 15 s.
4. Press **Try the demo recording** once, to check that everything works.

**OBS (screen recording):**
1. Settings > Video: Base and Output resolution **1920 × 1080**, **30 fps**.
2. Settings > Output: Recording format **MP4**, Recording quality **High Quality, Medium File
   Size**.
3. Sources:
   - **Display Capture** (the whole screen, so the corner view shows too);
   - **Desktop Audio** on for the comparison scene (so the takes are heard);
   - **Mic/Aux** set to the **same USB microphone** for the role-play, so the video's sound is
     exactly what the app heard. Windows lets both apps use it at once.
4. Record 10 seconds and play it back: is the text sharp and the sound clear?

**Phone camera:**
- Landscape, 1080p, 30 fps, on the tripod at the actors' eye level.
- Tap and hold on a face to lock focus and exposure.
- Frame the client's head and shoulders, face fully visible (no hands near the mouth, no strong
  light behind them).

**Syncing the two recordings.** At the start of every take, the client says a sharp **"ba!"**
once. It shows as a spike in both sound tracks and as a dot and a tick on the display, so the
screen recording and the phone video can be lined up in the editor. Don't clap: a clap has no
pitch, so the display does not show it.

---

## 3. The scenes

Timings add up to about 4:50. At about 140 words a minute, each scene's narration fits its
slot. Record the narration separately at the end, in the quiet room, with the USB microphone.

### Scene 1: What you can't hear (0:00 to 0:25)
- **Purpose:** hearing viewers feel the barrier before they hear about it.
- **Shot:** the phone, close on the client's face. They say, the B way (slow, long pauses,
  rising): *"I'm fine... Work's been... fine."*
- **In the edit:**
  1. Play it with **no sound**, captions only: *"I'm fine. Work's been fine."* Hold for about
     8 seconds.
  2. On-screen text: **"Captions give the words. Not the voice."**
- **Narration** (over a black card or the face, about 25 words): *"For Vikram, a deaf psychology
  student, every client sounds like this. The words arrive. How they were said doesn't."*

### Scene 2: The barrier (0:25 to 0:55)
- **Purpose:** the challenger and the need, in his terms.
- **Plan A:** a short clip or quote from Vikram himself (with permission).
- **Plan B:** a team member on camera, or on-screen text over simple visuals: a lecture, a
  role-play.
- **Narration** (about 65 words): *"Vikram lip-reads and uses Indian Sign Language. Captions can
  give him the words. But trainee psychologists are also taught to notice* how *something is said:
  a pause before an answer, a voice that goes quiet or tight. That channel is closed to him. His
  challenge asked for a tool that shows vocal tone in real time, during supervised practice. So
  we built one."*

### Scene 3: The idea, evidence not a verdict (0:55 to 1:20)
- **Shot:** screen recording.
  1. The dashboard opening on the **Start here** card.
  2. Press **Try the demo recording**; let it run about 10 seconds. Viewers see the grey line
     and the "Learning this voice" ring.
- **Edit:** highlight the line at the bottom of the display: *"Shows vocal features only.
  Interpretation is yours."*
- **Narration** (about 60 words): *"It shows five things about a voice: pitch, loudness, pauses,
  pace and voice quality. It always compares a person with their own usual voice, which it learns
  in the first twenty seconds, so a naturally quiet or deep voice isn't a finding. It never names
  an emotion. It shows the evidence, and the judgement stays with Vikram."*

### Scene 4: How to read it, the same sentence four ways (1:20 to 2:30)
- **Shot:** screen recording of the **Compare** tab, full screen (F11), with your real takes.
  Press **Play with sound** and let all four panels fill in (about 40 seconds). Keep Desktop
  Audio on, so hearing judges hear each take.
- **Edit:** after it plays, zoom into each panel in turn, with an arrow or a circle on what the
  narration names.
- **Narration** (about 110 words, over the zooms):
  - **A:** *"Take A: the line stays around her usual middle, white, with even syllable ticks."*
  - **B:** *"Take B: these shaded columns are pauses of more than a second, darker the longer
    they last. The line sits higher and rises at the ends."*
  - **C:** *"Take C: a thick, bright line, which means louder. The ticks are packed together
    and the pace bar is up, which means faster. And amber: her voice is more pressed than her
    usual."*
  - **D:** *"Take D: thin, dim and hugging the middle, which means quieter and flatter. And blue:
    softer and breathier."*
  - **Close:** *"Same words, four different voices. The app doesn't say what any of them means.
    It shows what changed."*

### Scene 5: Live, a role-play (2:30 to 3:35)
- **Purpose:** proof that it works live, in the real situation it was designed for.
- **Label it on screen as an acted role-play.**
- **People:** the client (the actor from the takes), the trainee, and the supervisor at the
  laptop.
- **Set-up:**
  - The two actors face each other.
  - The USB microphone sits in front of the client, closer to them than to the trainee.
  - The laptop, turned towards the camera, shows the **Live** tab. Or open the **corner view** and
    put it beside a picture of the client's face, if you want to show how Vikram would use it.
- **Recording:**
  - Record with OBS and the phone at the same time.
  - The phone frames both actors, with the laptop screen visible if possible.
- **Steps:**
  1. Start OBS and the phone. The client says "ba!".
  2. The supervisor presses **Start listening**.
  3. The trainee opens the conversation. As soon as the client starts talking, the supervisor
     presses **Recalibrate**.
  4. The client talks normally for about 25 seconds (lines below). Wait until the grey line turns
     white and the label says **Knows this voice**.
  5. Carry on with the lines. At the pause after the question about home, the supervisor presses
     **N** and types *question about home*, then Enter. At the exams answer, press **M**.
  6. Press **Stop**. Keep the app open for Scene 6.
- **The lines** (acted; improvise around them):
  - **Trainee:** "Thanks for coming in. How's your week been?"
  - **Client** (ordinary, about 25 s): "It's been all right, actually. I've been taking the bus to
    college, it's slow but I read on the way. On Saturday I met a couple of friends and we tried
    a new place for dosa, which was really good..." (keep going naturally)
  - **Trainee:** "And how have things been at home?"
  - **Client** (a long pause of about 2 s, then quieter, flatter, slower): "...It's been... fine.
    Everyone's just busy, I suppose."
  - **Trainee:** "What about your exams?"
  - **Client** (faster, louder, pushing the words out): "Oh, exams are fine, I've got it all
    planned, there's nothing to worry about, honestly, it's all under control."
  - **Trainee:** "It sounds like there's a lot going on right now."
- **Edit:**
  - Put the screen recording large, with the actors' faces as an inset in a corner.
  - Caption all the dialogue.
  - Add small labels as things appear: "long pause", "quieter", "faster and louder".
  - **No narration over the key moment**: let viewers read the display themselves.

### Scene 6: The supervision debrief (3:35 to 4:05)
- **Shot:** screen recording of the **Review** tab right after the role-play.
  1. Show the **What changed** list, and click the entry just after the question about home.
  2. Show the mark with its note.
  3. Select the ordinary talk, **Set as A**; select the answer about home, **Set as B**;
     **Compare A with B**.
- **Narration** (about 65 words): *"Afterwards, the supervisor and Vikram look back together.
  The app lists where the voice stayed away from its usual: here, a long pause and a quieter,
  flatter answer, just after the question about home. It describes the voice, never the person.
  Deciding what that means, and whether to gently ask about it, is Vikram's job, the same as for
  any trainee."*

### Scene 7: Designed for a deaf user (4:05 to 4:25)
- **Shot:**
  - the **How to read it** key, close up;
  - then scroll through **How it works** (the example pictures);
  - then the corner view at the edge of the screen.
- **Narration** (about 50 words): *"It's made to be read from the corner of the eye while
  lip-reading: shape, thickness, brightness and colour, with no text and no numbers while you
  watch. Every rule is 'more is up, thicker or brighter'. Blue and amber stay distinct for
  colour-blind viewers, and nothing flashes."*

### Scene 8: Honest limits (4:25 to 4:40)
- **Shot:** `docs\img\failures.png`, or live: two people talking at once, then a voice played
  through a phone speaker (the line turns amber).
- **Narration** (about 40 words): *"It has limits, and we show them. Two people talking at once
  get mixed together. A voice through a small speaker looks falsely pressed. Whispers have no
  pitch at all. Knowing where it fails is part of using it well."*

### Scene 9: Evidence and next steps (4:40 to 4:55)
- **Shot:** one evidence card (a slide) with:
  - **about 70 ms** from voice to screen;
  - the voice-quality measure **chosen by a measured comparison** of four candidates;
  - **122 automated tests**, including one that fails if the app ever uses an emotion word;
  - **offline, saves no sound**;
  - **your Test 1 and Test 2 results**.
- **Then:** an end card with the team name, *Hackcessible India 2026, Vikram's challenge*, and
  *Evidence, not verdict.*
- **Narration** (about 45 words): *"It runs on an ordinary laptop, offline, and saves no sound.
  Next, in Stage 2, we want to test it with Vikram in real supervised role-plays, and add a second
  microphone so it shows only the client's voice."*

---

## 4. Editing and captions

1. **Assemble:** put the scenes in order in Clipchamp or DaVinci Resolve. Line up each phone
   clip with its screen recording using the "ba!" spike.
2. **Captions are required, not optional:** the challenger is deaf, and so may some judges be.
   - Use **burned-in (open) captions** for all speech, so they are always visible.
   - Big, high contrast, bottom centre, at most two lines.
   - Clipchamp can generate them automatically; **correct every line by hand**.
   - Optional, and valued: an ISL interpreter in a corner of the frame, if the team can arrange
     one.
3. **Labels:**
   - Keep them short ("long pause", "louder").
   - Put them on the display, near what they point at.
   - No emotion words (see the table at the top).
4. **Music:** none under the demo scenes. Viewers must be able to hear the takes, and caption
   readers lose nothing.
5. **Export:** MP4 (H.264), 1920 × 1080, 30 fps. Check the competition's length and format
   rules before exporting.
6. **The Vikram check.** Watch the whole video with the **sound off**. Does it still make sense
   from the captions and the pictures alone? If not, fix it before submitting.

---

## 5. If something goes wrong on the day

| Problem | Fix |
|---|---|
| No line when someone talks | Check the microphone next to **Start listening** and that the level bar moves. In Setup, press **Refresh** after plugging a microphone in. |
| Stuck on "Learning this voice" | It needs about 15 s of *voice*. Keep talking, a little closer to the microphone. |
| The wrong person got learned | Press **Recalibrate** when the client starts talking. |
| Amber for no reason | Is the voice coming out of a speaker? Is a fan or a TV on? (README, section 9) |
| Text too small in the recording | Press **F11** for full screen; record at 1920 × 1080. |
| The live part fails completely | The comparison (Compare tab, or `run_demo.bat`) and **Try the demo recording** run from files, so they work even if the microphone doesn't. |
| A take looks wrong | Record it again in **Record your own takes**. It replaces the file. |

---

## 6. Timeline

| When | What |
|---|---|
| By Fri 2 Oct | Record the real takes (1a); run the tests (1b); collect consent (1c); rehearse the role-play twice |
| Sat 3 or Sun 4 Oct | Filming day (the other day is the spare) |
| Mon 5 Oct | Milestone: the demo is on camera |
| 6 to 16 Oct | Edit, caption, show it to a teacher or mentor, re-shoot anything weak |
| 17 to 20 Oct | The Vikram check (sound off); length and format check |
| Wed 21 Oct | Submit (two days' buffer before Fri 23 Oct) |
