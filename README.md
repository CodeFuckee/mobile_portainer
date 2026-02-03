# Mobile Portainer API

[English](README.md) | [中文](README_zh.md)

A lightweight Docker management API service built with [FastAPI](https://fastapi.tiangolo.com/). It is designed to provide a simple interface for mobile applications to manage Docker containers, images, networks, and volumes. It also includes a simple Web Admin UI for managing API keys and cluster nodes.

## ✨ Features

- **Docker Management**:
  - **Containers**: List, inspect details, view logs, resource stats, start, stop, restart, kill, remove, **browse files**.
  - **Images**: List, pull new images, remove, inspect details.
  - **Networks**: List, inspect details, create, remove.
  - **Volumes**: List, inspect details, create, remove, **browse files**.
  - **System**: Get Docker system info, version, real-time events stream.
- **Security**:
  - Core API endpoints are protected by `X-API-Key`.
  - Web Admin UI is protected by Basic Auth.
- **Web Admin UI**:
  - Intuitive interface to manage API Access Keys.
  - Manage Cluster Nodes information.
- **Auto Update**:
  - Built-in Git auto-update service that can be configured to periodically check the remote repository and update/restart automatically.
- **System Monitoring**:
  - Supports mounting the host root directory for monitoring host resource usage.

## 🛠️ Tech Stack

- **Language**: Python 3.9+
- **Web Framework**: FastAPI
- **Database**: SQLite (managed via SQLAlchemy ORM)
- **Docker Interaction**: Docker SDK for Python
- **Deployment**: Docker / Docker Compose

## 🚀 Quick Start

### 1. Prerequisites

Ensure your server has the following installed:
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

### 2. Install & Run

#### Option A: Build from Source (Docker Compose)

Start the service directly using Docker Compose:

```bash
# Build and start in detached mode
docker-compose up -d --build
```

#### Option B: Run from Docker Hub

You can also run the pre-built image directly:

**Docker CLI:**

```bash
docker run -d \
  --name mobile-portainer \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v mobile_portainer_data:/app/data \
  -v /:/hostfs:ro \
  -e ADMIN_USER=admin \
  -e ADMIN_PASSWORD=password \
  --restart unless-stopped \
  codefuckee/mobile_portainer:latest
```

**Docker Compose:**

```yaml
version: '3.8'
services:
  api:
    image: codefuckee/mobile_portainer:latest
    ports:
      - "8000:8000"
    environment:
      - ADMIN_USER=admin
      - ADMIN_PASSWORD=password
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./data:/app/data
      - /:/hostfs:ro
    restart: unless-stopped
```

### 3. Access the Service

Once started, you can access the following:

- **Web Admin UI**: [http://localhost:8000](http://localhost:8000)
  - Default Username: `admin`
  - Default Password: `password`
  - *Please change the default password in `docker-compose.yml` for production environments!*
- **API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Documentation (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## ⚙️ Environment Variables

You can configure the service by modifying the `environment` section in `docker-compose.yml`:

| Variable Name | Default Value | Description |
| :--- | :--- | :--- |
| `ADMIN_USER` | `admin` | Username for Web Admin UI |
| `ADMIN_PASSWORD` | `...` | Password for Web Admin UI |
| `IGNORED_EVENTS` | `exec_create,exec_start,exec_die` | Event types to ignore in Docker event stream |
| `GIT_AUTO_UPDATE` | `true` | Enable/Disable Git auto-update feature |
| `GIT_REPO_URL` | `...` | Git repository URL for auto-update |
| `GIT_BRANCH` | `main` | Git branch to track |
| `GIT_CHECK_INTERVAL` | `60` | Auto-update check interval (in seconds) |
| `GIT_USER` | `...` | Git username (if required) |
| `GIT_PASSWORD` | `...` | Git password (if required) |
| `HOST_FILESYSTEM_ROOT` | `/hostfs` | Mount path of host root directory inside container |

## 📂 Project Structure

```text
.
├── app/
│   ├── core/           # Core config, security, utils
│   ├── db/             # Database models and connection
│   ├── routers/        # API routers (Containers, Images, WebUI, etc.)
│   ├── services/       # Background services (Docker Event Listener, Git Updater)
├── data/               # Data persistence directory (SQLite database)
├── docker-compose.yml  # Docker Compose orchestration file
├── Dockerfile          # Docker image build file
├── main.py             # FastAPI application entry point
└── requirements.txt    # Python dependencies
```

## 📝 API Usage Example

All protected API endpoints require the `X-API-Key` header.

**Get Container List:**

```http
GET /containers/json HTTP/1.1
Host: localhost:8000
X-API-Key: <Your-API-Key-From-Web-UI>
```

You can generate and manage these API Keys after logging into the Web Admin UI (`/`).
