import os


# --- Security & Config ---
API_KEY_NAME = "X-API-Key"
ADMIN_USER_HEADER = "X-Admin-User"
ADMIN_PASS_HEADER = "X-Admin-Pass"
ADMIN_USER = os.getenv("ADMIN_USER", "admin")  # Username to access Web UI
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password")  # Password to access Web UI
IGNORED_EVENTS = set(
    os.getenv("IGNORED_EVENTS", "exec_create,exec_start,exec_die").split(",")
)

# --- System Monitoring ---
HOST_FILESYSTEM_ROOT = os.getenv("HOST_FILESYSTEM_ROOT", "/hostfs")

# --- Docker Engine API 代理 ---
DOCKER_SOCKET_PATH = os.getenv("DOCKER_SOCKET_PATH", "/var/run/docker.sock")
DOCKER_ENGINE_API_ENABLED = (
    os.getenv("DOCKER_ENGINE_API_ENABLED", "true").lower() == "true"
)
