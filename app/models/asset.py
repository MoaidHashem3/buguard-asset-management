from sqlalchemy import Column
from sqlalchemy import String

from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True)

    type = Column(String)

    value = Column(String)

    status = Column(String)