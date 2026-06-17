"""AI insights router — predictive delivery risk + supplier scorecards.

Mounted separately from the chat router so analytics endpoints stay grouped:

  GET  /api/ai/insights/delay-risk              → top at-risk POs
  POST /api/ai/insights/delay-risk/rescore      → recompute risk now (manager)
  GET  /api/ai/insights/suppliers               → supplier scorecards (worst first)
  GET  /api/ai/insights/suppliers/{name}        → one supplier's scorecard
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.deps import require_manager
from ..database import get_db
from ..services import ai_insights_service

router = APIRouter(prefix="/api/ai/insights", tags=["ai-insights"])


@router.get("/delay-risk")
def delay_risk(
    db: Session = Depends(get_db),
    band: str | None = Query(default=None, description="Filter: LOW / MEDIUM / HIGH"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    items = ai_insights_service.list_delay_risk(db, band=band, limit=limit)
    return {
        "count": len(items),
        "band": band,
        "items": items,
    }


@router.post("/delay-risk/rescore")
def rescore_delay_risk(
    db: Session = Depends(get_db),
    _user=Depends(require_manager),
) -> dict:
    return ai_insights_service.rescore_all(db)


@router.get("/suppliers")
def supplier_scorecards(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    items = ai_insights_service.supplier_scorecards(db, limit=limit)
    return {"count": len(items), "items": items}


@router.get("/suppliers/{name}")
def supplier_scorecard(name: str, db: Session = Depends(get_db)) -> dict:
    items = ai_insights_service.supplier_scorecards(db, name=name, limit=1)
    if not items:
        raise HTTPException(404, f"No procurement records for supplier '{name}'")
    return items[0]
