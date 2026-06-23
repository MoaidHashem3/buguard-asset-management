from fastapi import FastAPI

from app.database import Base
from app.database import engine

from app.models.asset import Asset

Base.metadata.create_all(bind=engine)

app = FastAPI()


@app.get("/")
def root():
    return {"message": "API Running"}