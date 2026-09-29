"""Address -> house -> management company and utility providers (HouseScore + Dominfo).

Ported from the console prototype colleague_anton/research/house_lookup.py. Cache files keep the
prototype's names and record format, so its saved responses can be copied into
HOUSE_LOOKUP_CACHE_DIR without spending the HouseScore quota. Addresses, query URLs and the API key
are never logged. Dominfo supplier records are historical candidates, not verified contracts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

import httpx

log = logging.getLogger("app.house_lookup")

HOUSESCORE_URL = "https://housescore.ru"
DOMINFO_URL = "https://dominfo.ru"
MAX_BODY = 5_000_000
SERVICE_NAMES = {
    "heating": "Отопление",
    "hot_water": "Горячая вода",
    "cold_water": "Холодная вода",
    "sewerage": "Водоотведение",
    "electricity": "Электричество",
    "gas": "Газ",
    "waste": "Вывоз ТКО",
}
# House lookup codes -> housing_engine ServiceCode (gas has no engine code).
ENGINE_SERVICE = {"heating": "heating", "hot_water": "hot_water", "cold_water": "cold_water",
                  "sewerage": "drainage", "electricity": "electricity", "gas": None, "waste": "waste"}
_GUID = re.compile(r"[0-9a-fA-F-]{36}")
CONTACTS_FILE = next((parent / "knowledge" / "house_lookup" / "organization_contacts.json"
                      for parent in Path(__file__).resolve().parents
                      if (parent / "knowledge" / "manifest.yaml").is_file()), None)


class LookupUnavailable(Exception):
    """Expected, user-explainable failure: no_key, quota, user_quota, network, service, timeout."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def clean_address(text: str) -> str:
    """Keep only the house address: drop apartment, account, phone and e-mail fragments."""
    value = " ".join(text.replace("ё", "е").replace("Ё", "Е").split())
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " ", value)
    value = re.sub(r"(?i)[,;]?\s*(?:кв(?:артира)?|пом(?:ещение)?|офис|комн(?:ата)?)\.?\s*№?\s*\d+[а-яa-z]?\b", " ", value)
    value = re.sub(r"(?i)(?:лицевой\s+сч[её]т|л/с|лс)\s*[:№-]?\s*[\d\s-]+", " ", value)
    value = re.sub(r"(?i)(?:тел(?:ефон)?\.?\s*:?\s*)?\+?\d[\d\s()-]{8,}\d", " ", value)
    value = re.sub(r"\s+([,.;])", r"\1", " ".join(value.split()))
    return value.strip(" ,.;")[:200]


def _house_number(value: str) -> str | None:
    match = re.search(r"\b(?:дом|д\.?)\s*(\d+(?:/\d+)?[а-яa-z]?)", value.lower())
    return match.group(1) if match else None


def _corpus_number(value: str) -> str | None:
    match = re.search(r"\b(?:корпус|корп\.?|к\.?)\s*(\d+[а-яa-z]?)", value.lower())
    return match.group(1) if match else None


def query_house_number(value: str) -> str | None:
    """House number from free text; also accepts «Гагарина 24» without the word «дом»."""
    value = clean_address(value)
    explicit = _house_number(value)
    if explicit:
        return explicit
    lowered = value.lower()
    lowered = re.sub(r"\b(?:корпус|корп\.?|к\.?|строение|стр\.?|с\.)\s*\d+[а-яa-z]?", " ", lowered)
    lowered = re.sub(r"\b\d{6}\b", " ", lowered)  # postal code
    numbers = re.findall(r"(?<![\w-])(\d{1,4}(?:/\d{1,4})?[а-яa-z]?)(?![\w-])", lowered)
    return numbers[-1] if numbers else None


def choose_house(query: str, candidates: list[dict]) -> dict:
    """Decide whether the search result is the exact house or needs the user's confirmation.

    Returns {"status": "exact"|"confirm"|"not_found", "house": candidate|None, "options": [...]}.
    """
    requested_house = query_house_number(query)
    requested_corpus = _corpus_number(query)
    if requested_house:
        matching = [item for item in candidates if _house_number(item["address"]) == requested_house]
        if requested_corpus:
            matching = [item for item in matching if _corpus_number(item["address"]) == requested_corpus]
        if not matching:
            return {"status": "not_found", "house": None, "options": candidates[:8]}
        if len(matching) == 1 and (requested_corpus or not _corpus_number(matching[0]["address"])):
            return {"status": "exact", "house": matching[0], "options": []}
        return {"status": "confirm", "house": None, "options": matching[:8]}
    return {"status": "confirm", "house": None, "options": candidates[:8]}


