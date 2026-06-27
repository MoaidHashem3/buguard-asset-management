from pydantic import BaseModel


class RelationshipCreate(BaseModel):
    from_asset_id: str
    to_asset_id: str
    relation_type: str


class RelationshipOut(BaseModel):
    id: str
    from_asset_id: str
    to_asset_id: str
    relation_type: str

    model_config = {"from_attributes": True}