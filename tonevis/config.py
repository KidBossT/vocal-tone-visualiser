"""Every tunable number in one place.

The README's "What you see" section describes these same mappings in plain English,
so if you change a value here, update the README too.
"""

# ---- Sound in --------------------------------------------------------------------------------
ANALYSIS_RATE = 16_000    # Hz. All sound is converted to this rate before analysis; speech
                          # pitch, loudness and spectral balance all sit below 8 kHz.
BLOCK_SECONDS = 0.010     # the sound card hands over audio in 10 ms blocks
INPUT_LATENCY = 0.020     # s of microphone buffering requested. Smaller risks dropouts when
                          # Python is busy drawing; 20 ms costs little of the 300 ms budget.
OUTPUT_LATENCY = 0.050    # s of playback buffering in --file mode (a dropout would be audible
                          # on camera; the display waits for the sound, so sync is unaffected)

HIGH_PASS_HZ = 50.0       # Hz. Removes DC offset (some microphones add one, and it reads as
                          # sound during silence) and rumble below the lowest voice pitch

# ---- Pitch (F0) ------------------------------------------------------------------------------
FRAME_STEP = 0.010        # s between pitch values (100 per second)
HOP = 0.020               # s between analysis runs; each run adds two new pitch values
ANALYSIS_WINDOW = 0.200   # s of audio given to Praat per run. Must be a whole number of HOPs.
                          # The extra context helps Praat's path-finder avoid octave jumps.
PITCH_FLOOR = 70.0        # Hz. Lowest pitch looked for before calibration. Also sets Praat's
                          # analysis window (3 periods = 43 ms), so the newest value is 25 ms old.
PITCH_CEILING = 500.0     # Hz. Highest pitch looked for before calibration
VOICING_THRESHOLD = 0.45  # Praat default: how periodic a frame must be to count as voiced
SILENCE_THRESHOLD = 0.03  # Praat default: frames this quiet relative to the loudest moment
                          # in the analysed 200 ms count as unvoiced
LEVEL_WINDOW = 0.025      # s of audio used to measure each frame's level

# Noise gate: a frame can only count as voiced if it is clearly louder than the background.
# Stops mains hum or a fan being drawn as pitch (hum is strongly periodic, so Praat alone
# would call it voiced; on test it was 5-6 dB above its own quietest moments).
NOISE_FLOOR_START_DB = -60.0       # first guess at the background level (dB below full scale)
NOISE_FLOOR_RISE_DB_PER_S = 1.0    # the estimate drops instantly to any quieter frame and
                                   # rises only this fast, so speech cannot drag it up
GATE_DB_ABOVE_FLOOR = 10.0         # voiced frames must be at least this far above the background
ABSOLUTE_GATE_DB = -80.0           # ...and louder than this in absolute terms
MIN_VOICED_FRAMES = 5              # voiced stretches shorter than this (50 ms) are not drawn:
                                   # real syllables last longer; shorter blips are mostly noise

# ---- Loudness --------------------------------------------------------------------------------
LOUDNESS_ATTACK = 0.02    # s: smoothed loudness follows a rise within about 20 ms...
LOUDNESS_RELEASE = 0.15   # s: ...and lets go more slowly, so each syllable reads as one shape
LOUDNESS_RANGE_DB = (-15.0, 12.0)  # dB from the speaker's typical level: thinnest .. thickest

# ---- Pauses ----------------------------------------------------------------------------------
SPEECH_DB_ABOVE_FLOOR = 6.0     # sound within 6 dB of the background counts as silence...
SPEECH_DB_BELOW_TYPICAL = 25.0  # ...and so does anything 25 dB below the speaker's typical
                                # level (breaths, a far-off room), as in de Jong & Wempe (2009)
SPEECH_MIN_VOICED = 3     # frames: a voiced stretch must last 30 ms to count as someone speaking
SPEECH_HANGOVER = 0.3     # s: unvoiced sound (consonants) counts as speech only this close
                          # after voicing, so fans, clicks and a laptop mic's noise bursts
                          # never count as speaking time or break a pause
PAUSE_MIN = 0.25          # s of silence before it counts as a pause (the usual cut-off since
                          # Goldman-Eisler; shorter silences are mostly consonants)
LONG_PAUSE = 1.0          # s: pauses this long are highlighted
PAUSE_STEPS = (1.0, 2.0, 3.0)   # s: the highlight gets stronger at each step
BRIDGE_MAX = 0.25         # s: gaps in the pitch line shorter than this, inside speech, are
                          # joined with a thin line, so that only real pauses show as gaps

# ---- Pace (speaking rate) --------------------------------------------------------------------
NUCLEUS_DIP_DB = 2.0      # a syllable is a loudness peak standing 2 dB above the dips either
                          # side of it, with voice at the peak (de Jong & Wempe 2009)
NUCLEUS_MAX_DB_BELOW_TYPICAL = 18.0  # and no quieter than this below the typical level
RATE_WINDOW = 4.0         # s of speaking time (pauses excluded) the pace is measured over
RATE_MIN_SPEECH = 1.5     # s of speaking time needed before a pace is shown
PACE_FULL_SCALE = 0.6     # the pace bar is full at 2^0.6 = 1.5x faster (or 1/1.5 slower)
                          # than the speaker's usual pace

