from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.jwt import require_api_key
from app.models.asset import Asset
from app.models.relationship import AssetRelationship
from app.schemas.relationship import RelationshipCreate, RelationshipOut

router = APIRouter(prefix="/relationships", tags=["relationships"])


@router.post("", response_model=RelationshipOut, status_code=status.HTTP_201_CREATED)
def create_relationship(
    body: RelationshipCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    # Check for both assets
    for aid in (body.from_asset_id, body.to_asset_id):
        if not db.get(Asset, aid):
            raise HTTPException(status_code=404, detail=f"Asset {aid} not found")

    # Prevent exact duplicates
    existing = (
        db.query(AssetRelationship)
        .filter_by(
            from_asset_id=body.from_asset_id,
            to_asset_id=body.to_asset_id,
            relation_type=body.relation_type,
        )
        .first()
    )
    if existing:
        return existing

    rel = AssetRelationship(**body.model_dump())
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


@router.get("", response_model=list[RelationshipOut])
def list_relationships(
    asset_id: str = None,
    db: Session = Depends(get_db),
):
    q = db.query(AssetRelationship)
    if asset_id:
        q = q.filter(
            (AssetRelationship.from_asset_id == asset_id)
            | (AssetRelationship.to_asset_id == asset_id)
        )
    return q.all()


@router.delete("/{rel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relationship(
    rel_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    rel = db.get(AssetRelationship, rel_id)
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")
    db.delete(rel)
    db.commit()