def _cache_name(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json"


class _FileCache:
    def __init__(self, root: Path):
        self.root = root

    def read(self, name: str) -> dict | None:
        path = self.root / name
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return record if isinstance(record, dict) and "data" in record and "fetched_at" in record else None

    def write(self, name: str, record: dict) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            temporary = self.root / f".{name}.{uuid.uuid4().hex}.tmp"
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.root / name)
        except OSError:
            log.warning("house cache write failed")


def _fresh(record: dict, max_age_days: int) -> bool:
    try:
        return utc_now() - _parse_time(record["fetched_at"]) <= timedelta(days=max_age_days)
    except (TypeError, ValueError):
        return False


@lru_cache(maxsize=1)
def organization_contacts() -> dict:
    if CONTACTS_FILE is None or not CONTACTS_FILE.is_file():
        return {}
    return json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))


class HouseLookup:
    """HouseScore + Dominfo client with a shared file cache and a per-call time budget."""

    def __init__(self, *, api_key: str | None, cache_dir: Path,
                 quota: Callable[[str, str | None], None] | None = None,
                 transport: httpx.BaseTransport | None = None, budget_seconds: float = 15.0):
        self.api_key = api_key
        self.cache = _FileCache(cache_dir)
        self.quota = quota
        self.transport = transport
        self.budget_seconds = budget_seconds
        self.live_requests = {"housescore": 0, "dominfo": 0}
        self._deadline = time.monotonic() + budget_seconds

    def _start_budget(self) -> None:
        self._deadline = time.monotonic() + self.budget_seconds

    def _remaining(self) -> float:
        return self._deadline - time.monotonic()

    def _send(self, method: str, url: str, host: str, *, headers: dict, body: bytes | None = None) -> dict:
        remaining = self._remaining()
        if remaining < 1.5:
            raise LookupUnavailable("timeout")
        timeout = httpx.Timeout(min(6.0, remaining), connect=min(3.0, remaining))
        try:
            with httpx.Client(transport=self.transport, timeout=timeout, follow_redirects=False) as client:
                request = client.build_request(method, url, headers=headers, content=body)
                response = client.send(request, stream=True)
                try:
                    if urlparse(str(response.url)).hostname != host:
                        raise LookupUnavailable("service")
                    if response.status_code != 200:
                        raise LookupUnavailable("service")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_BODY:
                            raise LookupUnavailable("service")
                        chunks.append(chunk)
                finally:
                    response.close()
            return json.loads(b"".join(chunks))
        except LookupUnavailable:
            raise
        except httpx.TimeoutException:
            raise LookupUnavailable("timeout") from None
        except (httpx.HTTPError, ValueError, OSError):
            raise LookupUnavailable("network") from None

    def _housescore(self, path: str, params: dict | None = None, *, max_age_days: int = 7,
                    user_scope: str | None = None) -> dict:
        if not path.startswith("/api/"):
            raise LookupUnavailable("service")
        url = HOUSESCORE_URL + path + ("?" + urlencode(params) if params else "")
        name = _cache_name(url)
        cached = self.cache.read(name)
        if cached is not None and _fresh(cached, max_age_days):
            return cached
        try:
            if not self.api_key:
                raise LookupUnavailable("no_key")
            if self.quota is not None:
                self.quota("housescore", user_scope)
            self.live_requests["housescore"] += 1
            data = self._send("GET", url, "housescore.ru", headers={
                "Authorization": f"Bearer {self.api_key}", "Accept": "application/json",
                "User-Agent": "ZhkhMaxAssistant/1.0"})
        except LookupUnavailable as exc:
            if cached is not None:  # Stale public house data is better than no answer.
                return cached
            log.info("housescore unavailable: %s", exc.code)
            raise
        record = {"url": url, "fetched_at": utc_now().isoformat(), "data": data, "origin": "live"}
        self.cache.write(name, record)
        return record

    def _dominfo(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        name = "dominfo_" + hashlib.sha256(path.encode("utf-8") + b"\n" + body).hexdigest() + ".json"
        cached = self.cache.read(name)
        if cached is not None and _fresh(cached, 30):
            return cached
        try:
            if self.live_requests["dominfo"] >= 2:
                raise LookupUnavailable("quota")
            self.live_requests["dominfo"] += 1
            data = self._send("POST", DOMINFO_URL + path, "dominfo.ru", body=body, headers={
                "User-Agent": "Mozilla/5.0 (compatible; zhkh-max-assistant/1.0)",
                "Content-Type": "application/json", "Accept": "application/json"})
        except LookupUnavailable:
            if cached is not None:
                return cached
            raise
        record = {"url": DOMINFO_URL + path, "fetched_at": utc_now().isoformat(), "data": data}
        self.cache.write(name, record)
        return record

    def find_houses(self, address: str, user_scope: str | None = None) -> list[dict]:
        """One HouseScore search; returns [{fias_guid, address}] (possibly empty)."""
        self._start_budget()
        record = self._housescore("/api/houses/find-by-address", {"q": address}, user_scope=user_scope)
        items = record["data"].get("data", []) if isinstance(record["data"], dict) else []
        candidates = []
        for item in items if isinstance(items, list) else []:
            guid = str(item.get("fias_id") or item.get("fias_guid") or "") if isinstance(item, dict) else ""
            label = item.get("address") if isinstance(item, dict) else None
            if _GUID.fullmatch(guid) and isinstance(label, str) and label.strip():
                candidates.append({"fias_guid": guid, "address": " ".join(label.split())[:300]})
        return candidates

    def house_details(self, candidate: dict) -> dict:
        """House card, management company, its contacts and historical supplier candidates."""
        self._start_budget()
        guid = candidate["fias_guid"]
        if not _GUID.fullmatch(guid):
            raise LookupUnavailable("service")
        house_record = self._housescore(f"/api/houses/{quote(guid)}")
        management_record = self._housescore(f"/api/houses/{quote(guid)}/management")
        management = management_record["data"] if isinstance(management_record["data"], dict) else {}
        company_ref = management.get("management_company")
        if isinstance(company_ref, list):
            company_ref = company_ref[0] if company_ref else None
        ogrn = str(company_ref.get("ogrn")) if isinstance(company_ref, dict) and company_ref.get("ogrn") else None
        company_record = None
        warnings = []
        if ogrn and re.fullmatch(r"\d{13,15}", ogrn):
            try:
                company_record = self._housescore(f"/api/companies/{quote(ogrn)}")
            except LookupUnavailable:
                warnings.append("Контакты управляющей организации сейчас не удалось получить.")
        else:
            warnings.append("У управляющей организации нет ОГРН в источнике; контакты не запрошены.")
        house = house_record["data"] if isinstance(house_record["data"], dict) else {}
        address = house.get("address") or candidate["address"]
        services = [{"service_code": code, "service_name": name, "status": "unknown", "organization": None}
                    for code, name in SERVICE_NAMES.items()]
        dominfo_source = None
        try:
            facts, dominfo_source = dynamic_provider_facts(address, self._dominfo)
            for service in services:
                if service["service_code"] in facts:
                    service.update(facts[service["service_code"]])
            if ogrn and dominfo_source.get("management_ogrn") and ogrn != str(dominfo_source["management_ogrn"]):
                warnings.append("Dominfo указывает другую, вероятно прежнюю УК; сведения о поставщиках требуют проверки.")
        except (LookupUnavailable, KeyError, TypeError, AttributeError, ValueError):
            warnings.append("Поставщиков по услугам сейчас не удалось найти в открытых данных.")
        if any(item["status"] == "candidate" for item in services):
            warnings.append("Поставщики указаны по историческим данным; действующий договор с домом не проверен.")
        return {
            "address": address, "fias_guid": guid, "house": house, "management": management,
            "company": company_record["data"] if company_record and isinstance(company_record["data"], dict) else None,
            "services": services, "warnings": warnings,
            "sources": {"house": {"url": house_record["url"], "fetched_at": house_record["fetched_at"]},
                        "management": {"url": management_record["url"], "fetched_at": management_record["fetched_at"]},
                        "company": {"url": company_record["url"], "fetched_at": company_record["fetched_at"]}
                        if company_record else None,
                        "dominfo": dominfo_source},
        }


def _dominfo_service_code(name: str) -> str | None:
    normalized = re.sub(r"[^а-яёa-z]+", " ", name.casefold()).strip().replace("ё", "е")
    return {
        "отопление": "heating",
        "горячее водоснабжение": "hot_water",
        "холодное водоснабжение": "cold_water",
        "водоотведение": "sewerage",
        "электроснабжение": "electricity",
        "газоснабжение": "gas",
        "обращение с твердыми коммунальными отходами": "waste",
        "вывоз твердых коммунальных отходов": "waste",
    }.get(normalized)


def _plain(value: str) -> str:
    return re.sub(r"[^0-9а-яa-z]+", "", value.casefold().replace("ё", "е"))


def _dominfo_matches_house(address: str, house: dict) -> bool:
    fias = house.get("passport", {}).get("fias", {})
    normalized = _plain(address)
    for field in ("formalname_region", "formalname_city", "formalname_settlement", "formalname_street"):
        name = fias.get(field)
        if name and _plain(name) not in normalized:
            return False
    return (_house_number(address) == str(fias.get("house_number", "")).casefold()
            and (_corpus_number(address) or "") == str(fias.get("block") or "").casefold())


def dynamic_provider_facts(address: str, post: Callable[[str, dict], dict]) -> tuple[dict, dict]:
    search = post("/api/houses/search/general", {"query": address})
    results = search["data"].get("response", {}).get("data", {}).get("results", [])
    candidates = [{"address": item["house"].get("address", ""), "item": item}
                  for item in results if isinstance(item.get("house"), dict)]
    choice = choose_house(address, candidates)
    selected = choice["house"] or (choice["options"][0] if choice["status"] == "confirm"
                                   and len(choice["options"]) == 1 else None)
    if selected is None:
        raise LookupUnavailable("service")
    item = selected["item"]
    slug = item["house"].get("link")
    if not slug or not re.fullmatch(r"[a-z0-9-]+", slug):
        raise LookupUnavailable("service")
    card = post("/api/houses/house/get", {"link": slug})
    house = card["data"].get("response", {}).get("data", {}).get("house", {})
    if not _dominfo_matches_house(address, house):
        raise LookupUnavailable("service")
    page_url = f"https://dominfo.ru/dom/{slug}"
    facts = {}
    utilities = house.get("management", {}).get("utilities") or {}
    for utility in utilities.values() if isinstance(utilities, dict) else utilities:
        code = _dominfo_service_code(utility.get("service", {}).get("name", ""))
        company = utility.get("company") or {}
        if not code or not company.get("name"):
            continue
        started = utility.get("date_start") or {}
        start_utc = (datetime.fromtimestamp(started["seconds"], timezone.utc).isoformat()
                     if isinstance(started.get("seconds"), (int, float)) else None)
        organization = company["name"].strip()
        if organization.count('"') % 2:
            organization += '"'
        facts[code] = {"status": "candidate", "organization": organization,
                       "organization_inn": company.get("inn"), "role": "resource_supplier",
                       "source_url": page_url, "record_start_at_utc": start_utc,
                       "source_reviewed_at": card["fetched_at"][:10],
                       "note": "Исторические сведения Dominfo; действующий договор не проверен"}
    gas_type = str(house.get("passport", {}).get("engineering", {}).get("gas_type", ""))
    if "отсутств" in gas_type.casefold() and "gas" not in facts:
        facts["gas"] = {"status": "not_available", "organization": None,
                        "note": "По техническому паспорту Dominfo газоснабжение отсутствует",
                        "source_url": page_url, "source_reviewed_at": card["fetched_at"][:10]}
    return facts, {"url": page_url, "fetched_at": card["fetched_at"],
                   "management_company": item.get("name_short"), "management_ogrn": item.get("ogrn")}


def _web_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
        return value
    return None


def _phone(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if len(digits) == 11 and digits[0] == "7":
        return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:]}"
    return None