# ---- Tension proxy: spectral tilt ------------------------------------------------------------
# Chosen over jitter and shimmer after a measured comparison (tools/tension_bakeoff.py; the
# numbers are in BUILD_LOG.md): it ignores volume and intonation, is least disturbed by room
# echo and noise, and moves most with voice quality.
TILT_LOW_BAND = (50.0, 1000.0)     # Hz
TILT_HIGH_BAND = (1000.0, 5000.0)  # Hz (the "alpha ratio" of eGeMAPS)
TILT_FRAME = 512          # samples (32 ms) per spectrum
TILT_FRAMES = 150         # the measure pools the spectra of the last 150 voiced frames (1.5 s)
TILT_MIN_FRAMES = 20      # ...and needs at least 20 before it says anything
TILT_DEAD_ZONE_DB = 1.0   # changes smaller than this from the baseline leave the colour neutral
TILT_FULL_SCALE_DB = 5.0  # a change this big gives the full colour

# ---- Calibration -----------------------------------------------------------------------------
CALIBRATION_SPEECH_SECONDS = 15.0  # seconds of the person actually speaking (pauses not
                                   # counted); usually about 20-25 s of conversation
USUAL_RANGE_PERCENTILES = (10, 90) # the faint "usual range" band around the centre line
PITCH_FLOOR_FACTOR = 0.75          # after calibration, look for pitch from 0.75 x the speaker's
PITCH_CEILING_FACTOR = 2.0         # lower quartile to 2 x their upper quartile (after Hirst's
                                   # two-pass method); cuts octave errors and stray voices
TARGET_GATE_DB = 30.0              # after calibration, voiced sound more than 30 dB below the
                                   # speaker's typical level is treated as background

# ---- Evidence in words (the dashboard's review) ----------------------------------------------
# How far a stretch of speech must be from the speaker's baseline before the dashboard describes
# it as different. Each sits well above that measure's ordinary wobble (see BUILD_LOG.md), so
# steady speech reads "much as usual". The words describe the voice, never a feeling.
EVIDENCE_PITCH_ST = 1.5            # median pitch this far from the usual middle: higher / lower
EVIDENCE_SPREAD_RATIO = (0.7, 1.3) # pitch movement vs the usual range: flatter / more up-and-down
EVIDENCE_LOUDNESS_DB = 4.0         # louder / quieter
EVIDENCE_PACE_RATIO = (0.87, 1.15) # slower / faster
EVIDENCE_TILT_DB = 1.5             # more pressed / softer or breathier
EVIDENCE_MIN_SPEECH = 2.0          # s of speech a stretch needs before anything is said about it
CHANGE_SPEECH = 3.0                # "what changed" looks at the last 3 s of *speaking* each time
CHANGE_SPEECH_PACE = 6.0           # (6 s for pace: syllable counts in 3 s wobble by about 20 %)
CHANGE_MAX_SPAN = 15.0             # (reaching back at most 15 s, so hesitant speech still counts),
CHANGE_STEP = 1.0                  # every second,
CHANGE_MIN_WINDOWS = 3             # and reports a change only if 3 windows in a row agree
CHANGE_LONG_PAUSE = 3.0            # s: pauses this long are listed on their own

# ---- Display ---------------------------------------------------------------------------------
HISTORY_SECONDS = 10.0    # the window shows the last 10 s; newest sound at the right edge
MAX_PX_PER_SEMITONE = 16.0  # px: on a big display, one semitone is never taller than this,
                          # so a syllable reads as a curve, not a tall vertical scribble
SEMITONE_RANGE = 10.0     # semitones from the centre line to the top (and to the bottom) edge.
                          # Everyday speech moves about 2-6 semitones either side of its middle.
REFERENCE_SECONDS = 20.0  # before calibration finishes, the centre line is the median pitch of
                          # the voiced sound in the last 20 s
FPS = 60                  # redraws per second
STALL_SECONDS = 1.5       # warn if the microphone sends nothing for this long
WINDOW_SIZE = (400, 250)  # starting size; the window is resizable
MIN_WINDOW_SIZE = (300, 190)
RIBBON_WIDTH = (2.5, 13.0)        # px: line thickness at the quiet and the loud end
RIBBON_BRIGHTNESS = (0.5, 1.0)    # line brightness at the quiet and the loud end
BRIDGE_WIDTH = 2.5        # px: the join across short unvoiced gaps, so a phrase reads as
                          # one line and only real pauses show as gaps
GLOW_EXTRA = 6.0          # px: soft glow drawn behind the line
NOW_DOT_RADIUS = 6.0      # px; the dot marking the newest voiced sound
NOW_DOT_MAX_AGE = 0.25    # s; the dot shows only while the voiced sound is this recent
PACE_BAR_WIDTH = 10.0     # px
RHYTHM_LANE = 10.0        # px: height of the syllable-tick lane under the line
FADE_FRACTION = 0.12      # the oldest 12% of the window fades into the background
LINE_SMOOTHING = 0.10     # s: the pitch line is averaged over about this long, so it reads as
                          # a smooth curve rather than a jittery scribble

# Colours (dark theme). The tension colours are blue and amber: they stay distinct for the
# common kinds of colour blindness, and there is deliberately no red.
BACKGROUND = "#0E1116"
CENTRE_LINE = "#323B4B"
USUAL_BAND = (255, 255, 255, 10)          # RGBA
NEUTRAL = "#E6EAF2"                        # the line at the speaker's usual voice quality
WARM = "#FFB24A"                           # relatively more high-frequency energy (pressed)
COOL = "#5EA8FF"                           # relatively less (soft, breathy)
CALIBRATING_LINE = "#9AA3B2"               # the line is grey until calibration finishes
OFF_SCALE_MARK = "#5C6678"                 # faint mark at the edge where pitch left the scale
PAUSE_FILL = (255, 255, 255, (12, 22, 34))  # RGB + alpha at each PAUSE_STEPS level
RHYTHM_TICK = "#8E99AC"
PACE_TRACK = "#1B212B"
PACE_FILL = "#CDD5E3"
PACE_NOTCH = "#6B7588"
DIM_TEXT = "#7A8699"

DISCLAIMER = "Shows vocal features only. Interpretation is yours."
