"""
Deduplication logic
an asset is a duplicate if (type, value) already exists
On reimport we update last_seen, merge tags, and merge metadata (incoming wins on conflicts)
A stale asset that reappears is set back to active
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.asset import Asset, AssetStatus


def upsert_asset(db: Session, data: dict) -> tuple[Asset, bool]:
    """
    Returns (asset, created).
    created=True  → new record inserted
    created=False → existing record updated
    """
    existing = (
        db.query(Asset)
        .filter(Asset.type == data["type"], Asset.value == data["value"])
        .first()
    )

    now = datetime.now(timezone.utc)

    if existing:
        # Merge tags (no duplicates)
        existing_tags = set(existing.tags or [])
        incoming_tags = set(data.get("tags") or [])
        existing.tags = list(existing_tags | incoming_tags)

        # Merge metadata (incoming wins on key conflicts)
        merged_meta = {**(existing.metadata_ or {}), **(data.get("metadata") or {})}
        existing.metadata_ = merged_meta

        # Update last_seen
        existing.last_seen = now

        # Reactivate stale asset
        if existing.status == AssetStatus.stale:
            existing.status = AssetStatus.active

        db.flush()
        return existing, False

    asset = Asset(
        id=data.get("id") or None,
        type=data["type"],
        value=data["value"],
        status=data.get("status", AssetStatus.active),
        source=data.get("source", "import"),
        tags=data.get("tags") or [],
        metadata_=data.get("metadata") or {},
        first_seen=now,
        last_seen=now,
    )
    db.add(asset)
    db.flush()
    return asset, True