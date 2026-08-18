"""
认证：JWT 签发与校验
"""

from jose import JWTError, jwt
import bcrypt
import os
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from src.config import runtime_config as config
from src.repo import runtime_models as models
from src.config.utils import utcnow


security = HTTPBearer()

# 本机免认证：单机工具默认无需登录（无凭据时以 admin 身份放行）。
# 设环境变量 RPA_AUTH_DISABLED=0 恢复原认证行为（对外部署时用）。
_AUTH_DISABLED = os.environ.get("RPA_AUTH_DISABLED", "1") != "0"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int, username: str) -> str:
    expire = utcnow() + config.ACCESS_TOKEN_EXPIRE
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, config.SECRET_KEY, algorithm=config.ALGORITHM)


def get_db():
    """数据库 session 依赖注入"""
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Cookie auth (for admin panel) ----------

def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db)) -> models.User:
    """从 request cookie 中读取 JWT token 并验证用户。"""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/admin/login"},
        )
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/admin/login"},
        )

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/admin/login"},
        )
    return user


# ---------- Header + Cookie auth (unified) ----------

# 允许空 header（用于 cookie fallback）
_optional_security = HTTPBearer(auto_error=False)


def _default_user(db: Session) -> models.User | None:
    """免认证模式的默认身份：admin（启动时种子必然存在）。"""
    return db.query(models.User).filter(models.User.username == "admin").first()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_security),
    db: Session = Depends(get_db)
) -> models.User:
    """从 JWT 解析当前用户。支持两种方式：
    1. Authorization: Bearer <token>（API 客户端）
    2. Cookie: access_token=<token>（管理后台页面）

    本机免认证模式（RPA_AUTH_DISABLED 默认开）：无凭据时返回 admin 默认用户，
    打开即用；携带凭据时仍严格校验（过期/无效 token 依旧 401）。
    """
    token = None
    if credentials:
        token = credentials.credentials
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        if _AUTH_DISABLED:
            user = _default_user(db)
            if user:
                return user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证令牌")

    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证令牌")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user