def build_service_card(result: dict, code: str, contacts: dict | None = None) -> dict:
    """Bot-ready view of exactly one service ("management" = only the managing company)."""
    if code != "management" and code not in SERVICE_NAMES:
        raise LookupUnavailable("service")
    contacts = organization_contacts() if contacts is None else contacts
    links = []
    provider = None
    service = {"code": code, "name": "Управляющая организация" if code == "management" else SERVICE_NAMES[code],
               "status": "management", "note": None}
    source = {"url": None, "reviewed_at": None, "record_start_at_utc": None}
    if code != "management":
        fact = next(item for item in result["services"] if item["service_code"] == code)
        service.update({"status": fact["status"], "note": fact.get("note")})
        if fact.get("organization") and fact["status"] in {"candidate", "verified"}:
            inn = str(fact.get("organization_inn") or "")
            contact = contacts.get(inn, {}) if inn else {}
            website = _web_url(contact.get("website")) if contact.get("website_source_url") else None
            provider = {"name": fact["organization"], "inn": inn or None, "website": website,
                        "contact_url": _web_url(contact.get("contact_url")),
                        "contact_label": contact.get("contact_label")}
            if website:
                links.append({"label": "Сайт поставщика", "url": website})
            if provider["contact_url"]:
                links.append({"label": provider["contact_label"] or "Контакты поставщика",
                              "url": provider["contact_url"]})
        source = {"url": _web_url(fact.get("source_url")), "reviewed_at": fact.get("source_reviewed_at"),
                  "record_start_at_utc": fact.get("record_start_at_utc")}
        if source["url"] and urlparse(source["url"]).hostname != "housescore.ru":
            links.append({"label": "Источник сведений", "url": source["url"]})
    company = result.get("company") or {}
    reference = result.get("management", {}).get("management_company") or {}
    if isinstance(reference, list):
        reference = reference[0] if reference else {}
    origin = result["sources"].get("company") or result["sources"]["management"]
    management = {"name": company.get("name") or (reference.get("name") if isinstance(reference, dict) else None),
                  "phone": _phone(company.get("phone")) or (company.get("phone") or None),
                  "email": company.get("email") if isinstance(company.get("email"), str) else None,
                  "fetched_at": origin["fetched_at"][:10]}
    return {"address": result["address"], "fias_guid": result["fias_guid"], "service": service,
            "provider": provider, "management": management, "source": source, "links": links[:3],
            "warnings": list(result.get("warnings", []))}


