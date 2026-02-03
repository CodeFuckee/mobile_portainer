from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
import os
import git
import docker
from datetime import datetime
from app.core.security import get_api_key
from app.core.utils import get_docker_client, get_current_container_id
import psutil
import asyncio

# Try importing GPUtil
try:
    import GPUtil
except ImportError:
    GPUtil = None

router = APIRouter(
    tags=["system"],
    dependencies=[Depends(get_api_key)]
)

@router.get("/self", response_model=Dict[str, Any])
async def get_self_container_info():
    """
    Get information about the container running this API server.
    """
    client = get_docker_client()
    try:
        self_id = get_current_container_id()
        if not self_id:
            raise HTTPException(status_code=404, detail="Could not determine self container ID")

        try:
            container = client.containers.get(self_id)
            return container.attrs
        except docker.errors.NotFound:
            # Try finding by prefix if self_id is short ID
            if len(self_id) < 64:
                 # List all and check prefix
                 containers = client.containers.list(all=True)
                 for c in containers:
                     if c.id.startswith(self_id):
                         return c.attrs
            
            raise HTTPException(status_code=404, detail=f"Self container not found (ID: {self_id})")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving self container info: {str(e)}")
    finally:
        client.close()

@router.get("/stacks", response_model=List[str])
async def list_stacks():
    """
    Get a list of all Docker Stacks (Compose projects).
    """
    client = get_docker_client()
    try:
        containers = client.containers.list(all=True)
        stacks = set()
        for container in containers:
            labels = container.labels or {}
            stack_name = labels.get("com.docker.compose.project")
            if stack_name:
                stacks.add(stack_name)
        return sorted(list(stacks))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving stacks: {str(e)}")
    finally:
        client.close()

@router.get("/git/version")
async def get_git_version():
    """
    Get the current git version (commit hash, branch, message).
    """
    repo_dir = os.getcwd()
    try:
        repo = git.Repo(repo_dir, search_parent_directories=True)
        
        try:
            head_commit = repo.head.commit
        except (ValueError, Exception):
             return {
                "branch": "unknown",
                "commit_hash": "unknown",
                "short_hash": "unknown",
                "commit_message": "No commits or invalid repo",
                "author": "unknown",
                "date": datetime.now().isoformat()
            }

        branch_name = "detached"
        try:
            branch_name = repo.active_branch.name
        except (TypeError, ValueError, Exception):
            # Handle detached HEAD or missing refs (like 'master' not found)
            try:
                # Try to get symbolic reference name if available
                if not repo.head.is_detached:
                    branch_name = repo.head.ref.name
            except:
                pass

        return {
            "branch": branch_name,
            "commit_hash": head_commit.hexsha,
            "short_hash": head_commit.hexsha[:7],
            "commit_message": head_commit.message.strip(),
            "author": head_commit.author.name,
            "date": datetime.fromtimestamp(head_commit.committed_date).isoformat()
        }
    except git.exc.InvalidGitRepositoryError:
         raise HTTPException(status_code=404, detail="Not a git repository")
    except Exception as e:
         # Log the error but return a graceful response instead of 500 if possible, 
         # or just raise 500 if it's a critical failure.
         # Given the user's issue, catching the specific error inside is better.
         raise HTTPException(status_code=500, detail=f"Error retrieving git info: {str(e)}")

@router.get("/usage")
async def get_system_usage():
    """
    Get system usage statistics (CPU, Memory, Disk, GPU).
    """
    try:
        # CPU - Run in executor to avoid blocking main loop (interval=1 blocks for 1 sec)
        loop = asyncio.get_event_loop()
        cpu_percent = await loop.run_in_executor(None, psutil.cpu_percent, 1)
        cpu_count = psutil.cpu_count()
        
        # Memory
        mem = psutil.virtual_memory()
        memory = {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent
        }
        
        # Disk
        disks = []
        host_fs = os.getenv("HOST_FILESYSTEM_ROOT", "/")
        
        try:
            # If HOST_FILESYSTEM_ROOT is set and not '/', prioritize it
            if host_fs != "/" and os.path.exists(host_fs):
                 usage = psutil.disk_usage(host_fs)
                 disks.append({
                    "device": "host_root",
                    "mountpoint": host_fs,
                    "fstype": "unknown", # Hard to determine from inside without mount inspection
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent
                })
            else:
                # Fallback to standard partition discovery
                for partition in psutil.disk_partitions():
                    try:
                        # Filter out snap and loops to reduce noise, unless you really want them
                        if "loop" in partition.device or "snap" in partition.mountpoint:
                            continue
                            
                        usage = psutil.disk_usage(partition.mountpoint)
                        disks.append({
                            "device": partition.device,
                            "mountpoint": partition.mountpoint,
                            "fstype": partition.fstype,
                            "total": usage.total,
                            "used": usage.used,
                            "free": usage.free,
                            "percent": usage.percent
                        })
                    except (PermissionError, OSError):
                        continue
        except Exception as e:
            pass # Keep going if disk info fails
                
        # GPU
        gpus = []
        if GPUtil:
            try:
                # GPUtil.getGPUs() might fail if no NVIDIA driver or no GPUs
                gpu_list = await loop.run_in_executor(None, GPUtil.getGPUs)
                for gpu in gpu_list:
                    gpus.append({
                        "id": gpu.id,
                        "name": gpu.name,
                        "load": gpu.load * 100, # Convert to percent
                        "memory_total": gpu.memoryTotal,
                        "memory_used": gpu.memoryUsed,
                        "memory_free": gpu.memoryFree,
                        "temperature": gpu.temperature
                    })
            except Exception:
                pass # Gracefully handle GPU errors (no driver, etc)
        
        return {
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count
            },
            "memory": memory,
            "disk": disks,
            "gpu": gpus
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving system usage: {str(e)}")
