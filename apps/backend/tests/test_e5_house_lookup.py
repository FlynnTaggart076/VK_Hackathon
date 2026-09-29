"""House lookup port: synthetic HouseScore/Dominfo payloads through httpx.MockTransport, no network."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import create_engine

from app.db.models import Base
from app.main import Settings
from app.db.store import SqlStore
from app.services.house_lookup import (
    HouseLookup, LookupUnavailable, _cache_name, build_service_card, choose_house, clean_address,
    db_quota, query_house_number, render_card_text,
)

GUID_1 = "11111111-1111-4111-8111-111111111111"
GUID_2 = "22222222-2222-4222-8222-222222222222"
SEARCH = {"data": [
    {"address": "123456, г Москва, ул Примерная, д. 12, к. 1", "fias_id": GUID_1},
    {"address": "123456, г Москва, ул Примерная, д. 12, к. 2", "fias_id": GUID_2},
]}
HOUSE = {"fias_guid": GUID_2, "address": "123456, г Москва, ул Примерная, д. 12, к. 2", "building_year": 2001}
MANAGEMENT = {"management_type": "УО", "management_company": {"inn": "7700000001", "ogrn": 1027700000001,
                                                              "name": "ООО Учебная УК"}}
COMPANY = {"ogrn": 1027700000001, "name": "ООО «Учебная управляющая компания»", "phone": "8 (495) 000-00-00",
           "email": "uk@example.org"}
DOMINFO_SEARCH = {"response": {"data": {"results": [
    {"house": {"address": "г Москва, ул Примерная, д. 12, к. 2", "link": "primernaya-12-2"},
     "name_short": "ООО Учебная УК", "ogrn": 1027700000001}]}}}
DOMINFO_CARD = {"response": {"data": {"house": {
    "passport": {"fias": {"formalname_city": "Москва", "formalname_street": "Примерная", "house_number": "12",
                          "block": "2"}, "engineering": {"gas_type": "Отсутствует"}},
    "management": {"utilities": [
        {"service": {"name": "Электроснабжение"}, "company": {"name": "АО «Учебная энергосбытовая»", "inn": "7700000002"},
         "date_start": {"seconds": 1600000000}},
        {"service": {"name": "Отопление"}, "company": {"name": "ПАО «Учебная теплосеть»", "inn": "7700000003"}},
    ]}}}}}
CONTACTS = {"7700000002": {"website": "https://energy.example.org/", "website_source_url": "https://energy.example.org/about"},
            "7700000003": {"website": "https://unverified.example.org/"}}


def transport(calls: list, *, fail: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if fail:
            raise httpx.ConnectError("offline", request=request)
        path = request.url.path
        if request.url.host == "housescore.ru":
            assert request.headers["Authorization"] == "Bearer fixture-key"
            payload = {"/api/houses/find-by-address": SEARCH, f"/api/houses/{GUID_2}": HOUSE,
                       f"/api/houses/{GUID_2}/management": MANAGEMENT,
                       "/api/companies/1027700000001": COMPANY}[path]
        else:
            payload = DOMINFO_SEARCH if path.endswith("search/general") else DOMINFO_CARD
        return httpx.Response(200, json=payload)
    return httpx.MockTransport(handler)


def test_address_cleaning_and_house_numbers():
    assert clean_address("Москва, ул. Примерная, д. 12, кв. 45, тел. +7 999 111-22-33") == "Москва, ул. Примерная, д. 12"
    assert "лицев" not in clean_address("ул. Примерная 5, лицевой счёт 123456789").lower()
    assert query_house_number("Люберцы, проспект Примерный 24 к2") == "24"
    assert query_house_number("Москва, 3-я улица Строителей, 25") == "25"
    assert query_house_number("Химки ул Примерная 5/2 кв 7") == "5/2"
    assert query_house_number("Москва, улица Примерная") is None


def test_corpus_choice_matches_prototype_rules():
    candidates = [{"fias_guid": GUID_1, "address": "г Москва, ул Примерная, д. 12, к. 1"},
                  {"fias_guid": GUID_2, "address": "г Москва, ул Примерная, д. 12, к. 2"}]
    assert choose_house("Москва, Примерная улица, дом 12, корпус 2", candidates)["house"]["fias_guid"] == GUID_2
    assert choose_house("Москва, Примерная улица, дом 12", candidates)["status"] == "confirm"
    assert choose_house("Москва, Примерная улица, дом 12, корпус 3", candidates)["status"] == "not_found"


def test_lookup_uses_cache_after_first_live_call(tmp_path):
    calls = []
    lookup = HouseLookup(api_key="fixture-key", cache_dir=tmp_path, transport=transport(calls))
    candidates = lookup.find_houses("Москва, Примерная улица, дом 12, корпус 2")
    assert [item["fias_guid"] for item in candidates] == [GUID_1, GUID_2]
    details = lookup.house_details(candidates[1])
    assert details["company"]["name"].startswith("ООО «Учебная")
    services = {item["service_code"]: item for item in details["services"]}
    assert services["electricity"]["status"] == "candidate"
    assert services["gas"]["status"] == "not_available"
    assert services["cold_water"]["status"] == "unknown"
    first = len(calls)
    assert first == 6  # search, house, management, company + 2 Dominfo
    cached = HouseLookup(api_key=None, cache_dir=tmp_path, transport=transport(calls, fail=True))
    assert cached.find_houses("Москва, Примерная улица, дом 12, корпус 2") == candidates
    assert cached.house_details(candidates[1])["services"] == details["services"]
    assert len(calls) == first
    assert "fixture-key" not in "".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.json"))


def test_no_key_and_network_errors_are_explicit(tmp_path):
    with pytest.raises(LookupUnavailable) as error:
        HouseLookup(api_key=None, cache_dir=tmp_path).find_houses("Москва, Примерная, 1")
    assert error.value.code == "no_key"
    with pytest.raises(LookupUnavailable) as error:
        HouseLookup(api_key="fixture-key", cache_dir=tmp_path,
                    transport=transport([], fail=True)).find_houses("Москва, Примерная, 1")
    assert error.value.code == "network"


def test_stale_cache_is_used_when_the_service_fails(tmp_path):
    url = "https://housescore.ru/api/houses/find-by-address?q=%D0%9C"
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    (tmp_path / _cache_name(url)).write_text(json.dumps({"url": url, "fetched_at": old, "data": SEARCH}),
                                             encoding="utf-8")
    lookup = HouseLookup(api_key="fixture-key", cache_dir=tmp_path, transport=transport([], fail=True))
    assert len(lookup.find_houses("М")) == 2


def test_redirect_to_other_host_is_rejected(tmp_path):
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://evil.example/"})
    lookup = HouseLookup(api_key="fixture-key", cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    with pytest.raises(LookupUnavailable) as error:
        lookup.find_houses("Москва, Примерная, 1")
    assert error.value.code == "service"


def test_service_card_matches_website_by_inn_with_evidence(tmp_path):
    lookup = HouseLookup(api_key="fixture-key", cache_dir=tmp_path, transport=transport([]))
    details = lookup.house_details({"fias_guid": GUID_2, "address": HOUSE["address"]})
    electricity = build_service_card(details, "electricity", CONTACTS)
    assert electricity["provider"]["website"] == "https://energy.example.org/"
    assert electricity["management"]["phone"] == "+7 (495) 000-00-00"
    heating = build_service_card(details, "heating", CONTACTS)
    assert heating["provider"]["website"] is None  # No evidence URL for this website.
    unknown = build_service_card(details, "cold_water", CONTACTS)
    assert unknown["provider"] is None and "не найден" in render_card_text(unknown)
    management = build_service_card(details, "management", CONTACTS)
    assert management["provider"] is None and "Учебная управляющая" in render_card_text(management)
    assert all(link["url"].startswith("https://") for link in electricity["links"])


def test_daily_quota_is_shared_and_per_user(tmp_path):
    url = f"sqlite:///{(tmp_path / 'quota.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url))
    settings = Settings(database_url=url, storage_path=tmp_path, housescore_daily_limit=3,
                        house_lookup_user_daily_limit=2)
    consume = db_quota(SqlStore(settings), settings)
    user = str(uuid.uuid4())
    consume("housescore", user)
    consume("housescore", user)
    with pytest.raises(LookupUnavailable) as error:
        consume("housescore", user)
    assert error.value.code == "user_quota"
    consume("housescore", None)
    with pytest.raises(LookupUnavailable) as error:
        consume("housescore", str(uuid.uuid4()))
    assert error.value.code == "quota"

