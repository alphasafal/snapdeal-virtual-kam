"""Shared test setup: each test that asks for `fresh_db` gets its own empty database
loaded with the three mock sellers."""
import pytest

@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    from brain import db, seed
    db.reset_engine()
    seed.seed()
    yield
    db.reset_engine()
