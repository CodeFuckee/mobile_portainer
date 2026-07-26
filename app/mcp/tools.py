"""
MCP 工具定义。

通过 register_all_tools(server) 将 24 个 Docker 管理工具注册到 MCP Server。
工具分为 5 组：容器(11)、镜像(4)、网络(2)、卷(3)、系统(4)。
"""

import os
from datetime import datetime

import docker
import git
import psutil
from mcp.server.fastmcp import FastMCP

from app.core.utils import (
    get_current_container_id,
    parse_docker_run_command,
    process_container_summary,
)

from .helpers import get_docker_client_safe, get_db_session

try:
    import GPUtil
except ImportError:
    GPUtil = None


def register_all_tools(server: FastMCP) -> None:
    """向 MCP Server 注册所有 Docker 管理工具。"""

    # ==================== 容器工具 ====================

    @server.tool(description="列出所有 Docker 容器。可选择返回摘要信息或完整属性。")
    def list_containers(summary: bool = False, all: bool = True) -> list[dict]:
        client = get_docker_client_safe()
        try:
            containers = client.containers.list(all=all)
            if summary:
                self_id = get_current_container_id()
                return [process_container_summary(c, self_id) for c in containers]
            return [
                {
                    "id": c.id,
                    "short_id": c.short_id,
                    "name": c.name,
                    "status": str(c.status).lower(),
                    "image": str(c.image),
                    "attrs": c.attrs,
                }
                for c in containers
            ]
        finally:
            client.close()

    @server.tool(description="通过 ID 或名称获取指定容器的详细信息。")
    def get_container(container_id: str) -> dict:
        client = get_docker_client_safe()
        try:
            return client.containers.get(container_id).attrs
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到容器：{container_id}")
        finally:
            client.close()

    @server.tool(description="获取指定容器的日志。")
    def get_container_logs(
        container_id: str, tail: int = 2000, timestamps: bool = True
    ) -> dict:
        client = get_docker_client_safe()
        try:
            container = client.containers.get(container_id)
            logs = container.logs(tail=tail, timestamps=timestamps).decode(
                "utf-8", errors="replace"
            )
            return {"logs": logs}
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到容器：{container_id}")
        finally:
            client.close()

    @server.tool(description="启动一个已停止的容器。")
    def start_container(container_id: str) -> dict:
        client = get_docker_client_safe()
        try:
            container = client.containers.get(container_id)
            container.start()
            return {
                "status": "success",
                "message": f"容器 {container.name} 已启动",
            }
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到容器：{container_id}")
        finally:
            client.close()

    @server.tool(description="正常停止一个正在运行的容器。")
    def stop_container(container_id: str) -> dict:
        client = get_docker_client_safe()
        try:
            container = client.containers.get(container_id)
            container.stop()
            return {
                "status": "success",
                "message": f"容器 {container.name} 已停止",
            }
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到容器：{container_id}")
        finally:
            client.close()

    @server.tool(description="重启一个容器。")
    def restart_container(container_id: str) -> dict:
        client = get_docker_client_safe()
        try:
            container = client.containers.get(container_id)
            container.restart()
            return {
                "status": "success",
                "message": f"容器 {container.name} 已重启",
            }
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到容器：{container_id}")
        finally:
            client.close()

    @server.tool(description="强制终止（kill）一个容器。")
    def kill_container(container_id: str) -> dict:
        client = get_docker_client_safe()
        try:
            container = client.containers.get(container_id)
            container.kill()
            return {
                "status": "success",
                "message": f"容器 {container.name} 已终止",
            }
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到容器：{container_id}")
        finally:
            client.close()

    @server.tool(description="暂停容器中的所有进程。")
    def pause_container(container_id: str) -> dict:
        client = get_docker_client_safe()
        try:
            container = client.containers.get(container_id)
            container.pause()
            return {
                "status": "success",
                "message": f"容器 {container.name} 已暂停",
            }
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到容器：{container_id}")
        finally:
            client.close()

    @server.tool(description="恢复（取消暂停）一个容器。")
    def unpause_container(container_id: str) -> dict:
        client = get_docker_client_safe()
        try:
            container = client.containers.get(container_id)
            container.unpause()
            return {
                "status": "success",
                "message": f"容器 {container.name} 已恢复",
            }
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到容器：{container_id}")
        finally:
            client.close()

    @server.tool(description="删除一个容器。可选择强制删除和同时删除关联的卷。")
    def remove_container(
        container_id: str, force: bool = True, v: bool = False
    ) -> dict:
        client = get_docker_client_safe()
        try:
            container = client.containers.get(container_id)
            container.remove(force=force, v=v)
            return {
                "status": "success",
                "message": f"容器 {container_id} 已删除",
            }
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到容器：{container_id}")
        finally:
            client.close()

    @server.tool(
        description=(
            "使用 docker run 命令字符串运行一个新容器。"
            "例如: 'docker run -d -p 8080:80 --name my-nginx nginx'。"
            "注意：始终以分离模式运行，避免阻塞。"
        )
    )
    def run_container(command: str) -> dict:
        client = get_docker_client_safe()
        try:
            params = parse_docker_run_command(command)
            if not params.get("detach"):
                params["detach"] = True
            container = client.containers.run(**params)
            return {
                "status": "success",
                "id": container.id,
                "short_id": container.short_id,
                "name": container.name,
            }
        except ValueError as e:
            raise RuntimeError(f"无效命令：{e}")
        except docker.errors.ImageNotFound as e:
            raise RuntimeError(f"未找到镜像：{e}")
        except docker.errors.APIError as e:
            raise RuntimeError(f"Docker API 错误：{e}")
        finally:
            client.close()

    # ==================== 镜像工具 ====================

    @server.tool(description="列出所有 Docker 镜像，含使用状态。")
    def list_images() -> list[dict]:
        client = get_docker_client_safe()
        try:
            images = client.images.list()
            containers = client.containers.list(all=True)
            used_image_ids = {c.attrs["Image"] for c in containers}
            return [
                {
                    "id": img.id,
                    "tags": img.tags,
                    "created": img.attrs.get("Created"),
                    "size": img.attrs.get("Size"),
                    "labels": img.labels,
                    "short_id": img.short_id,
                    "in_use": img.id in used_image_ids,
                }
                for img in images
            ]
        finally:
            client.close()

    @server.tool(description="通过 ID 或名称（标签）获取指定镜像的详细信息。")
    def get_image(image_id: str) -> dict:
        client = get_docker_client_safe()
        try:
            image = client.images.get(image_id)
            containers = client.containers.list(all=True)
            used_image_ids = {c.attrs["Image"] for c in containers}
            data = dict(image.attrs or {})
            data["id"] = image.id
            data["short_id"] = image.short_id
            data["tags"] = image.tags
            data["in_use"] = image.id in used_image_ids
            return data
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到镜像：{image_id}")
        finally:
            client.close()

    @server.tool(description="从注册表拉取一个 Docker 镜像。")
    def pull_image(image: str, tag: str = "latest") -> dict:
        client = get_docker_client_safe()
        try:
            pulled = client.images.pull(image, tag=tag)
            return {
                "status": "success",
                "id": pulled.id,
                "tags": pulled.tags,
                "message": f"镜像 {image}:{tag} 已拉取",
            }
        except docker.errors.APIError as e:
            raise RuntimeError(f"Docker API 错误：{e}")
        finally:
            client.close()

    @server.tool(
        description=("删除一个 Docker 镜像。image_id 可以是短 ID、完整 ID 或名称。")
    )
    def remove_image(image_id: str, force: bool = False) -> dict:
        client = get_docker_client_safe()
        try:
            client.images.remove(image=image_id, force=force)
            return {
                "status": "success",
                "message": f"镜像 {image_id} 已删除",
            }
        except docker.errors.ImageNotFound:
            raise RuntimeError(f"未找到镜像：{image_id}")
        except docker.errors.APIError as e:
            raise RuntimeError(f"删除镜像失败：{e}")
        finally:
            client.close()

    # ==================== 网络工具 ====================

    @server.tool(description="列出所有 Docker 网络。")
    def list_networks() -> list[dict]:
        client = get_docker_client_safe()
        try:
            networks = client.networks.list()
            return [
                {
                    "id": net.id,
                    "name": net.name,
                    "driver": net.attrs.get("Driver"),
                    "scope": net.attrs.get("Scope"),
                    "ipam": net.attrs.get("IPAM"),
                    "containers": net.attrs.get("Containers"),
                    "short_id": net.short_id,
                    "created": net.attrs.get("Created"),
                }
                for net in networks
            ]
        finally:
            client.close()

    @server.tool(description="通过 ID 或名称获取指定网络的详细信息。")
    def get_network(network_id: str) -> dict:
        client = get_docker_client_safe()
        try:
            return client.networks.get(network_id).attrs
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到网络：{network_id}")
        finally:
            client.close()

    # ==================== 卷工具 ====================

    @server.tool(description="列出所有 Docker 卷，含使用状态。")
    def list_volumes() -> list[dict]:
        client = get_docker_client_safe()
        try:
            volumes = client.volumes.list()
            containers = client.containers.list(all=True)
            used_volume_names: set[str] = set()
            for c in containers:
                for m in c.attrs.get("Mounts", []):
                    if m.get("Type") == "volume":
                        name = m.get("Name")
                        if name:
                            used_volume_names.add(name)
            return [
                {
                    "id": vol.id,
                    "name": vol.name,
                    "driver": vol.attrs.get("Driver"),
                    "created": vol.attrs.get("CreatedAt"),
                    "mountpoint": vol.attrs.get("Mountpoint"),
                    "labels": vol.attrs.get("Labels"),
                    "in_use": vol.name in used_volume_names,
                }
                for vol in volumes
            ]
        finally:
            client.close()

    @server.tool(description="通过 ID 或名称获取指定卷的详细信息。")
    def get_volume(volume_id: str) -> dict:
        client = get_docker_client_safe()
        try:
            volume = client.volumes.get(volume_id)
            containers = client.containers.list(all=True)
            used_by: list[str] = []
            for c in containers:
                for m in c.attrs.get("Mounts", []):
                    if m.get("Type") == "volume" and m.get("Name") == volume.name:
                        used_by.append(c.name)
                        break
            data = dict(volume.attrs)
            data["in_use"] = len(used_by) > 0
            data["used_by_containers"] = used_by
            return data
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到卷：{volume_id}")
        finally:
            client.close()

    @server.tool(description="删除一个 Docker 卷。")
    def remove_volume(volume_id: str, force: bool = False) -> dict:
        client = get_docker_client_safe()
        try:
            volume = client.volumes.get(volume_id)
            volume.remove(force=force)
            return {
                "status": "success",
                "message": f"卷 {volume_id} 已删除",
            }
        except docker.errors.NotFound:
            raise RuntimeError(f"未找到卷：{volume_id}")
        except docker.errors.APIError as e:
            if "in use" in str(e).lower():
                raise RuntimeError(f"卷正在使用中：{e}")
            raise RuntimeError(f"Docker API 错误：{e}")
        finally:
            client.close()

    # ==================== 系统工具 ====================

    @server.tool(description="获取聚合系统信息，包括 Docker 统计、Git 版本和系统资源。")
    def get_system_info() -> dict:
        result: dict = {}

        # Docker 统计
        try:
            client = get_docker_client_safe()
            containers = client.containers.list(all=True)
            images = client.images.list()
            running = sum(1 for c in containers if c.status == "running")
            result["docker"] = {
                "containers": {
                    "total": len(containers),
                    "running": running,
                    "stopped": len(containers) - running,
                },
                "images": len(images),
            }
            client.close()
        except Exception as e:
            result["docker"] = {"error": str(e)}

        # Git 版本
        try:
            repo = git.Repo(os.getcwd(), search_parent_directories=False)
            head = repo.head.commit
            branch = "detached"
            if not repo.head.is_detached:
                branch = repo.active_branch.name
            result["git"] = {
                "branch": branch,
                "commit_hash": head.hexsha,
                "short_hash": head.hexsha[:7],
                "commit_message": head.message.strip(),
                "author": head.author.name,
                "date": datetime.fromtimestamp(head.committed_date).isoformat(),
            }
        except Exception:
            result["git"] = {"error": "无法获取 git 信息"}

        # 系统资源
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            result["system"] = {
                "cpu": {
                    "percent": cpu_percent,
                    "count": psutil.cpu_count(),
                },
                "memory": {
                    "total": mem.total,
                    "available": mem.available,
                    "used": mem.used,
                    "percent": mem.percent,
                },
            }
        except Exception as e:
            result["system"] = {"error": str(e)}

        return result

    @server.tool(description="获取系统资源使用情况（CPU、内存、磁盘、GPU）。")
    def get_system_usage() -> dict:
        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()

        # 磁盘
        disks: list[dict] = []
        host_fs = os.getenv("HOST_FILESYSTEM_ROOT", "/")
        try:
            if host_fs != "/" and os.path.exists(host_fs):
                usage = psutil.disk_usage(host_fs)
                disks.append(
                    {
                        "device": "host_root",
                        "mountpoint": host_fs,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    }
                )
            else:
                for partition in psutil.disk_partitions():
                    try:
                        if "loop" in partition.device or "snap" in partition.mountpoint:
                            continue
                        usage = psutil.disk_usage(partition.mountpoint)
                        disks.append(
                            {
                                "device": partition.device,
                                "mountpoint": partition.mountpoint,
                                "fstype": partition.fstype,
                                "total": usage.total,
                                "used": usage.used,
                                "free": usage.free,
                                "percent": usage.percent,
                            }
                        )
                    except (PermissionError, OSError):
                        continue
        except Exception:
            pass

        # GPU
        gpus: list[dict] = []
        if GPUtil:
            try:
                for gpu in GPUtil.getGPUs():
                    gpus.append(
                        {
                            "id": gpu.id,
                            "name": gpu.name,
                            "load": gpu.load * 100,
                            "memory_total": gpu.memoryTotal,
                            "memory_used": gpu.memoryUsed,
                            "memory_free": gpu.memoryFree,
                            "temperature": gpu.temperature,
                        }
                    )
            except Exception:
                pass

        return {
            "cpu": {"percent": cpu_percent, "count": psutil.cpu_count()},
            "memory": {
                "total": mem.total,
                "available": mem.available,
                "used": mem.used,
                "percent": mem.percent,
            },
            "disk": disks,
            "gpu": gpus,
        }

    @server.tool(description="列出所有 Docker Compose 项目（堆栈）及其容器数量。")
    def list_stacks() -> list[dict]:
        client = get_docker_client_safe()
        try:
            containers = client.containers.list(all=True)
            stacks: dict[str, int] = {}
            for c in containers:
                labels = c.labels or {}
                stack_name = labels.get("com.docker.compose.project")
                if stack_name:
                    stacks[stack_name] = stacks.get(stack_name, 0) + 1
            return [
                {"name": k, "container_count": v} for k, v in sorted(stacks.items())
            ]
        finally:
            client.close()

    @server.tool(description="获取属于指定堆栈的所有容器。")
    def get_stack_containers(stack_name: str) -> list[dict]:
        client = get_docker_client_safe()
        self_id = get_current_container_id()
        try:
            filters = {"label": f"com.docker.compose.project={stack_name}"}
            containers = client.containers.list(all=True, filters=filters)
            if not containers:
                # 也尝试 Docker Swarm 堆栈标签
                filters_swarm = {"label": f"com.docker.stack.namespace={stack_name}"}
                containers = client.containers.list(all=True, filters=filters_swarm)
            return [process_container_summary(c, self_id) for c in containers]
        finally:
            client.close()
