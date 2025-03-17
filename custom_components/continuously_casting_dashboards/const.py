"""Constants for the Continuously Casting Dashboards integration."""

DOMAIN = "continuously_casting_dashboards"
CONF_SWITCH_ENTITY = "switch_entity"
PLATFORMS = []

# Default configuration values
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_CAST_DELAY = 0
DEFAULT_START_TIME = "00:00"
DEFAULT_END_TIME = "23:59"
DEFAULT_VOLUME = 5
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_DELAY = 10
DEFAULT_VERIFICATION_WAIT_TIME = 15

# File paths
CONFIG_DIR = "/config/continuously_casting_dashboards"
STATUS_FILE = f"{CONFIG_DIR}/status.json"
HEALTH_STATS_FILE = f"{CONFIG_DIR}/health_stats.json"

# Device status types
STATUS_CONNECTED = "connected"
STATUS_DISCONNECTED = "disconnected"
STATUS_MEDIA_PLAYING = "media_playing"
STATUS_OTHER_CONTENT = "other_content"
STATUS_UNKNOWN = "unknown"
STATUS_STOPPED = "stopped"

# Health stats event types
EVENT_CONNECTION_ATTEMPT = "connection_attempt"
EVENT_CONNECTION_SUCCESS = "connection_success"
EVENT_DISCONNECTED = "disconnected"
EVENT_RECONNECT_ATTEMPT = "reconnect_attempt"
EVENT_RECONNECT_SUCCESS = "reconnect_success"
EVENT_RECONNECT_FAILED = "reconnect_failed"
