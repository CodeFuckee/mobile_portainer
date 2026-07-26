"""
MCP HTTP Server 入口点。

将 MCP Server 导出为 Streamable HTTP ASGI 应用，可嵌入 FastAPI 或其他 ASGI 框架。

用法:
    from app.mcp.http_server import mcp_http_app, mcp_session_manager

    # 在 FastAPI 中挂载
    app.mount("/mcp", mcp_http_app)

    # 在 lifespan 中管理 MCP 会话生命周期:
    async with mcp_session_manager.run():
        yield

Claude Code 配置示例:
    {
      "mcpServers": {
        "mobile-portainer": {
          "type": "http",
          "url": "https://your-server:8000/mcp"
        }
      }
    }

认证说明:
    本服务不通过 MCP 协议层做认证（不启用 OAuth）。
    如需认证，可通过以下方式之一：
    1. 在 Claude Code 配置中使用 headers 字段传 API Key:
       "headers": {"Authorization": "Bearer ${MOBILE_PORTAINER_API_KEY}"}
    2. 在 FastAPI 层面添加中间件校验 /mcp 路径的 X-API-Key 或 Authorization 头
"""

from .server import app as _mcp_app

# ---- 配置 MCP 端点路径 ----
# streamable_http_path 默认是 /mcp，但由于我们通过 FastAPI mount("/mcp", ...)
# 挂载，子应用内部的路径 /mcp 会变成 /mcp/mcp（双重路径）。
# 将其设为 / 后，有效路径就是 /mcp，与 Claude Code 配置的 URL 一致。
_mcp_app.settings.streamable_http_path = "/"

# ---- 创建 Streamable HTTP ASGI 应用 ----
mcp_http_app = _mcp_app.streamable_http_app()

# 导出 session manager，供 FastAPI lifespan 管理生命周期
mcp_session_manager = _mcp_app._session_manager