def render_card_text(card: dict) -> str:
    service = card["service"]
    provider = card["provider"]
    lines = [f"{service['name']} · {card['address']}"]
    if service["code"] != "management":
        if service["status"] == "candidate" and provider:
            lines.append(f"Поставщик (по историческим открытым данным): {provider['name']}.")
            lines.append("Что он обслуживает дом сейчас, не подтверждено — сверьте с квитанцией.")
        elif service["status"] == "verified" and provider:
            lines.append(f"Поставщик: {provider['name']}.")
        elif service["status"] == "not_available":
            lines.append((service.get("note") or "По данным источника система в доме отсутствует") + ".")
        else:
            lines.append("Поставщик этой услуги в открытых данных не найден. "
                         "Он указан в квитанции как получатель платы за услугу.")
        if provider and not provider["website"] and not provider["contact_url"]:
            lines.append("Официальный сайт поставщика пока не подтверждён.")
    management = card["management"]
    if management["name"]:
        lines.append(f"Управляющая организация: {management['name']}.")
        if management["phone"]:
            lines.append(f"Телефон УК: {management['phone']}")
        if management["email"]:
            lines.append(f"Почта УК: {management['email']}")
        if not management["phone"] and not management["email"]:
            lines.append("Контакты УК в источнике не указаны.")
        lines.append(f"Данные УК: HouseScore, получены {management['fetched_at']}.")
    else:
        lines.append("Управляющая организация в источнике не указана.")
    return "\n".join(lines)


