# =============================================================================
# CONFIGURATION
# =============================================================================

# Screenshot filename (used for all template matching)
SCREENSHOT_NAME = "screen.png"

# Log file for session tracking
LOG_FILE = "bot_session_log.txt"

# Tap jitter: each tap lands randomly within ± this many pixels (0-5 px)
TAP_OFFSET_MAX = 5

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

# Max searches per attack: bot attacks a random base after 1..this many searches
MAX_BASE_SEARCHES = 3

# =============================================================================
# FLOW PACING (sleeps between bot actions)
# =============================================================================
# Wait for the unit-selection UI to appear after picking a troop/spell/hero
SELECTION_UI_DELAY = 0.3
# Pause after reaching the attack screen and after tapping Attack
POST_ATTACK_SLEEP = 2
# Pause after pinch-zooming at battle start
POST_ZOOM_SLEEP = 1.5
# Pause after tapping Return Home (wait for the battle-end dialog)
RETURN_HOME_TAP_SLEEP = 3
# Range of random pauses between "Next" base searches
SEARCH_NEXT_SLEEP_RANGE = (4.5, 5.0)

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

# Hero abilities to trigger after deployment (template folder-name partials)
HERO_ABILITIES = ["grand_warden"]

# =============================================================================
# DEPLOYMENT COORDINATES
# =============================================================================

TROOP_LOCATIONS = [
    (226, 614),
    (300, 568),
    (354, 530),
    (394, 516),
    (432, 470),
    (484, 430),
    (530, 396),
    (572, 364),
    (616, 332),
    (650, 304),
    (704, 262),
    (738, 242),
    (804, 200),
    (838, 162),
    (882, 134),
    (928, 104),
    (836, 158),
    (776, 200),
    (718, 246),
    (646, 296),
    (610, 332),
    (554, 380),
    (512, 406),
    (448, 454),
    (394, 496),
    (338, 532),
    (256, 602),
    (220, 624),
    (298, 560),
    (358, 516),
    (422, 486),
    (506, 430),
    (588, 360),
    (650, 302),
    (754, 260),
]

SPELL_LOCATIONS = [
    (588, 272),
    (494, 395),
    (583, 205),
    (636, 395),
    (632, 500),
]

HERO_LOCATIONS = [
    (149, 320),
    (194, 379),
    (214, 261),
    (157, 325),
    (214, 261),
    (646, 296),
    (610, 332),
    (554, 380),
    (512, 406),
    (448, 454),
    (394, 496),
]

# =============================================================================
# SCRCPY CONTROL
# =============================================================================
# Control backend used by the bot:
#   "scrcpy" -> scrcpy control protocol + live video-stream screenshots
#               (see SCRCPY_BOT_REFERENCE.md). Recommended.
#   "adb"    -> fall back to ADB `input` / `screencap` commands.
CONTROL_MODE = "scrcpy"

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
ZOOM_START_DIST = 400  # Initial distance between fingers (px)
ZOOM_END_DIST = 320  # Final distance between fingers (px)
ZOOM_STEPS = 25  # Number of move frames

# Pan swipes after zooming: (x1, y1, x2, y2, steps, dt). Swipe left, then back.
BATTLE_PAN_SWIPE_1 = (250, 300, 600, 300, 15, 0.01)  # Swipe left to right
BATTLE_PAN_SWIPE_2 = (300, 250, 300, 600, 15, 0.01)  # Swipe top to bottom
BATTLE_PAN_SWIPE_3 = (300, 200, 300, 650, 15, 0.01)  # Swipe top to bottom (more)
