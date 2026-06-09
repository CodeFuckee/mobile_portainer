from fastapi import Security, HTTPException, status, Depends, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from app.core.config import API_KEY_NAME, ADMIN_USER, ADMIN_PASSWORD
from app.db.database import get_db
from app.db.models import APIKeyModel

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def _verify_admin_credentials(request: Request) -> bool:
    """检查请求中的 Admin 凭据是否有效"""
    admin_user = request.headers.get("X-Admin-User")
    admin_pass = request.headers.get("X-Admin-Pass")
    return admin_user == ADMIN_USER and admin_pass == ADMIN_PASSWORD


async def get_api_key(
    request: Request,
    api_key_header: str = Security(api_key_header),
    db: Session = Depends(get_db),
):
    # 先尝试 API Key 认证
    if api_key_header:
        key_record = (
            db.query(APIKeyModel).filter(APIKeyModel.key == api_key_header).first()
        )
        if key_record:
            return api_key_header

    # 回退到 Admin 凭据认证（Web UI 登录用户）
    if _verify_admin_credentials(request):
        return "admin"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key or Admin Credentials",
    )
