"""
Captured Element API: 浏览器扩展上传的捕获元素
本地桌面应用模式，无需 JWT 认证
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.orm import Session

from .. import schemas
from src.repo import runtime_models as models
from src.repo.models import SessionLocal

router = APIRouter(prefix="/api/elements", tags=["Captured Elements"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=schemas.CapturedElementOut)
def create_element(
    payload: schemas.CapturedElementIn,
    db: Session = Depends(get_db),
):
    el = models.CapturedElement(
        user_id=1,  # 本地单用户模式，固定 admin
        name=payload.name,
        description=payload.description,
        locator=payload.locator,
        locator_type=payload.locator_type,
        method=payload.method,
        candidates=__import__("json").dumps(payload.candidates),
        features=__import__("json").dumps(payload.features),
        css_selector=payload.css_selector,
        tag=payload.tag,
        text_preview=payload.text_preview,
        page_url=payload.page_url,
        hostname=payload.hostname,
        screenshot=payload.screenshot,
    )
    db.add(el)
    db.commit()
    db.refresh(el)
    # 反序列化 JSON 字段用于输出
    el.candidates = __import__("json").loads(el.candidates) if el.candidates else []
    el.features = __import__("json").loads(el.features) if el.features else {}
    return el


@router.get("", response_model=list[schemas.CapturedElementOut])
def list_elements(
    hostname: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(models.CapturedElement)
    if hostname:
        q = q.filter(models.CapturedElement.hostname == hostname)
    items = q.order_by(models.CapturedElement.created_at.desc()).all()
    # 反序列化 JSON 字段
    for item in items:
        try:
            item.candidates = __import__("json").loads(item.candidates) if item.candidates else []
        except Exception:
            item.candidates = []
        try:
            item.features = __import__("json").loads(item.features) if item.features else {}
        except Exception:
            item.features = {}
    return items


@router.get("/hosts", response_model=list[str])
def list_hosts(
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.CapturedElement.hostname)
        .distinct()
        .all()
    )
    return sorted([r[0] for r in rows if r[0]])


@router.get("/export")
def export_elements(
    db: Session = Depends(get_db),
):
    """导出所有元素为 JSON 数组（供下载备份）"""
    items = db.query(models.CapturedElement).order_by(models.CapturedElement.created_at.desc()).all()
    result = []
    for item in items:
        result.append({
            "name": item.name,
            "description": item.description,
            "locator": item.locator,
            "locator_type": item.locator_type,
            "method": item.method,
            "candidates": __import__("json").loads(item.candidates) if item.candidates else [],
            "features": __import__("json").loads(item.features) if item.features else {},
            "css_selector": item.css_selector,
            "tag": item.tag,
            "text_preview": item.text_preview,
            "page_url": item.page_url,
            "hostname": item.hostname,
            "screenshot": item.screenshot,
        })
    return result


@router.post("/import")
def import_elements(
    payload: list[dict],
    db: Session = Depends(get_db),
):
    """批量导入元素（追加模式，不覆盖已有）"""
    imported = 0
    failed = 0
    errors = []
    mapping = {}
    for idx, item in enumerate(payload):
        try:
            name = item.get("name")
            if not name:
                failed += 1
                errors.append(f"#{idx + 1}: 缺少 name")
                continue
            old_id = item.get("id")
            el = models.CapturedElement(
                user_id=1,
                name=name,
                description=item.get("description") or "",
                locator=item.get("locator") or "",
                locator_type=item.get("locator_type") or "css",
                method=item.get("method") or "ele",
                candidates=__import__("json").dumps(item.get("candidates") or []),
                features=__import__("json").dumps(item.get("features") or {}),
                css_selector=item.get("css_selector") or "",
                tag=item.get("tag") or "",
                text_preview=item.get("text_preview") or "",
                page_url=item.get("page_url") or "",
                hostname=item.get("hostname") or "",
                screenshot=item.get("screenshot") or "",
            )
            db.add(el)
            db.flush()
            if old_id is not None:
                mapping[str(old_id)] = el.id
            imported += 1
        except Exception as e:
            failed += 1
            errors.append(f"#{idx + 1}: {str(e)}")
    db.commit()
    return {"imported": imported, "failed": failed, "errors": errors, "mapping": mapping}


@router.get("/{element_id}", response_model=schemas.CapturedElementOut)
def get_element(
    element_id: int,
    db: Session = Depends(get_db),
):
    el = db.query(models.CapturedElement).filter(
        models.CapturedElement.id == element_id,
    ).first()
    if not el:
        raise HTTPException(status_code=404, detail="元素不存在")
    try:
        el.candidates = __import__("json").loads(el.candidates) if el.candidates else []
    except Exception:
        el.candidates = []
    try:
        el.features = __import__("json").loads(el.features) if el.features else {}
    except Exception:
        el.features = {}
    return el


@router.patch("/{element_id}", response_model=schemas.CapturedElementOut)
def update_element(
    element_id: int,
    payload: schemas.CapturedElementUpdate,
    db: Session = Depends(get_db),
):
    el = db.query(models.CapturedElement).filter(
        models.CapturedElement.id == element_id,
    ).first()
    if not el:
        raise HTTPException(status_code=404, detail="元素不存在")
    if payload.name is not None:
        el.name = payload.name
    if payload.description is not None:
        el.description = payload.description
    db.commit()
    db.refresh(el)
    try:
        el.candidates = __import__("json").loads(el.candidates) if el.candidates else []
    except Exception:
        el.candidates = []
    try:
        el.features = __import__("json").loads(el.features) if el.features else {}
    except Exception:
        el.features = {}
    return el


@router.delete("/{element_id}")
def delete_element(
    element_id: int,
    db: Session = Depends(get_db),
):
    el = db.query(models.CapturedElement).filter(
        models.CapturedElement.id == element_id,
    ).first()
    if not el:
        raise HTTPException(status_code=404, detail="元素不存在")
    db.delete(el)
    db.commit()
    return {"ok": True}
