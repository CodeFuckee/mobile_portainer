"""
Mobile Portainer MCP Server 入口点。

通过 stdio 传输提供 MCP 服务，让 AI 助手能管理 Docker 资源。

启动方式:
    python -m app.mcp.server

Claude Desktop 配置示例:
    {
      "mcpServers": {
        "mobile-portainer": {
          "command": "python",
          "args": ["-m", "app.mcp.server"],
          "env": {
            "MOBILE_PORTAINER_API_KEY": "your-api-key"
          }
        }
      }
    }
"""

import logging

from mcp.server.fastmcp import FastMCP

from .helpers import get_docker_client_safe
from .tools import register_all_tools

logger = logging.getLogger("mcp.portainer")
logger.setLevel(logging.INFO)

# 创建 FastMCP 实例
app = FastMCP("mobile-portainer")

# 注册所有 Docker 管理工具
register_all_tools(app)

# 启动时检查 Docker 连接
try:
    get_docker_client_safe()
    logger.info("Docker 守护进程连接成功")
except RuntimeError as e:
    logger.warning("无法连接到 Docker 守护进程：%s", e)


def main() -> None:
    """启动 MCP Server，使用 stdio 传输。"""
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
