# Media inputs and outputs
VIDEO = "src/files/pov_seb.mp4"
VIDEO2 = "src/files/pov_gus.mp4"
AUDIO1 = "src/files/pod1_seb.mp3"
AUDIO2 = "src/files/pod1_gus.mp3"
OUTPUT = "Synced_video.mp4"
CUTS_JSON = "test_synced_merged_cuts.json"

# Sync analysis
ANALYSIS_SECONDS = 300
ANALYSIS_SAMPLE_RATE = 8000
ENVELOPE_RATE = 100
MAX_SYNC_OFFSET_SECONDS = 120
MIN_OVERLAP_SECONDS = 30
MIN_CORRELATION = 0.20

# Render output
OUTPUT_AUDIO_RATE = 48000
OUTPUT_FPS = 30

# Loudness check and processing
TARGET_LUFS = -16.0
TARGET_TRUE_PEAK = -1.0
LOUDNESS_TOLERANCE_LU = 1.0

# Podcast voice processing (starting values; tune for your recordings)
GATE_THRESHOLD = 0.01
GATE_RATIO = 2
GATE_ATTACK_MS = 10
GATE_RELEASE_MS = 150
GATE_RANGE = 0.1
COMPRESSOR_THRESHOLD = 0.125
COMPRESSOR_RATIO = 3
COMPRESSOR_ATTACK_MS = 10
COMPRESSOR_RELEASE_MS = 100
COMPRESSOR_MAKEUP = 1

# Activity-driven camera selection
ACTIVITY_FLOOR_DBFS = -42.0
ACTIVITY_ABOVE_NOISE_DB = 10.0
MIN_ACTIVITY_SECONDS = 0.25
MAX_SILENCE_GAP_SECONDS = 0.20
