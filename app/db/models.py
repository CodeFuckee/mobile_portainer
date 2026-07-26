from sqlalchemy import Column, String, DateTime, Integer
from datetime import datetime
import uuid
from .database import Base


class APIKeyModel(Base):
    __tablename__ = "api_keys"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    key = Column(String, unique=True, index=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ClusterNode(Base):
    __tablename__ = "cluster_nodes"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, index=True)
    base_url = Column(String)
    admin_user = Column(String)
    admin_pass = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class AdminCredentialModel(Base):
    """管理员密码哈希；固定使用 id=1 的单条配置记录。"""

    __tablename__ = "admin_credentials"

    id = Column(Integer, primary_key=True, default=1)
    password_hash = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SMTPSettingsModel(Base):
    """SMTP 邮箱配置；固定使用 id=1 的单条配置记录。密码经过加密存储。"""

    __tablename__ = "smtp_settings"

    id = Column(Integer, primary_key=True, default=1)
    host = Column(String, nullable=True)
    port = Column(Integer, nullable=True)
    username = Column(String, nullable=True)
    encrypted_password = Column(String, nullable=True)  # 加密后的 SMTP 密码
    from_email = Column(String, nullable=True)
    from_name = Column(String, nullable=True)
    use_ssl = Column(Integer, default=0)  # 0/1 布尔标记
    use_starttls = Column(Integer, default=1)
    timeout = Column(Integer, default=10)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserProfileModel(Base):
    """用户个人信息；固定使用 id=1 的单条配置记录。"""

    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True, default=1)
    display_name = Column(String, nullable=True)  # 显示名称（昵称）
    email = Column(String, nullable=True)  # 联系邮箱
    avatar = Column(String, nullable=True)  # 头像 URL 或 base64
    bio = Column(String, nullable=True)  # 个人简介
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
