"""Constants for the Continuously Casting Dashboards integration."""

DOMAIN = "continuously_casting_dashboards"
CONF_SWITCH_ENTITY = "switch_entity_id"
CONF_SWITCH_ENTITY_STATE = "switch_entity_state"
PLATFORMS = ["sensor"]  # Add sensor platform here!

# Default configuration values
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_CAST_DELAY = 60
DEFAULT_START_TIME = "07:00"
DEFAULT_END_TIME = "01:00"
DEFAULT_VOLUME = 5
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_DELAY = 5
DEFAULT_VERIFICATION_WAIT_TIME = 15
DEFAULT_CASTING_TIMEOUT = 60

# Subprocess timeout constants (seconds)
TIMEOUT_STATUS_CHECK = 15.0       # catt status / catt scan command timeout
TIMEOUT_PROCESS_TERMINATE = 5.0   # Grace period after terminate() before kill()
TIMEOUT_PROCESS_KILL = 2.0        # Grace period after kill()
TIMEOUT_VOLUME_COMMAND = 10.0     # catt volume command timeout
TIMEOUT_SPEAKER_GROUP = 15.0      # Speaker group status check timeout
TIMEOUT_SCAN = 15.0               # catt scan timeout
TIMEOUT_SCAN_TERMINATE = 2.0      # Grace period after scan terminate()
DEFAULT_LOGGING_LEVEL = "warning"
DEFAULT_ENABLE_NOTIFICATIONS = True

# Logging levels
LOGGING_LEVELS = ["debug", "info", "warning", "error", "critical"]

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
STATUS_SPEAKER_GROUP_ACTIVE = "speaker_group_active"
STATUS_CASTING_IN_PROGRESS = "casting_in_progress"
STATUS_ASSISTANT_ACTIVE = "assistant_active"

# Health stats event types
EVENT_CONNECTION_ATTEMPT = "connection_attempt"
EVENT_CONNECTION_SUCCESS = "connection_success"
EVENT_DISCONNECTED = "disconnected"
EVENT_RECONNECT_ATTEMPT = "reconnect_attempt"
EVENT_RECONNECT_SUCCESS = "reconnect_success"
EVENT_RECONNECT_FAILED = "reconnect_failed"

# Configuration keys
CONF_LOGGING_LEVEL = "logging_level"
CONF_CAST_DELAY = "cast_delay"
CONF_START_TIME = "start_time"
CONF_END_TIME = "end_time"
CONF_SWITCH_ENTITY_ID = "switch_entity_id"
CONF_SWITCH_ENTITY_STATE = "switch_entity_state"
CONF_DASHBOARD_URL = "dashboard_url"
CONF_VOLUME = "volume"
CONF_SPEAKER_GROUPS = "speaker_groups"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_IP = "device_ip"
CONF_DEVICE_ALIAS = "device_alias"

# Translation strings
ERR_DEVICE_ALREADY_EXISTS = "device_already_exists"
