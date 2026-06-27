
#Lifecycle helpers : mark assets stale when they haven't been seen recently.

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.asset import Asset, AssetStatus


def mark_stale(db: Session, older_than_days: int = 30) -> int:
    #Mark active assets that haven't been seen in older_than_days as stale
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    updated = (
        db.query(Asset)
        .filter(Asset.status == AssetStatus.active, Asset.last_seen < cutoff)
        .update({"status": AssetStatus.stale}, synchronize_session=False)
    )
    db.commit()
    return updated