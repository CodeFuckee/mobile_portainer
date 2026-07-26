"""
MCP Server 辅助函数。

提供与 FastAPI 无关的 Docker 客户端封装、数据库会话管理和认证检查。
"""

import os
from contextlib import contextmanager

import docker
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import APIKeyModel

# 从环境变量读取 API Key，用于 MCP 客户端认证
_MCP_API_KEY = os.environ.get("MOBILE_PORTAINER_API_KEY")


def get_docker_client_safe() -> docker.DockerClient:
    """
    返回 Docker 客户端，连接失败时抛出 RuntimeError。

    与 app.core.utils.get_docker_client 不同，此函数不依赖 FastAPI 的
    HTTPException，适用于 MCP 上下文。
    """
    try:
        return docker.from_env()
    except Exception as e:
        raise RuntimeError(f"无法连接到 Docker 守护进程：{e}")


@contextmanager
def get_db_session():
    """
    数据库会话上下文管理器。

    替代 FastAPI 的 Depends(get_db) 依赖注入模式，用于 MCP 工具函数中
    需要直接访问数据库的场景。

    用法:
        with get_db_session() as db:
            keys = db.query(APIKeyModel).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_api_key(api_key: str | None = None) -> bool:
    """
    验证 API Key 是否被授权访问 MCP 服务。

    验证策略（按优先级）：
    1. 如果设置了 MOBILE_PORTAINER_API_KEY 环境变量，则 api_key 必须与之匹配
    2. 如果未设置环境变量，尝试在数据库中查找该 api_key
    3. 如果环境变量和 api_key 都为空，允许通过（不认证模式）

    返回:
        True 表示认证通过，False 表示认证失败。
    """
    if _MCP_API_KEY:
        # 环境变量模式：必须精确匹配
        return api_key == _MCP_API_KEY

    if api_key:
        # 数据库验证模式
        try:
            with get_db_session() as db:
                exists = (
                    db.query(APIKeyModel).filter(APIKeyModel.key == api_key).first()
                )
                return exists is not None
        except Exception:
            return False

    # 无认证要求，允许通过
    return True
