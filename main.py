from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import threading
from app.db.database import engine, Base
from app.services.docker_monitor import docker_event_listener
from app.services.git_updater import git_auto_updater

# Import Routers
from app.routers import containers, images, networks, volumes, system, admin, websockets, web_ui, stacks

# Initialize Database
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Mobile Portainer API",
    description="A simple API to manage Docker containers, stacks, and view logs.",
    version="1.0.0"
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(web_ui.router) # Root router first
app.include_router(containers.router)
app.include_router(images.router)
app.include_router(networks.router)
app.include_router(volumes.router)
app.include_router(stacks.router)
app.include_router(system.router)
app.include_router(admin.router)
app.include_router(websockets.router)

@app.on_event("startup")
async def startup_event():
    # Start Docker Event Listener
    loop = asyncio.get_event_loop()
    threading.Thread(target=docker_event_listener, args=(loop,), daemon=True).start()
    
    # Start Git Auto Updater
    threading.Thread(target=git_auto_updater, daemon=True).start()
