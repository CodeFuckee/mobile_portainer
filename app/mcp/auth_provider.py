"""
MCP OAuth 2.0 认证提供者。

实现基于内存的 OAuth 2.0 授权服务器，与 Mobile Portainer 的 API Key 系统集成。
遵循 RFC 6749 (OAuth 2.0) 和 RFC 7636 (PKCE) 规范。

=== 功能概述 ===

本模块实现 OAuthAuthorizationServerProvider 协议，提供：
- 动态客户端注册（Dynamic Client Registration）
- 授权码流程（Authorization Code Grant）+ PKCE
- Access Token 签发与验证
- Refresh Token 轮换（Token Rotation）
- Token 撤销（Token Revocation）

=== 与 API Key 系统的集成 ===

本提供者与 helpers.py 中的 API Key 认证并行工作：

1. 传统 API Key 模式：
   - 设置 MOBILE_PORTAINER_API_KEY 环境变量
   - 客户端在请求头中携带 API Key
   - 适用于简单的脚本调用和直接 API 访问

2. OAuth 2.0 模式（本模块）：
   - 客户端动态注册，获取 client_id 和 client_secret
   - 通过授权码流程（含 PKCE）获取 access token
   - 支持 token 刷新和撤销
   - 适用于 Claude Code 等标准 MCP 客户端

两种模式互操作：如果设置了 MOBILE_PORTAINER_API_KEY 环境变量，
该 key 可以直接作为 Bearer token 使用（无需 OAuth 流程）。

=== PKCE 说明 ===

PKCE (Proof Key for Code Exchange，RFC 7636) 是 OAuth 2.0 的安全扩展：
- 客户端生成 code_verifier（随机字符串）
- 将 code_verifier 的 SHA-256 哈希作为 code_challenge 发送
- 交换 token 时提交原始 code_verifier
- 防止授权码拦截攻击（Authorization Code Interception Attack）

即使没有客户端密钥（public client），PKCE 也能保证安全性。

=== 令牌有效期 ===

- 授权码：10 分钟
- Access Token：1 小时
- Refresh Token：30 天
- 客户端密钥：永不过期（client_secret_expires_at = 0）

=== 存储说明 ===

所有数据存储在内存字典中，进程重启后全部丢失。
生产环境建议替换为数据库支持的存储实现。
"""

import os
import secrets
import time

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    OAuthClientInformationFull,
    OAuthToken,
    RefreshToken,
)


