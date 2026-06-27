"""
Tests for: deduplication, lifecycle, filtering, relationships.
Uses an in-memory SQLite DB so no Postgres is needed to run tests.
"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

# Use the real Postgres from docker-compose
TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/darkatlas"
)

engine = create_engine(TEST_DB_URL)
TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

API_KEY = "testkey"


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setenv("API_KEY", API_KEY)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    # Clean up all tables between tests so they don't interfere
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()

@pytest.fixture
def client():
    return TestClient(app)


AUTH = {"Authorization": f"Bearer {API_KEY}"}

SAMPLE = [
    {"id": "a1", "type": "domain", "value": "example.com", "status": "active", "source": "scan", "tags": ["root"], "metadata": {}},
    {"id": "a2", "type": "subdomain", "value": "api.example.com", "status": "active", "source": "scan", "tags": ["prod"], "metadata": {}, "parent": "a1"},
    {"id": "a3", "type": "certificate", "value": "CN=api.example.com", "status": "active", "source": "scan", "tags": [], "metadata": {"issuer": "Let's Encrypt", "expires": "2025-01-02"}, "covers": "a2"},
]


# ── Deduplication ─────────────────────────────────────────────────────────────

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
    extra = [{"id": "a1", "type": "domain", "value": "example.com", "source": "manual", "tags": ["extra"], "metadata": {}}]
    client.post("/import", json=extra, headers=AUTH)

    r = client.get("/assets?value_contains=example.com&type=domain")
    items = r.json()["items"]
    assert "root" in items[0]["tags"]
    assert "extra" in items[0]["tags"]


# ── Filtering & pagination ────────────────────────────────────────────────────

def test_filter_by_type(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    r = client.get("/assets?type=certificate")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(i["type"] == "certificate" for i in items)


def test_filter_by_tag(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    r = client.get("/assets?tag=prod")
    items = r.json()["items"]
    assert all("prod" in i["tags"] for i in items)


def test_pagination(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    r = client.get("/assets?page=1&page_size=2")
    data = r.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def test_mark_stale_via_patch(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    assets = client.get("/assets").json()["items"]
    aid = assets[0]["id"]

    r = client.patch(f"/assets/{aid}", json={"status": "stale"}, headers=AUTH)
    assert r.json()["status"] == "stale"


def test_stale_asset_reactivated_on_reimport(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    assets = client.get("/assets?type=domain").json()["items"]
    aid = assets[0]["id"]
    client.patch(f"/assets/{aid}", json={"status": "stale"}, headers=AUTH)

    client.post("/import", json=SAMPLE, headers=AUTH)
    r = client.get(f"/assets/{aid}")
    assert r.json()["status"] == "active"


# ── Relationships ─────────────────────────────────────────────────────────────

def test_relationships_created_on_import(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    r = client.get("/relationships")
    assert r.status_code == 200
    assert len(r.json()) >= 2  # subdomain_of + covers


def test_asset_graph(client):
    client.post("/import", json=SAMPLE, headers=AUTH)
    domain = client.get("/assets?type=domain").json()["items"][0]
    r = client.get(f"/assets/{domain['id']}/graph")
    assert r.status_code == 200
    assert len(r.json()["related"]) >= 1


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_write_requires_auth(client):
    r = client.post("/assets", json={"type": "domain", "value": "x.com", "source": "manual"})
    assert r.status_code == 401


# ── Error handling ────────────────────────────────────────────────────────────

def test_import_skips_bad_records(client):
    bad_batch = [
        {"type": "domain", "value": "good.com", "source": "scan"},
        {"value": "no-type.com", "source": "scan"},          # missing type
        {"type": "subdomain", "source": "scan"},              # missing value
    ]
    r = client.post("/import", json=bad_batch, headers=AUTH)
    data = r.json()
    assert data["created"] == 1
    assert data["skipped"] == 2