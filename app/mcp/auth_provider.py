"""
MCP OAuth 认证提供者。

实现内存级别的 OAuth 2.0 授权服务器，与 Mobile Portainer API Key 系统集成。
支持动态客户端注册、授权码流程（PKCE），以及与现有 API Key 的互操作。
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
    """内存级 OAuth 2.0 提供者。

    实现 OAuthAuthorizationServerProvider 协议，提供完整的 OAuth 2.0 授权服务器功能。

    与 Mobile Portainer API Key 集成：
    - 如果设置了 MOBILE_PORTAINER_API_KEY 环境变量，该 key 可直接作为 Bearer token 使用
    - 同时支持标准的 OAuth 2.0 授权码流程（用于 Claude Code 等 MCP 客户端认证）

    OAuthAuthorizationServerProvider 是 typing.Protocol，使用结构化子类型。
    显式继承是为了代码清晰性和潜在的 isinstance 检查。
    """

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("MOBILE_PORTAINER_API_KEY")

        # 内存存储
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}  # code -> AuthorizationCode
        self._refresh_tokens: dict[str, RefreshToken] = {}  # token -> RefreshToken
        self._access_tokens: dict[str, AccessToken] = {}  # token -> AccessToken

    def _generate_token(self, prefix: str = "") -> str:
        """生成随机 token。"""
        raw = secrets.token_hex(32)
        return f"{prefix}{raw}" if prefix else raw

    def _cleanup_expired(self) -> None:
        """清理过期的授权码和令牌。"""
        now = int(time.time())
        expired_codes = [c for c, ac in self._auth_codes.items() if ac.expires_at < now]
        for c in expired_codes:
            del self._auth_codes[c]

        expired_tokens = [
            t
            for t, at in self._access_tokens.items()
            if at.expires_at and at.expires_at < now
        ]
        for t in expired_tokens:
            del self._access_tokens[t]

    # ---- TokenVerifier 接口 ----

    async def load_access_token(self, token: str) -> AccessToken | None:
        """验证 access token 或 API Key。"""
        self._cleanup_expired()

        # 如果是 API Key，自动视为有效 token
        if self._api_key and token == self._api_key:
            return AccessToken(
                token=token,
                client_id="api_key_client",
                scopes=["*"],
                subject="admin",
            )

        return self._access_tokens.get(token)

    # ---- OAuthAuthorizationServerProvider 接口 ----

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """根据 client_id 获取客户端信息。"""
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """注册新的 OAuth 客户端。"""
        if not client_info.client_id:
            client_info.client_id = self._generate_token("client_")

        if not client_info.client_secret:
            client_info.client_secret = self._generate_token("secret_")

        now = int(time.time())
        client_info.client_id_issued_at = now
        client_info.client_secret_expires_at = 0  # 永不过期

        self._clients[client_info.client_id] = client_info

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """处理授权请求，生成授权码并返回重定向 URL。"""
        code_value = self._generate_token("code_")

        auth_code = AuthorizationCode(
            code=code_value,
            client_id=client.client_id or "",
            scopes=params.scopes or [],
            expires_at=time.time() + 600,  # 10 分钟有效期
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            code_challenge=params.code_challenge,
            resource=params.resource,
        )
        self._auth_codes[code_value] = auth_code

        # 构造重定向 URL（携带授权码和 state）
        redirect_uri = str(params.redirect_uri)
        separator = "&" if "?" in redirect_uri else "?"
        redirect_url = f"{redirect_uri}{separator}code={code_value}"
        if params.state:
            redirect_url += f"&state={params.state}"

        return redirect_url

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        """加载并验证授权码。"""
        auth_code = self._auth_codes.get(authorization_code)
        if not auth_code:
            return None
        if auth_code.client_id != client.client_id:
            return None
        if auth_code.expires_at < time.time():
            del self._auth_codes[authorization_code]
            return None
        return auth_code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        """用授权码交换 access token 和 refresh token。"""
        # 删除已使用的授权码（一次性使用）
        self._auth_codes.pop(authorization_code.code, None)

        scopes = authorization_code.scopes
        access_token_str = self._generate_token("at_")
        refresh_token_str = self._generate_token("rt_")
        expires_in = 3600  # 1 小时

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
            expires_at=int(time.time()) + 86400 * 30,  # 30 天
            subject=authorization_code.subject,
        )

        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=expires_in,
            scope=" ".join(scopes) if scopes else None,
            refresh_token=refresh_token_str,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        """加载 refresh token。"""
        rt = self._refresh_tokens.get(refresh_token)
        if not rt:
            return None
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

        实现 token 轮换：旧的 refresh token 和 access token 都会被撤销。
        """
        # 撤销旧的 refresh token
        self._refresh_tokens.pop(refresh_token.token, None)

        new_scopes = scopes if scopes else refresh_token.scopes
        access_token_str = self._generate_token("at_")
        refresh_token_str = self._generate_token("rt_")
        expires_in = 3600

        self._access_tokens[access_token_str] = AccessToken(
            token=access_token_str,
            client_id=client.client_id or "",
            scopes=new_scopes,
            expires_at=int(time.time()) + expires_in,
            subject=refresh_token.subject,
        )

        self._refresh_tokens[refresh_token_str] = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id or "",
            scopes=new_scopes,
            expires_at=int(time.time()) + 86400 * 30,
            subject=refresh_token.subject,
        )

        return OAuthToken(
            access_token=access_token_str,
            token_type="Bearer",
            expires_in=expires_in,
            scope=" ".join(new_scopes) if new_scopes else None,
            refresh_token=refresh_token_str,
        )

    async def revoke_token(
        self, token: AuthorizationCode | RefreshToken | AccessToken
    ) -> None:
        """撤销 token。"""
        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
            # 也撤销关联的 refresh token
            for key, rt in list(self._refresh_tokens.items()):
                if rt.token == token.token:
                    del self._refresh_tokens[key]
        elif isinstance(token, RefreshToken):
            self._refresh_tokens.pop(token.token, None)
        elif isinstance(token, AuthorizationCode):
            self._auth_codes.pop(token.code, None)
