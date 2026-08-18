"""
认证（已简化）：本机单人工具，密码功能已移除。

- 所有依赖 `get_current_user` 的 API 端点直接以 admin 默认身份放行（免登录）。
- 不再签发/校验 JWT，不再有登录/改密入口。
- `hash_password` 保留仅供启动时种子 admin 用户行（历史数据兼容，无安全语义）。
"""

import bcrypt
from types import SimpleNamespace
from fastapi import Depends, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from src.repo import runtime_models as models


security = HTTPBearer()
_optional_security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def get_db():
    """数据库 session 依赖注入"""
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _default_user(db: Session):
    """默认身份（admin）：优先取数据库种子行，缺失时返回虚拟对象（兼容 user.id/username 用法）。"""
    try:
        user = db.query(models.User).filter(models.User.username == "admin").first()
        if user:
            return user
    except Exception:
        pass
    return SimpleNamespace(id=1, username="admin")


def get_current_user(
    request: Request,
    credentials=None,
    db: Session = Depends(get_db),
):
    """本机免认证：忽略凭据，始终返回 admin 默认身份。"""
    return _default_user(db)


def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db)):
    """兼容占位：不再需要 cookie 登录，返回 None（调用方按未登录处理）。"""
    return None
