"""认证路由"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas, auth
from src.repo import runtime_models as models

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(req: schemas.LoginRequest, db: Session = Depends(auth.get_db)):
    user = db.query(models.User).filter(models.User.username == req.username).first()
    if not user or not auth.verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = auth.create_access_token(user.id, user.username)
    return schemas.TokenResponse(access_token=token)


@router.post("/password")
def change_password(
    req: schemas.PasswordChangeRequest,
    db: Session = Depends(auth.get_db),
    user: models.User = Depends(auth.get_current_user),
):
    if not auth.verify_password(req.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="原密码错误")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度至少为 6 位")
    db_user = db.get(models.User, user.id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    db_user.hashed_password = auth.hash_password(req.new_password)
    db.commit()
    return {"ok": True}
