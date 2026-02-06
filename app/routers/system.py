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
import socket

# Try importing GPUtil
try:
    import GPUtil
except ImportError:
    GPUtil = None

router = APIRouter(
    tags=["system"],
    dependencies=[Depends(get_api_key)]
)

@router.get("/info")
async def get_system_info():
    """
    Get aggregated system information including Docker stats, Git version, and System resources.
    """
    try:
        # 1. Docker Stats
        docker_stats = {}
        try:
            client = get_docker_client()
            try:
                containers = client.containers.list(all=True)
                images = client.images.list()
                
                total_containers = len(containers)
                running_containers = sum(1 for c in containers if c.status == 'running')
                stopped_containers = total_containers - running_containers
                image_count = len(images)
                
                docker_stats = {
                    "containers": {
                        "total": total_containers,
                        "running": running_containers,
                        "stopped": stopped_containers
                    },
                    "images": image_count
                }
            finally:
                client.close()
        except Exception as e:
            docker_stats = {"error": str(e)}

        # 2. Git Version (Reuse existing logic by calling the function directly)
        # Note: Since get_git_version is an async endpoint function, we can await it.
        # However, it might return HTTPException which we should catch if we want partial results.
        git_info = {}
        try:
            git_info = await get_git_version()
        except HTTPException as e:
            git_info = {"error": e.detail}
        except Exception as e:
            git_info = {"error": str(e)}

        # 3. System Usage (Reuse existing logic)
        usage_info = {}
        try:
            usage_info = await get_system_usage()
        except HTTPException as e:
            usage_info = {"error": e.detail}
        except Exception as e:
            usage_info = {"error": str(e)}

        return {
            "docker": docker_stats,
            "git": git_info,
            "system": usage_info
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving system info: {str(e)}")

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

def _get_host_used_ports():
    used_ports = set()
    
    # Method 0: Check Docker mapped ports (Most reliable for containerized environment)
    try:
        client = get_docker_client()
        containers = client.containers.list(all=True)
        for c in containers:
            # ports format: {'80/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8000'}], ...}
            ports = c.attrs.get('NetworkSettings', {}).get('Ports', {})
            if ports:
                for container_port, host_bindings in ports.items():
                    if host_bindings:
                        for binding in host_bindings:
                            host_port = binding.get('HostPort')
                            if host_port:
                                try:
                                    used_ports.add(int(host_port))
                                except ValueError:
                                    pass
        client.close()
    except Exception:
        pass

    host_fs = os.getenv("HOST_FILESYSTEM_ROOT", "/")
    proc_net = os.path.join(host_fs, "proc/net")
    
    # Method 1: Try reading /proc/net (Linux with host mount)
    if os.path.exists(os.path.join(proc_net, "tcp")):
        files = [
            ("tcp", True),
            ("tcp6", True),
            ("udp", False),
            ("udp6", False)
        ]
        
        for fname, is_tcp in files:
            path = os.path.join(proc_net, fname)
            if not os.path.exists(path):
                continue
            
            try:
                with open(path, "r") as f:
                    lines = f.readlines()[1:] # Skip header
                    for line in lines:
                        parts = line.split()
                        if len(parts) < 4: continue
                        
                        local_addr = parts[1]
                        status = parts[3]
                        
                        if ":" in local_addr:
                            _, port_hex = local_addr.split(":")
                            try:
                                port = int(port_hex, 16)
                                if is_tcp:
                                    if status == "0A": # LISTEN
                                        used_ports.add(port)
                                else:
                                    used_ports.add(port) # UDP
                            except ValueError:
                                pass
            except Exception:
                pass
    
    # Method 2: Fallback to psutil (Windows or Linux without host mount)
    # Even with Method 1, psutil might catch some local processes if running outside container
    # or in host networking mode
    try:
        conns = psutil.net_connections(kind='inet')
        for c in conns:
            # TCP LISTEN or UDP (any)
            if c.status == 'LISTEN' or c.type == socket.SOCK_DGRAM:
                if c.laddr:
                    used_ports.add(c.laddr.port)
    except Exception:
        pass
            
    return used_ports

@router.get("/ports/available")
async def get_available_ports():
    """
    Get a list of available port ranges on the host.
    """
    try:
        used_ports = await asyncio.get_event_loop().run_in_executor(None, _get_host_used_ports)
        
        # Calculate available ranges
        sorted_used = sorted(list(used_ports))
        ranges = []
        start = 1
        
        for port in sorted_used:
            if port > start:
                ranges.append(f"{start}-{port-1}")
            start = port + 1
            
        if start <= 65535:
            ranges.append(f"{start}-65535")
            
        return {
            "total_available": 65535 - len(used_ports),
            "ranges": ranges
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving available ports: {str(e)}")