def db_quota(store, settings) -> Callable[[str, str | None], None]:
    """Atomically count live HouseScore requests per day, globally and per user."""
    from sqlalchemy.exc import IntegrityError

    from app.db.models import ExternalUsage

    def consume(provider: str, user_scope: str | None) -> None:
        day = utc_now().date().isoformat()
        checks = [("global", settings.housescore_daily_limit, "quota")]
        if user_scope:
            checks.append((f"user:{user_scope}"[:64], settings.house_lookup_user_daily_limit, "user_quota"))
        for attempt in range(2):
            try:
                with store.Session.begin() as session:
                    rows = []
                    for scope, limit, code in checks:
                        row = session.get(ExternalUsage, (provider, scope, day), with_for_update=True)
                        if row is None:
                            row = ExternalUsage(provider=provider, scope=scope, day=day, count=0)
                            session.add(row)
                            session.flush()
                        if row.count >= limit:
                            raise LookupUnavailable(code)
                        rows.append(row)
                    for row in rows:
                        row.count += 1
                return
            except IntegrityError:
                if attempt:
                    raise LookupUnavailable("quota") from None

    return consume


def lookup_for(store) -> HouseLookup:
    settings = store.settings
    return HouseLookup(api_key=settings.housescore_api_key, cache_dir=settings.house_cache_dir,
                       quota=db_quota(store, settings))
