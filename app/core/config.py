import os


# --- Security & Config ---
API_KEY_NAME = "X-API-Key"
ADMIN_USER = os.getenv("ADMIN_USER", "admin")  # Username to access Web UI
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password")  # Password to access Web UI
IGNORED_EVENTS = set(
    os.getenv("IGNORED_EVENTS", "exec_create,exec_start,exec_die").split(",")
)

# --- System Monitoring ---
HOST_FILESYSTEM_ROOT = os.getenv("HOST_FILESYSTEM_ROOT", "/hostfs")
