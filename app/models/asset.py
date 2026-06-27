import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Enum as SAEnum, ARRAY
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class AssetType(str, enum.Enum):
    domain = "domain"
    subdomain = "subdomain"
    ip_address = "ip_address"
    service = "service"
    certificate = "certificate"
    technology = "technology"


class AssetStatus(str, enum.Enum):
    active = "active"
    stale = "stale"
    archived = "archived"


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(SAEnum(AssetType), nullable=False)
    value = Column(String, nullable=False)
    status = Column(SAEnum(AssetStatus), default=AssetStatus.active, nullable=False)
    first_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source = Column(String, nullable=False)
    tags = Column(ARRAY(String), default=[])
    metadata_ = Column("metadata", JSON, default={})

    relationships_from = relationship(
        "AssetRelationship",
        foreign_keys="AssetRelationship.from_asset_id",
        back_populates="from_asset",
        cascade="all, delete-orphan",
    )
    relationships_to = relationship(
        "AssetRelationship",
        foreign_keys="AssetRelationship.to_asset_id",
        back_populates="to_asset",
        cascade="all, delete-orphan",
    )