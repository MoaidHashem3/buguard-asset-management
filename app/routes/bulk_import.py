
#Bulk import endpoint

from typing import Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.jwt import require_api_key
from app.models.relationship import AssetRelationship
from app.services.deduplication import upsert_asset

router = APIRouter(prefix="/import", tags=["import"])

# Inline-relationship keys present in the sample dataset
_RELATION_KEYS = {
    "parent": "subdomain_of",
    "covers": "covers",
    "resolves_to": "resolves_to",
}


@router.post("", status_code=status.HTTP_200_OK)
def bulk_import(
    records: list[dict[str, Any]],
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    created = updated = skipped = 0
    errors: list[dict] = []

    # First pass: upsert all assets, build id→asset map
    id_map: dict[str, str] = {}  # original_id → db_id

    for raw in records:
        try:
            _validate(raw)
            asset, is_new = upsert_asset(db, raw)
            original_id = raw.get("id")
            if original_id:
                id_map[original_id] = asset.id
            if is_new:
                created += 1
            else:
                updated += 1
        except Exception as exc:
            skipped += 1
            errors.append({"record": raw.get("id") or raw.get("value"), "error": str(exc)})

    db.flush()

    # Second pass: create relationships from inline keys
    for raw in records:
        asset_db_id = id_map.get(raw.get("id", ""))
        if not asset_db_id:
            continue
        for key, rel_type in _RELATION_KEYS.items():
            ref_original_id = raw.get(key)
            if not ref_original_id:
                continue
            ref_db_id = id_map.get(ref_original_id)
            if not ref_db_id:
                continue
            # Avoid duplicate relationships
            exists = (
                db.query(AssetRelationship)
                .filter_by(from_asset_id=asset_db_id, to_asset_id=ref_db_id, relation_type=rel_type)
                .first()
            )
            if not exists:
                db.add(AssetRelationship(
                    from_asset_id=asset_db_id,
                    to_asset_id=ref_db_id,
                    relation_type=rel_type,
                ))

    db.commit()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


def _validate(raw: dict) -> None:
    if not raw.get("type"):
        raise ValueError("missing field: type")
    if not raw.get("value", "").strip():
        raise ValueError("missing field: value")
    if not raw.get("source"):
        raise ValueError("missing field: source")