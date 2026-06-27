from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, field_validator
from app.models.asset import AssetType, AssetStatus


class AssetCreate(BaseModel):
    id: Optional[str] = None
    type: AssetType
    value: str
    status: AssetStatus = AssetStatus.active
    source: str
    tags: List[str] = []
    metadata: dict[str, Any] = {}

    @field_validator("value")
    @classmethod
    def value_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("value must not be blank")
        return v.strip()


class AssetUpdate(BaseModel):
    status: Optional[AssetStatus] = None
    tags: Optional[List[str]] = None
    metadata: Optional[dict[str, Any]] = None
    source: Optional[str] = None


class AssetOut(BaseModel):
    id: str
    type: AssetType
    value: str
    status: AssetStatus
    first_seen: datetime
    last_seen: datetime
    source: str
    tags: List[str]
    metadata: dict[str, Any]

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_asset(cls, asset) -> "AssetOut":
        return cls(
            id=asset.id,
            type=asset.type,
            value=asset.value,
            status=asset.status,
            first_seen=asset.first_seen,
            last_seen=asset.last_seen,
            source=asset.source,
            tags=asset.tags or [],
            metadata=asset.metadata_ or {},
        )


class AssetWithRelations(AssetOut):
    related: List["AssetOut"] = []


class PaginatedAssets(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AssetOut]