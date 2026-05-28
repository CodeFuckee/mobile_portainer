from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import threading
from app.db.database import engine, Base
from app.services.docker_monitor import docker_event_listener

# Import Routers
from app.routers import (
    containers,
    images,
    networks,
    volumes,
    system,
    admin,
    websockets,
    # web_ui,  # 前端已迁移至独立 Flutter Web 服务
    stacks,
    docker_proxy,
)
from app.core.config import DOCKER_ENGINE_API_ENABLED

# Initialize Database
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Mobile Portainer API",
    description="A simple API to manage Docker containers, stacks, and view logs.",
    version="1.0.0",
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers first (takes priority)
app.include_router(containers.router)
app.include_router(images.router)
app.include_router(networks.router)
app.include_router(volumes.router)
app.include_router(stacks.router)
app.include_router(system.router)
app.include_router(admin.router)
app.include_router(websockets.router)

# Docker Engine API 代理（在 API 路由之后、Web UI 之前）
if DOCKER_ENGINE_API_ENABLED:
    app.include_router(docker_proxy.router)

# Web UI 前端已迁移至独立 Flutter Web 服务（nginx 容器）
# app.include_router(web_ui.router)


@app.on_event("startup")
async def startup_event():
    # Start Docker Event Listener
    loop = asyncio.get_event_loop()
    threading.Thread(target=docker_event_listener, args=(loop,), daemon=True).start()


@app.on_event("shutdown")
async def shutdown_event():
    from app.core.docker_socket import close_docker_http_client

    await close_docker_http_client()
