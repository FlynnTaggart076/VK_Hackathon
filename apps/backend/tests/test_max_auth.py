"""Synthetic MAX vectors; no live bot token or MAX account is used."""

import hashlib
import hmac
import json
import time
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.db.models import Base
from app.errors import ApiError
from app.main import Settings, create_app
from app.services.max_auth import validate_init_data


FIXED = ("query_id=q-1&user=%7B%22id%22%3A123%7D&auth_date=1700000000"
         "&hash=ce697037a833dc45c4c7d541c46bd34a03db60e5286c0555b9c34c5303c487ca")


def signed_data(timestamp: int, user_id: int = 123) -> str:
    user = json.dumps({"id": user_id}, separators=(",", ":"))
    params = f"auth_date={timestamp}\nquery_id=q-1\nuser={user}"
    key = hmac.new(b"WebAppData", b"fixture-token", hashlib.sha256).digest()
    signature = hmac.new(key, params.encode(), hashlib.sha256).hexdigest()
    return f"query_id=q-1&user={quote(user, safe='')}&auth_date={timestamp}&hash={signature}"


def test_official_algorithm_fixed_vector_and_invalid_cases():
    assert validate_init_data(FIXED, "fixture-token", current_time=1700000000) == 123
    for raw in (FIXED.replace("123", "124"), FIXED + "&user=x", FIXED + "&hash=x",
                FIXED.replace("query_id=q-1", "query_id=q%ZZ"), FIXED.replace("&hash=", "&hash=x")):
        with pytest.raises(ApiError) as error:
            validate_init_data(raw, "fixture-token", current_time=1700000000)
        assert error.value.code == "INVALID_MAX_AUTH"
    for age in (-301, 31):
        with pytest.raises(ApiError):
            validate_init_data(FIXED, "fixture-token", current_time=1700000000 - age)


def test_max_exchange_repeat_and_logout_in_persistent_store(tmp_path):
    url = f"sqlite:///{(tmp_path / 'max.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    app = create_app(Settings(database_url=url, storage_path=tmp_path / "private",
                              max_bot_token="fixture-token"))
    raw = signed_data(int(time.time()))
    with TestClient(app) as client:
        first = client.post("/api/v1/auth/max", json={"init_data": raw})
        second = client.post("/api/v1/auth/max", json={"init_data": raw})
        assert first.status_code == second.status_code == 200
        assert first.json()["user"] == second.json()["user"]
        assert first.json()["access_token"] != second.json()["access_token"]
        bearer = {"Authorization": "Bearer " + first.json()["access_token"]}
        assert client.get("/api/v1/me", headers=bearer).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=bearer).status_code == 204
        assert client.get("/api/v1/me", headers=bearer).status_code == 401
