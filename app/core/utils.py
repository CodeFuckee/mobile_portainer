import docker
from fastapi import HTTPException
import socket
from typing import Dict, Any


def get_docker_client():
    try:
        return docker.from_env()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to connect to Docker daemon: {str(e)}"
        )


def get_self_container(client):
    """
    Get the container object for the current running process.
    Returns None if not found or not running in a container.
    """
    self_id = get_current_container_id()
    if not self_id:
        return None

    try:
        return client.containers.get(self_id)
    except docker.errors.NotFound:
        # Try finding by prefix if self_id is short ID
        if len(self_id) < 64:
            # List all and check prefix
            containers = client.containers.list(all=True)
            for c in containers:
                if c.id.startswith(self_id):
                    return c
    except Exception:
        pass

    return None


def get_current_container_id():
    """
    Try to resolve the current container's ID.
    Returns hostname (usually short ID) or full ID from cgroup.
    """
    try:
        # Try to read cgroup to find full container ID
        with open("/proc/self/cgroup", "r") as f:
            for line in f:
                if "docker" in line:
                    path = line.split(":")[-1].strip()
                    container_id = path.split("/")[-1]
                    if container_id:
                        return container_id
    except Exception:
        pass
    # Fallback to hostname
    return socket.gethostname()


def process_container_summary(container, self_id: str = None) -> Dict[str, Any]:
    # Stack
    labels = container.labels or {}
    stack = labels.get("com.docker.compose.project", "")

    # Image
    image = container.attrs.get("Image", "")
    if image.startswith("sha256:"):
        try:
            if container.image and container.image.tags:
                image = container.image.tags[0]
        except Exception:
            pass

    # Ports
    ports_str_list = []
    ports_list = []
    raw_ports = container.attrs.get("Ports", [])
    for p in raw_ports:
        if "PublicPort" in p:
            ports_str_list.append(f"{p['PublicPort']}->{p['PrivatePort']}/{p['Type']}")
        ports_list.append(
            {
                "public_port": p.get("PublicPort"),
                "private_port": p.get("PrivatePort"),
                "type": p.get("Type"),
            }
        )
    ports = ", ".join(ports_str_list)

    is_self = False
    if self_id:
        # Check against full ID or short ID
        if container.id == self_id:
            is_self = True
        elif container.id.startswith(self_id):  # self_id is short
            is_self = True
        elif self_id.startswith(
            container.id
        ):  # self_id is somehow longer (unlikely if container.id is full)
            is_self = True

    return {
        "id": container.id,
        "name": container.name,
        "status": str(container.status).lower(),
        "stack": stack,
        "image": image,
        "ports": ports,
        "ports_list": ports_list,
        "is_self": is_self,
    }
