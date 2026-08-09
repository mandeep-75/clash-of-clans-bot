# =============================================================================
# FLOW CONFIGURATION - Control which tasks run
# =============================================================================
# Set to True/False to enable/disable each task
# The bot will run tasks in the order defined here
FLOW_CONFIG = {
    "collect_gold": True,
    "collect_elixir": True,
    "collect_dark_elixir": True,
    "find_match": True,
    "search_for_base": True,
    "deploy_troops": True,
    "deploy_heroes": True,
    "deploy_spells": True,
    "trigger_abilities": True,
    "return_home": True,
}

# =============================================================================
# CONFIGURATION
# =============================================================================

# Discord Webhook URL for notifications (leave empty to disable)
DISCORD_WEBHOOK_URL = ""

# Screenshot filename (used for all template matching)
SCREENSHOT_NAME = "screen.png"

# Log file for session tracking
LOG_FILE = "bot_session_log.txt"

# Random offset ranges to make clicks appear more human-like
# Higher values = more variation in tap position
RANDOM_OFFSET = 3  # For troop deployments
RANDOM_OFFSET_HEROES = 3  # For hero deployments
RANDOM_OFFSET_SPELLS = 25  # For spell deployments (larger area)

# Resource thresholds for base selection
# Bot will attack bases that meet ALL of these minimums:
GOLD_THRESHOLD = 500_000  # Minimum gold required
ELIXIR_THRESHOLD = 500_000  # Minimum elixir required
DARK_ELIXIR_THRESHOLD = 0  # Minimum dark elixir required
MAX_TROPHIES_ATTACK_THRESHOLD = 30  # Reserved for future trophy-based filtering

# =============================================================================
# TIMEOUTS (in seconds)
# =============================================================================
BASE_SEARCH_TIMEOUT = 120  # Maximum time to spend searching for a suitable base
RETURN_HOME_TIMEOUT = 210  # Maximum time to wait for return home button after battle

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
# UI TEMPLATE FOLDERS
# =============================================================================
# Path to builder menu button template (for future use)
BUILD_MENU_BUTTON_FOLDER = "templates/builder_menu_button"

# =============================================================================
# DEPLOYMENT COORDINATES
# =============================================================================
# Number of troops to deploy per attack (should match your army camp capacity)
TROOP_COUNT = 28

TROOP_LOCATIONS = [
    (173, 380),
    (198, 395),
    (220, 413),
    (252, 438),
    (293, 464),
    (321, 479),
    (178, 288),
    (203, 271),
    (227, 258),
    (256, 230),
    (295, 202),
    (318, 188),
    (357, 166),
    (383, 144),
    (406, 120),
    (321, 479),
    (178, 288),
    (203, 271),
    (227, 258),
    (256, 230),
    (295, 202),
    (318, 188),
    (357, 166),
    (383, 144),
    (406, 120),
    (227, 258),
    (256, 230),
    (293, 464),
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

# Battle zoom: pinch-zoom when a battle starts.
#   "in"  -> fingers spread apart (zoom in)
#   "out" -> fingers close together (zoom out)
#   ""    -> disabled
BATTLE_ZOOM = "in"
ZOOM_START_DIST = 60  # Initial distance between fingers (px)
ZOOM_END_DIST = 320  # Final distance between fingers (px)
ZOOM_STEPS = 25  # Number of move frames
