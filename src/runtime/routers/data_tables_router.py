"""
Data Table API: 流程级数据表格
"""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .. import schemas
from src.repo import runtime_models as models
from src.repo.models import SessionLocal
import json

router = APIRouter(prefix="/api/workflows", tags=["Data Tables"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _deserialize_table(table):
    try:
        table.columns = json.loads(table.columns) if table.columns else []
    except Exception:
        table.columns = []
    try:
        table.rows = json.loads(table.rows) if table.rows else []
    except Exception:
        table.rows = []
    return table


@router.get("/{wf_id}/data-table", response_model=schemas.DataTableOut)
def get_or_create_table(wf_id: int, db: Session = Depends(get_db)):
    """每个流程只有一个数据表格；不存在则自动创建。"""
    table = db.query(models.DataTable).filter(models.DataTable.workflow_id == wf_id).first()
    if not table:
        table = models.DataTable(
            workflow_id=wf_id,
            name="default",
            columns=json.dumps([{"name": name, "type": "text"} for name in ["A", "B", "C", "D", "E"]]),
            rows=json.dumps([{} for _ in range(30)]),
        )
        db.add(table)
        db.commit()
        db.refresh(table)
    _deserialize_table(table)
    return table


@router.put("/{wf_id}/data-table", response_model=schemas.DataTableOut)
def update_table(wf_id: int, payload: schemas.DataTableIn, db: Session = Depends(get_db)):
    table = db.query(models.DataTable).filter(models.DataTable.workflow_id == wf_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="表格不存在")
    table.name = payload.name
    table.columns = json.dumps(payload.columns)
    table.rows = json.dumps(payload.rows)
    db.commit()
    db.refresh(table)
    _deserialize_table(table)
    return table


@router.post("/{wf_id}/data-table/import", response_model=schemas.DataTableOut)
def import_table(wf_id: int, payload: dict, db: Session = Depends(get_db)):
    """Import CSV content: first row = column names, subsequent rows = data."""
    table = db.query(models.DataTable).filter(models.DataTable.workflow_id == wf_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="表格不存在")
    csv_text = payload.get("csv", "")
    if not csv_text.strip():
        raise HTTPException(status_code=400, detail="CSV 内容为空")
    try:
        reader = csv.reader(io.StringIO(csv_text.strip()))
        rows = list(reader)
        if not rows:
            raise HTTPException(status_code=400, detail="CSV 解析失败")
        headers = rows[0]
        columns = [{"name": h.strip(), "type": "text"} for h in headers]
        data_rows = []
        for row in rows[1:]:
            data_rows.append({h: v for h, v in zip(headers, row)})
        table.columns = json.dumps(columns)
        table.rows = json.dumps(data_rows)
        db.commit()
        db.refresh(table)
        _deserialize_table(table)
        return table
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"导入失败: {e}")


@router.get("/{wf_id}/data-table/export")
def export_table(wf_id: int, db: Session = Depends(get_db)):
    """Export table as CSV."""
    table = db.query(models.DataTable).filter(models.DataTable.workflow_id == wf_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="表格不存在")
    _deserialize_table(table)
    columns = table.columns or []
    rows = table.rows or []
    headers = [c["name"] for c in columns]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(h, "") for h in headers])
    return PlainTextResponse(content=output.getvalue(), media_type="text/csv; charset=utf-8")


@router.post("/{wf_id}/data-table/clear", response_model=schemas.DataTableOut)
def clear_table(wf_id: int, db: Session = Depends(get_db)):
    """Clear all rows, preserve columns."""
    table = db.query(models.DataTable).filter(models.DataTable.workflow_id == wf_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="表格不存在")
    table.rows = json.dumps([])
    db.commit()
    db.refresh(table)
    _deserialize_table(table)
    return table


@router.get("/{wf_id}/data-table/last-run")
def get_last_run_table(wf_id: int):
    """Return the latest runtime table result for this workflow."""
    from src.runtime.workflow.extension_runner import _last_run_tables
    data = _last_run_tables.get(wf_id, {"columns": [], "rows": [], "runId": None, "success": False})
    return data
