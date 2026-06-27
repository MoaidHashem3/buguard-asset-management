import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

API_KEY = "testkey"

DB_URL = "postgresql://postgres:postgres@db:5432/darkatlas"


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(DB_URL)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_tables(db_engine):
    """Wipe all rows before each test, keep the schema."""
    yield
    with db_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def client(db_engine, monkeypatch):
    monkeypatch.setenv("API_KEY", API_KEY)
    TestingSession = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


AUTH = {"Authorization": f"Bearer {API_KEY}"}

SAMPLE = [
    {"id": "a1", "type": "domain", "value": "example.com", "status": "active", "source": "scan", "tags": ["root"], "metadata": {}},
    {"id": "a2", "type": "subdomain", "value": "api.example.com", "status": "active", "source": "scan", "tags": ["prod"], "metadata": {}, "parent": "a1"},
    {"id": "a3", "type": "certificate", "value": "CN=api.example.com", "status": "active", "source": "scan", "tags": [], "metadata": {"issuer": "Let's Encrypt", "expires": "2025-01-02"}, "covers": "a2"},
]


# Deduplication 

def test_import_idempotent(client):
    r1 = client.post("/import", json=SAMPLE, headers=AUTH)
    assert r1.status_code == 200
    assert r1.json()["created"] == 3

    r2 = client.post("/import", json=SAMPLE, headers=AUTH)
    assert r2.status_code == 200
    assert r2.json()["created"] == 0
    assert r2.json()["updated"] == 3


def test_dedup_merges_tags(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    extra = [{"type": "domain", "value": "example.com", "source": "manual", "tags": ["extra"], "metadata": {}}]
    client.post("/import", json=extra, headers=AUTH)

    r = client.get("/assets?value_contains=example.com&type=domain")
    tags = r.json()["items"][0]["tags"]
    assert "root" in tags
    assert "extra" in tags


# Filtering & pagination

def test_filter_by_type(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    r = client.get("/assets?type=certificate")
    assert r.status_code == 200
    assert all(i["type"] == "certificate" for i in r.json()["items"])


def test_filter_by_tag(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    r = client.get("/assets?tag=prod")
    assert all("prod" in i["tags"] for i in r.json()["items"])


def test_pagination(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    r = client.get("/assets?page=1&page_size=2")
    data = r.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2


#Lifecycle

def test_mark_stale_via_patch(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    aid = client.get("/assets").json()["items"][0]["id"]
    r = client.patch(f"/assets/{aid}", json={"status": "stale"}, headers=AUTH)
    assert r.json()["status"] == "stale"


def test_stale_asset_reactivated_on_reimport(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    aid = client.get("/assets?type=domain").json()["items"][0]["id"]
    client.patch(f"/assets/{aid}", json={"status": "stale"}, headers=AUTH)

    client.post("/import", json=SAMPLE, headers=AUTH)
    assert client.get(f"/assets/{aid}").json()["status"] == "active"


# Relationships

def test_relationships_created_on_import(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    r = client.get("/relationships")
    assert r.status_code == 200
    assert len(r.json()) >= 2


def test_asset_graph(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    domain = client.get("/assets?type=domain").json()["items"][0]
    r = client.get(f"/assets/{domain['id']}/graph")
    assert r.status_code == 200
    assert len(r.json()["related"]) >= 1


# Auth
def test_write_requires_auth(client):
    r = client.post("/assets", json={"type": "domain", "value": "x.com", "source": "manual"})
    assert r.status_code == 401


# Error handling
def test_import_skips_bad_records(client):
    bad_batch = [
        {"type": "domain", "value": "good.com", "source": "scan"},
        {"value": "no-type.com", "source": "scan"},
        {"type": "subdomain", "source": "scan"},
    ]
    r = client.post("/import", json=bad_batch, headers=AUTH)
    data = r.json()
    assert data["created"] == 1
    assert data["skipped"] == 2