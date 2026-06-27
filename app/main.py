from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.database import Base, engine
from app.routes import assets, relationships
from app.routes import bulk_import as import_route

from dotenv import load_dotenv
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="DarkAtlas Asset Management API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(assets.router)
app.include_router(relationships.router)
app.include_router(import_route.router)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "error": str(exc)})


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}