import uuid
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class AssetRelationship(Base):
    __tablename__ = "asset_relationships"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    from_asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    to_asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String, nullable=False)  # e.g. "subdomain_of", "resolves_to", "covers"

    from_asset = relationship("Asset", foreign_keys=[from_asset_id], back_populates="relationships_from")
    to_asset = relationship("Asset", foreign_keys=[to_asset_id], back_populates="relationships_to")