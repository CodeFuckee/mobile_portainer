"""
MCP HTTP Server — Streamable HTTP 传输模式。

将 MCP Server 导出为 Streamable HTTP ASGI 应用，
可嵌入 FastAPI 或其他 ASGI 框架，支持远程 AI 助手访问。

=== Streamable HTTP vs stdio ===

stdio 模式（server.py）：
  - 适合本地使用，父进程启动子进程通信
  - 单连接、单会话

Streamable HTTP 模式（本模块）：
  - 适合远程访问、多客户端
  - 支持会话管理、OAuth 认证
  - 可与现有 FastAPI 应用集成，共享端口和中间件

=== 用法 ===

1. 在 FastAPI 中挂载子应用：
    from app.mcp.http_server import mcp_http_app, mcp_session_manager

    app = FastAPI()

    @app.on_event("startup")
    async def startup():
        async with mcp_session_manager.run():
            # 会话管理器已启动
            pass

    app.mount("/mcp", mcp_http_app)

2. 使用 FastAPI lifespan（推荐）：
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp_session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/mcp", mcp_http_app)

=== Claude Code 配置示例 ===

    {
      "mcpServers": {
        "mobile-portainer": {
          "type": "http",
          "url": "https://your-server:8000/mcp"
        }
      }
    }

=== 路径说明 ===

FastMCP 的 streamable_http_path 默认为 "/mcp"。
由于我们通过 FastAPI 的 `app.mount("/mcp", ...)` 挂载子应用，
子应用内部的 "/mcp" 路径会变成 "/mcp/mcp"（双重路径）。
因此将其设为 "/"，让最终有效路径就是 "/mcp"。

即：
  客户端请求 → FastAPI /mcp → 子应用 / → MCP 处理

=== 认证说明 ===

本服务不通过 MCP 协议层做认证（不启用 OAuth）。
如需认证，可通过以下方式之一：

1. 在 Claude Code 配置中使用 headers 字段传 API Key：
    "headers": {"Authorization": "Bearer ${MOBILE_PORTAINER_API_KEY}"}

2. 在 FastAPI 层面添加中间件校验 /mcp 路径的 X-API-Key 或 Authorization 头：
    @app.middleware("http")
    async def auth_middleware(request, call_next):
        if request.url.path.startswith("/mcp"):
            # 验证 API Key
            pass
        return await call_next(request)

3. 启用 OAuth 认证（见 auth_provider.py）：
    在 FastMCP 实例上配置 OAuth 提供者，由 MCP 协议层处理认证流程
"""

from .server import app as _mcp_app

# ---- 配置 MCP 端点路径 ----
# 将路径设为 "/"，配合 FastAPI mount("/mcp", ...) 使用
# 这样客户端请求 /mcp 时不会被路由到 /mcp/mcp
_mcp_app.settings.streamable_http_path = "/"

# ---- 创建 Streamable HTTP ASGI 应用 ----
# streamable_http_app() 是 FastMCP 提供的方法，
# 返回一个标准的 ASGI 3 应用实例，可直接用 app.mount() 挂载
# 底层使用 SSE (Server-Sent Events) 实现流式响应
mcp_http_app = _mcp_app.streamable_http_app()

# ---- 导出会话管理器 ----
# SessionManager 负责管理 MCP 会话的生命周期：
# - 创建和销毁客户端会话
# - 管理会话超时和清理
# - 处理断线重连
# 需要在 FastAPI 的 lifespan 中启动和关闭
mcp_session_manager = _mcp_app._session_manager
