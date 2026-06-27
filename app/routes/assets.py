from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, text
from app.database import get_db
from app.auth.jwt import require_api_key
from app.models.asset import Asset, AssetStatus, AssetType
from app.schemas.asset import AssetCreate, AssetUpdate, AssetOut, AssetWithRelations, PaginatedAssets
from app.services.deduplication import upsert_asset
from app.services.lifecycle import mark_stale

router = APIRouter(prefix="/assets", tags=["assets"])


# List / search

@router.get("", response_model=PaginatedAssets)
def list_assets(
    type: Optional[AssetType] = None,
    status: Optional[AssetStatus] = None,
    tag: Optional[str] = None,
    value_contains: Optional[str] = None,
    sort_by: str = Query("last_seen", pattern="^(last_seen|first_seen|value|type|status|id)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Asset)

    if type:
        q = q.filter(Asset.type == type)
    if status:
        q = q.filter(Asset.status == status)
    if tag:
        q = q.filter(text(":tag = ANY(assets.tags)").bindparams(tag=tag))
    if value_contains:
        q = q.filter(Asset.value.ilike(f"%{value_contains}%"))

    sort_col = getattr(Asset, sort_by)
    q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedAssets(
        total=total,
        page=page,
        page_size=page_size,
        items=[AssetOut.from_orm_asset(a) for a in items],
    )


# Single asset CRUD 

@router.post("", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
def create_asset(
    body: AssetCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    asset, _ = upsert_asset(db, body.model_dump())
    db.commit()
    db.refresh(asset)
    return AssetOut.from_orm_asset(asset)


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return AssetOut.from_orm_asset(asset)


@router.patch("/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: str,
    body: AssetUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if body.status is not None:
        asset.status = body.status
    if body.tags is not None:
        asset.tags = body.tags
    if body.metadata is not None:
        asset.metadata_ = {**(asset.metadata_ or {}), **body.metadata}
    if body.source is not None:
        asset.source = body.source

    asset.last_seen = datetime.now(timezone.utc)
    db.commit()
    db.refresh(asset)
    return AssetOut.from_orm_asset(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    db.delete(asset)
    db.commit()


# Asset with its relationship graph

@router.get("/{asset_id}/graph", response_model=AssetWithRelations)
def get_asset_graph(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    related_ids = (
        {r.to_asset_id for r in asset.relationships_from}
        | {r.from_asset_id for r in asset.relationships_to}
    )
    related_assets = db.query(Asset).filter(Asset.id.in_(related_ids)).all()

    result = AssetWithRelations(
        **AssetOut.from_orm_asset(asset).model_dump(),
        related=[AssetOut.from_orm_asset(a) for a in related_assets],
    )
    return result


#Lifecycle util

@router.post("/actions/mark-stale", tags=["lifecycle"])
def action_mark_stale(
    older_than_days: int = Query(30, ge=1),
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    count = mark_stale(db, older_than_days)
    return {"marked_stale": count}