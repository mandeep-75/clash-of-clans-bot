# =============================================================================
# CONFIGURATION
# =============================================================================

# Screenshot filename (used for all template matching)
SCREENSHOT_NAME = "screen.png"

# Log file for session tracking
LOG_FILE = "bot_session_log.txt"

# Tap jitter: each tap lands randomly within ± this many pixels (0-5 px)
TAP_OFFSET_MAX = 3

# =============================================================================
# DETECTION
# =============================================================================
# Minimum template match confidence (0.0-1.0)
MATCH_THRESHOLD = 0.8

# Seconds between button polls while waiting for a button to appear
BUTTON_POLL_INTERVAL = 1

# =============================================================================
# DEVICE / SUBPROCESS
# =============================================================================
# Timeout (seconds) for every adb subprocess call
ADB_TIMEOUT = 5

# Number of consecutive device failures (tap / screenshot / health check)
# before the bot gives up and stops instead of silently looping forever.
MAX_CONSECUTIVE_FAILURES = 5

# =============================================================================
# CLICK CONTROL - top-level control over every tap (see utils/click_controller.py)
# =============================================================================
# Set False to globally disable every click (dry-run mode: detects but never taps)
CLICK_ENABLED = True
# Seconds to pause after each tap (human-like pacing; larger = slower, safer)
CLICK_DELAY = 0.05
# Finger-down duration per tap (seconds): random within this small range
TAP_HOLD_MIN = 0.05
TAP_HOLD_MAX = 0.15
# Path to log every click (leave empty to disable click logging)
CLICK_LOG = ""

# =============================================================================
# TIMEOUTS (in seconds)
# =============================================================================
RETURN_HOME_TIMEOUT = 210  # Maximum time to wait for return home button after battle

# Seconds between polls when continuously checking for event tap button during battle
EVENT_TAP_POLL_INTERVAL = 0.5

# Max times to dismiss event tap popups before giving up
MAX_EVENT_TAPS = 3

# =============================================================================
# BASE EVALUATION (resource thresholds for attack/skip decision)
# =============================================================================
# Minimum available loot to attack a base
MIN_GOLD = 800000
MIN_ELIXIR = 800000
MIN_DARK_ELIXIR = 0  # Set to 0 to ignore dark elixir
# OCR language for resource detection
OCR_LANGUAGES = ["en"]
# Separate bounding boxes for each resource (x, y, w, h)
GOLD_CROP_REGION = (64, 95, 140, 35)
ELIXIR_CROP_REGION = (64, 135, 140, 35)
DARK_ELIXIR_CROP_REGION = (64, 170, 140, 35)

# =============================================================================
# FLOW PACING (sleeps between bot actions)
# =============================================================================
# Wait for the unit-selection UI to appear after picking a troop/spell/hero
SELECTION_UI_DELAY = 0.15
# Pause after reaching the attack screen and after tapping Attack
POST_ATTACK_SLEEP = 1
# Pause after pinch-zooming at battle start
POST_ZOOM_SLEEP = 0.5
# Pause after tapping Return Home (wait for the battle-end dialog)
RETURN_HOME_TAP_SLEEP = 1
# Range of random pauses between "Next" base searches
SEARCH_NEXT_SLEEP_RANGE = (2, 3)
# Range of random delays (seconds) between hero ability activations
ABILITY_DELAY_RANGE = (1.0, 2.0)

# =============================================================================
# ARMY COMPOSITION
# =============================================================================
# Each unit is a dict of templates/<type>/<folder-name> -> count to deploy.
# Folder name must match the template folder under templates/troops,
# templates/hero, or templates/spells.

# Available troops: ballon, dragon, super_minion, valkyrie
SELECTED_TROOPS = {
    "super_minion": 26,
}

# Available spells: heal, rage
SELECTED_SPELLS = {
    "rage": 6,
}

# Available heroes: archer_queen, barbarian_king, grand_warden,
#                   minion_prince, rolaychampion
SELECTED_HEROES = {
    "barbarian_king": 1,
    "archer_queen": 1,
    "grand_warden": 1,
    "minion_prince": 1,
    "rolaychampion": 1,
}
# =============================================================================
# DEPLOYMENT COORDINATES
# =============================================================================

TROOP_LOCATIONS = [
    (151, 409),
    (200, 379),
    (236, 353),
    (263, 344),
    (288, 313),
    (323, 287),
    (353, 264),
    (381, 243),
    (411, 221),
    (433, 203),
    (469, 175),
    (492, 161),
    (536, 133),
    (559, 108),
    (588, 89),
    (619, 69),
    (557, 105),
    (517, 133),
    (479, 164),
    (431, 197),
    (407, 221),
    (369, 253),
    (341, 271),
    (299, 303),
    (263, 331),
    (225, 355),
    (171, 401),
    (147, 416),
    (199, 373),
    (239, 344),
    (281, 324),
    (337, 287),
    (392, 240),
    (433, 201),
    (503, 173),
]

SPELL_LOCATIONS = [
    (408, 399),
    (455, 352),
    (528, 319),
    (595, 273),
    (712, 276),
    (645, 357),
    (539, 415),
]

HERO_LOCATIONS = [
    (431, 197),
    (407, 221),
    (369, 253),
    (341, 271),
    (299, 303),
    (263, 331),
]

# =============================================================================
# SCRCPY CONTROL
# =============================================================================

# scrcpy server / tunnel settings
SCRCPY_PORT = 27183  # Local TCP port for the adb reverse tunnel
SCRCPY_SCID = 0x00000001  # Session id -> device socket "scrcpy_00000001"
SCRCPY_SERVER_VERSION = "4.1"  # Must match the scrcpy-server.jar version
SCRCPY_SERVER_JAR = "scrcpy-server.jar"  # Local path to the server jar
SCRCPY_DEVICE_SERVER_PATH = "/data/local/tmp/scrcpy-server.jar"  # Device path

# Battle view: pinch-zoom when a battle starts, then pan to survey the base.
#   "in"  -> fingers spread apart (zoom in)
#   "out" -> fingers close together (zoom out)
#   ""    -> disabled
BATTLE_ZOOM = "out"
ZOOM_START_DIST = 267  # Initial distance between fingers (px)
ZOOM_END_DIST = 213  # Final distance between fingers (px)
ZOOM_STEPS = 25  # Number of move frames

# Pan swipes after zooming: (x1, y1, x2, y2, steps, dt). Swipe left, then back.
BATTLE_PAN_SWIPE_1 = (167, 200, 400, 200, 15, 0.01)  # Swipe left to right
BATTLE_PAN_SWIPE_2 = (200, 167, 200, 400, 15, 0.01)  # Swipe top to bottom
BATTLE_PAN_SWIPE_3 = (200, 133, 200, 433, 15, 0.01)  # Swipe top to bottom (more)