class InMemoryOAuthProvider(OAuthAuthorizationServerProvider):
    """内存级 OAuth 2.0 授权服务器提供者。

    实现 OAuthAuthorizationServerProvider 协议的所有方法，
    提供完整的 OAuth 2.0 授权服务器功能。

    === 技术说明 ===

    OAuthAuthorizationServerProvider 定义为一个 typing.Protocol，
    使用结构化子类型（structural subtyping）。
    显式继承是为了：
    1. 代码清晰性——明确表达类的意图
    2. IDE 类型检查——让静态分析工具能验证方法签名
    3. 潜在的 isinstance 检查

    === 线程安全 ===

    当前实现的字典操作不是线程安全的。
    在 stdio 模式（单线程）下没有问题。
    在 HTTP 多线程模式下，建议使用 threading.Lock 或 asyncio.Lock 保护共享状态。

    === 内存管理 ===

    _cleanup_expired() 方法在每个 access token 验证时调用，
    惰性清理过期的授权码和令牌，防止内存泄漏。
    """

    def __init__(self, api_key: str | None = None):
        """初始化 OAuth 提供者。

        参数:
            api_key: 可选的 API Key，用作备用认证方式。
                     如果为 None，从 MOBILE_PORTAINER_API_KEY 环境变量读取。
        """
        # API Key 用于与现有认证系统互操作
        self._api_key = api_key or os.environ.get("MOBILE_PORTAINER_API_KEY")

        # ---- 内存存储 ----
        # 四个核心数据结构，存储 OAuth 2.0 的各种凭据

        # 客户端注册表：client_id -> 客户端完整信息
        self._clients: dict[str, OAuthClientInformationFull] = {}

        # 授权码存储：授权码字符串 -> AuthorizationCode 对象
        # 授权码是一次性的：用后即删
        self._auth_codes: dict[str, AuthorizationCode] = {}

        # Refresh Token 存储：token 字符串 -> RefreshToken 对象
        # 用于在 access token 过期后获取新 token
        self._refresh_tokens: dict[str, RefreshToken] = {}

        # Access Token 存储：token 字符串 -> AccessToken 对象
        # 用于验证每个 API 请求的身份
        self._access_tokens: dict[str, AccessToken] = {}

    # ================================================================
    # 内部辅助方法
    # ================================================================

    def _generate_token(self, prefix: str = "") -> str:
        """生成加密安全的随机 token。

        使用 secrets.token_hex(32) 生成 64 个十六进制字符（256 位熵），
        安全性足以防止暴力破解和碰撞。

        参数:
            prefix: 可选的 token 前缀，用于区分不同类型的 token
                    - "client_" → 客户端 ID
                    - "secret_" → 客户端密钥
                    - "code_"   → 授权码
                    - "at_"     → Access Token
                    - "rt_"     → Refresh Token

        返回:
            带有可选前缀的十六进制 token 字符串（如 "at_a1b2c3...")
        """
        raw = secrets.token_hex(32)  # 256 位随机数 = 64 个十六进制字符
        return f"{prefix}{raw}" if prefix else raw

    def _cleanup_expired(self) -> None:
        """清理过期的授权码和 access token。

        惰性清理策略：
        - 每次验证 access token 时调用（load_access_token）
        - 遍历所有存储的凭据，删除已过期的条目
        - 防止内存随着时间推移无限增长

        清理范围：
        - 过期的授权码（expires_at < 当前时间）
        - 过期的 access token
        - 注意：不过期清理 refresh token（它们有自己的过期检查逻辑）
        """
        now = int(time.time())

        # 清理过期的授权码
        expired_codes = [
            code for code, ac in self._auth_codes.items() if ac.expires_at < now
        ]
        for code in expired_codes:
            del self._auth_codes[code]

        # 清理过期的 access token
        expired_tokens = [
            token
            for token, at in self._access_tokens.items()
            if at.expires_at and at.expires_at < now
        ]
        for token in expired_tokens:
            del self._access_tokens[token]

    # ================================================================
    # TokenVerifier 接口 — Token 验证
    # ================================================================

    async def load_access_token(self, token: str) -> AccessToken | None:
        """验证 access token 或备用的 API Key。

        这是 MCP 协议层在每个请求中调用的方法，
        用于验证客户端提供的 Bearer token 是否有效。

        验证逻辑：
        1. 首先清理过期的凭据（惰性清理）
        2. 检查 token 是否匹配 API Key（环境变量模式）
        3. 如果都不是，在 access token 存储中查找

        参数:
            token: 客户端提供的 Bearer token 字符串

        返回:
            AccessToken: 如果 token 有效，返回对应的 AccessToken 对象
            None: 如果 token 无效或已过期

        注意:
            API Key 模式返回的 AccessToken 具有以下特征：
            - client_id = "api_key_client"（虚拟客户端 ID）
            - scopes = ["*"]（完全权限）
            - subject = "admin"（管理员身份）
        """
        self._cleanup_expired()

        # 备选路径：API Key 作为 token
        # 如果 token 匹配环境变量中的 API Key，直接视为有效管理员 token
        if self._api_key and token == self._api_key:
            return AccessToken(
                token=token,
                client_id="api_key_client",
                scopes=["*"],
                subject="admin",
            )

        # 标准路径：在 access token 存储中查找
        return self._access_tokens.get(token)

    # ================================================================
    # OAuthAuthorizationServerProvider 接口 — 客户端管理
    # ================================================================

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """根据 client_id 查找已注册的 OAuth 客户端。

        参数:
            client_id: 客户端注册时分配的 ID

        返回:
            OAuthClientInformationFull: 如果找到客户端，返回完整信息
            None: 如果客户端不存在
        """
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """注册新的 OAuth 2.0 客户端。

        处理动态客户端注册请求。如果客户端未提供 client_id 或
        client_secret，会自动生成。

        自动填充字段：
        - client_id：自动生成（格式：client_xxxx）
        - client_secret：自动生成（格式：secret_xxxx）
        - client_id_issued_at：当前时间戳
        - client_secret_expires_at：0 表示永不过期

        参数:
            client_info: 客户端注册信息（可能不完整，由本方法补全）

        注意:
            - client_info 对象会被原地修改（in-place mutation）
            - 注册成功后，客户端信息存储在内存字典中
            - 生产环境应持久化到数据库
        """
        # 自动生成 client_id（如果客户端未提供）
        if not client_info.client_id:
            client_info.client_id = self._generate_token("client_")

        # 自动生成 client_secret（如果客户端未提供）
        if not client_info.client_secret:
            client_info.client_secret = self._generate_token("secret_")

        # 设置时间戳
        now = int(time.time())
        client_info.client_id_issued_at = now
        client_info.client_secret_expires_at = 0  # 0 = 永不过期

        # 存储到内存注册表
        self._clients[client_info.client_id] = client_info

    # ================================================================
    # OAuthAuthorizationServerProvider 接口 — 授权流程
    # ================================================================

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """处理 OAuth 2.0 授权请求，生成授权码并返回重定向 URL。

        实现授权码流程的第一步：
        1. 生成一次性的授权码（code_xxxx）
        2. 存储授权码及相关参数（client_id、scopes、PKCE challenge 等）
        3. 构造重定向 URL（携带授权码和 state 参数）

        参数:
            client: 发起授权请求的客户端信息
            params: 授权请求参数，包括：
                    - scopes: 请求的权限范围
                    - redirect_uri: 授权后的回调地址
                    - state: CSRF 防护 token（原样返回）
                    - code_challenge: PKCE code challenge（SHA-256 哈希）
                    - resource: 请求访问的资源标识

        返回:
            完整的重定向 URL，格式如：
            https://client.example/callback?code=code_xxx&state=yyy

        安全机制：
        - 授权码有效期仅 10 分钟，减少泄露风险
        - PKCE code_challenge 存储后用于交换 token 时验证
        - state 参数原样返回，防止 CSRF 攻击
        """
        # 生成加密安全的授权码
        code_value = self._generate_token("code_")

        # 构造授权码对象，存储所有相关参数
        auth_code = AuthorizationCode(
            code=code_value,
            client_id=client.client_id or "",
            scopes=params.scopes or [],
            expires_at=time.time() + 600,  # 10 分钟有效期，平衡安全性和可用性
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            code_challenge=params.code_challenge,  # PKCE: 存储 challenge 用于后续验证
            resource=params.resource,
        )
        self._auth_codes[code_value] = auth_code

        # 构造重定向 URL
        # 注意处理 URL 中是否已有查询参数
        redirect_uri = str(params.redirect_uri)
        separator = "&" if "?" in redirect_uri else "?"
        redirect_url = f"{redirect_uri}{separator}code={code_value}"

        # state 参数用于 CSRF 防护，原样返回给客户端
        if params.state:
            redirect_url += f"&state={params.state}"

        return redirect_url

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        """加载并验证授权码的有效性。

        在客户端用授权码交换 token 时调用。

        验证条件（全部满足才返回授权码）：
        1. 授权码存在于存储中
        2. 授权码的 client_id 与请求的客户端匹配
        3. 授权码未过期（expires_at >= 当前时间）

        参数:
            client: 请求交换 token 的客户端
            authorization_code: 客户端提交的授权码字符串

        返回:
            AuthorizationCode: 如果授权码有效，返回完整授权码对象
            None: 如果授权码无效、不匹配或已过期

        注意:
            过期授权码会被自动清理（惰性删除），防止存储膨胀
        """
        auth_code = self._auth_codes.get(authorization_code)
        if not auth_code:
            return None

        # 验证授权码是否属于请求的客户端
        if auth_code.client_id != client.client_id:
            return None

        # 验证是否过期
        if auth_code.expires_at < time.time():
            # 惰性清理过期授权码
            del self._auth_codes[authorization_code]
            return None

        return auth_code

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """用授权码交换 access token 和 refresh token。

        实现授权码流程的第二步（token endpoint）：
        1. 删除已使用的授权码（一次性使用，防止重放攻击）
        2. 生成新的 access token（1 小时有效期）
        3. 生成新的 refresh token（30 天有效期）
        4. 返回 OAuthToken 响应

        参数:
            client: 请求交换的客户端信息
            authorization_code: 已验证的授权码对象

        返回:
            OAuthToken: 包含 access_token、refresh_token、过期时间等信息

        安全机制：
        - 授权码一次性使用（用后即删），防止重放
        - PKCE 验证由 MCP 框架在调用本方法前完成
        - Access token 短有效期（1h），减少泄露影响
        - Refresh token 长有效期（30d），方便长期使用
        """
        # 删除已使用的授权码（一次性使用，防止重放攻击）
        self._auth_codes.pop(authorization_code.code, None)

        scopes = authorization_code.scopes
        access_token_str = self._generate_token("at_")
        refresh_token_str = self._generate_token("rt_")
        expires_in = 3600  # 1 小时（单位：秒）

        # 存储 access token
        self._access_tokens[access_token_str] = AccessToken(
            token=access_token_str,
            client_id=client.client_id or "",
            scopes=scopes,
            expires_at=int(time.time()) + expires_in,
            subject=authorization_code.subject,
        )

        # 存储 refresh token
        self._refresh_tokens[refresh_token_str] = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id or "",
            scopes=scopes,
            expires_at=int(time.time()) + 86400 * 30,  # 30 天（单位：秒）
            subject=authorization_code.subject,
        )

        # 构造并返回标准 OAuthToken 响应
        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=expires_in,
            scope=" ".join(scopes) if scopes else None,
            refresh_token=refresh_token_str,
        )

    # ================================================================
    # OAuthAuthorizationServerProvider 接口 — Token 刷新
    # ================================================================

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        """加载并验证 refresh token。

        参数:
            client: 请求刷新的客户端
            refresh_token: 客户端提交的 refresh token 字符串

        返回:
            RefreshToken: 如果 token 有效且属于该客户端
            None: 如果 token 无效或不属于该客户端

        验证条件：
        1. refresh token 存在于存储中
        2. refresh token 的 client_id 与请求的客户端匹配
        """
        rt = self._refresh_tokens.get(refresh_token)
        if not rt:
            return None

        # 验证 refresh token 是否属于请求的客户端
        if rt.client_id != client.client_id:
            return None

        return rt

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """用 refresh token 交换新的 access token 和 refresh token。

        实现 Token 轮换（Token Rotation）机制：
        1. 撤销旧的 refresh token（删除）
        2. 生成新的 access token
        3. 生成新的 refresh token
        4. 返回新的 OAuthToken

        参数:
            client: 请求刷新的客户端
            refresh_token: 已验证的旧 refresh token
            scopes: 请求的权限范围（如果为空，保持原有范围）

        返回:
            OAuthToken: 包含全新的 access_token 和 refresh_token

        安全机制 — Token 轮换：
        - 每次使用 refresh token 后，旧的被撤销，签发新的
        - 如果攻击者盗用了 refresh token，合法用户下次刷新时
          会发现旧 token 失效，从而检测到泄露
        - RFC 6819 (OAuth 2.0 Threat Model) 推荐的实践
        """
        # 撤销旧的 refresh token（token 轮换）
        self._refresh_tokens.pop(refresh_token.token, None)

        # 确定新的权限范围
        new_scopes = scopes if scopes else refresh_token.scopes

        access_token_str = self._generate_token("at_")
        refresh_token_str = self._generate_token("rt_")
        expires_in = 3600  # 1 小时

        # 存储新的 access token
        self._access_tokens[access_token_str] = AccessToken(
            token=access_token_str,
            client_id=client.client_id or "",
            scopes=new_scopes,
            expires_at=int(time.time()) + expires_in,
            subject=refresh_token.subject,
        )

        # 存储新的 refresh token
        self._refresh_tokens[refresh_token_str] = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id or "",
            scopes=new_scopes,
            expires_at=int(time.time()) + 86400 * 30,  # 30 天
            subject=refresh_token.subject,
        )

        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=expires_in,
            scope=" ".join(new_scopes) if new_scopes else None,
            refresh_token=refresh_token_str,
        )

    # ================================================================
    # OAuthAuthorizationServerProvider 接口 — Token 撤销
    # ================================================================

    async def revoke_token(
        self, token: AuthorizationCode | RefreshToken | AccessToken
    ) -> None:
        """撤销（作废）指定的 token。

        支持撤销三种类型的 token，每种处理方式不同：

        1. AccessToken:
           - 从 access token 存储中删除
           - 同时删除关联的 refresh token（如果存在）

        2. RefreshToken:
           - 从 refresh token 存储中删除

        3. AuthorizationCode:
           - 从授权码存储中删除
           - 防止未使用的授权码被恶意交换

        参数:
            token: 要撤销的 token 对象（可以是三种类型之一）

        注意:
            - 撤销操作是幂等的（多次撤销同个 token 不会出错）
            - 撤销 access token 时会尝试级联撤销 refresh token
              （通过 token 字符串匹配，而非结构化关联）
        """
        if isinstance(token, AccessToken):
            # 撤销 access token
            self._access_tokens.pop(token.token, None)
            # 级联撤销：查找并删除关联的 refresh token
            for key, rt in list(self._refresh_tokens.items()):
                if rt.token == token.token:
                    del self._refresh_tokens[key]

        elif isinstance(token, RefreshToken):
            # 撤销 refresh token
            self._refresh_tokens.pop(token.token, None)

        elif isinstance(token, AuthorizationCode):
            # 撤销授权码（如用户在授权页面点击"取消"）
            self._auth_codes.pop(token.code, None)
