import os

# --- Security & Config ---
API_KEY_NAME = "X-API-Key"
ADMIN_USER = os.getenv("ADMIN_USER", "admin") # Username to access Web UI
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password") # Password to access Web UI
IGNORED_EVENTS = set(os.getenv("IGNORED_EVENTS", "exec_create,exec_start,exec_die").split(","))

# --- Git Auto Update Config ---
GIT_AUTO_UPDATE = os.getenv("GIT_AUTO_UPDATE", "false").lower() == "true"
GIT_REPO_URL = os.getenv("GIT_REPO_URL", "")
GIT_BRANCH = os.getenv("GIT_BRANCH", "main")
GIT_CHECK_INTERVAL = int(os.getenv("GIT_CHECK_INTERVAL", "60"))
GIT_USER = os.getenv("GIT_USER", "")
GIT_PASSWORD = os.getenv("GIT_PASSWORD", "")
GIT_SSL_NO_VERIFY = os.getenv("GIT_SSL_NO_VERIFY", "false").lower() == "true"

# --- System Monitoring ---
HOST_FILESYSTEM_ROOT = os.getenv("HOST_FILESYSTEM_ROOT", "/hostfs")
