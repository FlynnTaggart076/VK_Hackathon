"""One step-by-step assistant dialogue shared by the MAX chat and the mini-app.

The server keeps the slots (topic, service, city, house address, pending question and offered
options) in `dialog_states`, so a clarification answer — a button, a number or plain text such as
«Москва» — always continues the pending question instead of starting a new one. Contact questions
go through the house lookup (HouseScore + Dominfo); other questions use the local knowledge engine
and the receipt facts. DeepSeek only helps to read free text and to phrase answers, with consent.
"""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.services.assistant_adapter import _fallback_intent
from app.services.house_lookup import (
    SERVICE_NAMES, LookupUnavailable, build_service_card, choose_house, clean_address,
    query_house_number, render_card_text,
)

log = logging.getLogger("app.dialog")

CHANNELS = frozenset({"max_chat", "web"})
FLOW_TTL = timedelta(minutes=30)
MEMORY_TTL = timedelta(days=30)
CONTACT_TOPICS = ("supplier_contacts", "management_contacts", "meter_readings", "meter_deadline", "service_issue")

SERVICE_OPTIONS = (
    ("cold_water", "Холодная вода"), ("hot_water", "Горячая вода"), ("heating", "Отопление"),
    ("electricity", "Электричество"), ("sewerage", "Водоотведение"), ("gas", "Газ"),
    ("waste", "Вывоз мусора (ТКО)"), ("management", "Управляющая компания"),
)
ENGINE_SERVICE_OPTIONS = (
    ("cold_water", "Холодная вода"), ("hot_water", "Горячая вода"), ("heating", "Отопление"),
    ("electricity", "Электроэнергия"), ("drainage", "Водоотведение"), ("maintenance", "Содержание жилья"),
    ("capital_repair", "Капремонт"), ("waste", "Вывоз отходов"), ("other", "Другая услуга"),
)
ROLE_OPTIONS = (("owner", "Собственник"), ("tenant", "Наниматель или арендатор"), ("other", "Другая роль"))
MENU = (
    ("topic:supplier_contacts", "Контакты поставщика"),
    ("topic:management_contacts", "Контакты УК"),
    ("topic:meter_readings", "Передать показания"),
    ("intent:bill_rise", "Почему выросла сумма"),
    ("topic:service_issue", "Проблема с услугой"),
    ("topic:new_resident", "Я переехал(а)"),
)
BACK = ("reset", "Новый вопрос")
CONSENT_OPTIONS = (("consent:on", "Включить умные ответы"), ("consent:off", "Без нейросети"))
GLOBAL_WORDS = {
    "новый вопрос": "reset", "меню": "reset", "/reset": "reset", "/menu": "reset", "заново": "reset",
    "начать заново": "reset", "сброс": "reset", "отмена": "reset", "главное меню": "reset",
    "другой адрес": "change_address", "сменить адрес": "change_address",
    "другая услуга": "change_service", "сменить услугу": "change_service",
    "включить умные ответы": "consent:on", "/llm_on": "consent:on",
    "без нейросети": "consent:off", "/llm_off": "consent:off",
    "попробовать ещё раз": "retry_lookup", "попробовать еще раз": "retry_lookup",
}
SMALLTALK = {"привет", "здравствуйте", "добрый день", "добрый вечер", "доброе утро", "спасибо",
             "спасибо большое", "ок", "понятно", "хорошо", "hi", "hello"}

# City dictionary: Moscow, Moscow Oblast towns (catalog territories) and large cities elsewhere.
_MO_TOWNS = (
    "Люберцы", "Химки", "Балашиха", "Подольск", "Мытищи", "Королёв", "Красногорск", "Одинцово",
    "Домодедово", "Реутов", "Лобня", "Долгопрудный", "Щёлково", "Пушкино", "Сергиев Посад", "Коломна",
    "Электросталь", "Серпухов", "Ногинск", "Раменское", "Жуковский", "Видное", "Дзержинский",
    "Котельники", "Лыткарино", "Дмитров", "Клин", "Воскресенск", "Чехов", "Наро-Фоминск", "Истра",
    "Солнечногорск", "Фрязино", "Ивантеевка", "Звенигород", "Орехово-Зуево", "Егорьевск", "Ступино",
    "Дубна", "Бронницы", "Краснознаменск", "Протвино", "Пущино", "Лосино-Петровский", "Электроугли",
    "Старая Купавна", "Красноармейск", "Шатура", "Павловский Посад", "Кашира", "Можайск", "Руза",
)
_OTHER_CITIES = (
    "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород", "Челябинск",
    "Самара", "Омск", "Ростов-на-Дону", "Уфа", "Красноярск", "Воронеж", "Пермь", "Волгоград",
    "Краснодар", "Саратов", "Тюмень", "Тольятти", "Ижевск", "Барнаул", "Ульяновск", "Иркутск",
    "Хабаровск", "Ярославль", "Владивосток", "Махачкала", "Томск", "Оренбург", "Кемерово",
    "Новокузнецк", "Рязань", "Астрахань", "Набережные Челны", "Пенза", "Киров", "Липецк",
    "Чебоксары", "Калининград", "Тула", "Курск", "Сочи", "Ставрополь", "Тверь", "Магнитогорск",
    "Иваново", "Брянск", "Белгород", "Сургут", "Владимир", "Архангельск", "Калуга", "Смоленск",
    "Чита", "Орёл", "Мурманск", "Вологда", "Кострома", "Петрозаводск", "Новгород", "Псков", "Тамбов",
)
_CITY_ALIASES = {"мск": "Москва", "спб": "Санкт-Петербург", "питер": "Санкт-Петербург",
                 "петербург": "Санкт-Петербург", "нн": "Нижний Новгород", "екб": "Екатеринбург"}
_STREET = (r"(?:улица|улице|улицы|ул|проспект|проспекте|пр-кт|пр-т|просп|переулок|переулке|пер|шоссе|ш|бульвар|"
           r"бульваре|б-р|бул|проезд|проезде|пр-д|набережная|набережной|наб|площадь|площади|пл|микрорайон|"
           r"микрорайоне|мкр|аллея|аллее|тупик|линия|квартал|кв-л|посёлок|поселок|пос)")


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[0-9a-zа-я/\-]+", text.casefold().replace("ё", "е")))


_PLURAL_GENITIVE = {"люберцы": {"люберец"}, "химки": {"химок"}, "мытищи": {"мытищ"}}
_STREET_WORDS = {"улица", "ул", "проспект", "пр-кт", "пр-т", "просп", "переулок", "пер", "шоссе", "ш", "бульвар",
                 "б-р", "бул", "проезд", "пр-д", "набережная", "наб", "площадь", "пл", "аллея", "им", "имени",
                 "улице", "улицы", "проспекте", "переулке", "шоссе"}


def _forms(name: str) -> set[str]:
    base = name.casefold().replace("ё", "е")
    forms = {base}
    if " " in base or "-" in base:
        return forms
    if base.endswith(("ы", "и")):
        stem = base[:-1]
        forms |= {stem + "ах", stem + "ам", stem + "ами"} | _PLURAL_GENITIVE.get(base, set())
    elif base.endswith("а"):
        stem = base[:-1]
        forms |= {stem + "е", stem + "у", stem + "ы", stem + "и", stem + "ой"}
    elif base.endswith(("ий", "ый")):
        stem = base[:-2]
        forms |= {stem + "ом", stem + "ого", stem + "ому"}
    elif base.endswith(("о", "е")):
        forms.add(base[:-1] + "е")
    else:
        forms |= {base + "е", base + "а", base + "у", base + "ом"}
    return forms


_CITY_INDEX: dict[str, tuple[str, str | None]] = {}
for _name in _MO_TOWNS:
    for _form in _forms(_name):
        _CITY_INDEX[_form] = (_name, "moscow-oblast")
for _name in _OTHER_CITIES:
    for _form in _forms(_name):
        _CITY_INDEX.setdefault(_form, (_name, None))
for _form in _forms("Москва"):
    _CITY_INDEX[_form] = ("Москва", "moscow")
for _alias, _name in _CITY_ALIASES.items():
    _CITY_INDEX[_alias] = (_name, "moscow" if _name == "Москва" else None)


def find_city(text: str) -> tuple[str, str | None, int, str] | None:
    """(display city, catalog territory id or None, offset in normalized text, matched form).

    «ул. Кирова» or «ул. Чехова» are streets, not cities: a form right after a street word is ignored.
    """
    normalized = f" {_norm(text)} "
    region = re.search(r" (?:московская область|московской области|московскую область|подмосковье|подмосковья|"
                       r"подмосковью|мо) ", normalized)
    best = None
    for form, (city, territory) in _CITY_INDEX.items():
        start = 0
        while True:
            index = normalized.find(f" {form} ", start)
            if index < 0:
                break
            before = normalized[:index].split()
            if not before or before[-1] not in _STREET_WORDS:
                if best is None or index < best[2] or (index == best[2] and len(form) > len(best[3])):
                    best = (city, territory, index, form)
                break
            start = index + 1
    if best is None:
        explicit = re.search(r" (?:г|город|гор|городе) ([а-я][а-я\-]{2,40})", normalized)
        if explicit:
            best = (explicit.group(1).capitalize(), None, explicit.start(), explicit.group(1))
    if best is None and region:
        return "Московская область", "moscow-oblast", region.start(), region.group(0).strip()
    if best is not None and best[1] is None and region:
        return best[0], "moscow-oblast", best[2], best[3]
    return best


def find_service(text: str) -> str | None:
    words = _norm(text).split()

    def has(*roots: str) -> bool:
        return any(word.startswith(root) for word in words for root in roots)

    found = []
    if has("хвс", "холодн") and not has("батар"):
        found.append("cold_water")
    if has("гвс", "горяч"):
        found.append("hot_water")
    if has("отоплен", "отопит", "батаре", "тепло", "теплоснаб"):
        found.append("heating")
    if has("электр", "свет", "электроснаб") or "электричество" in words:
        found.append("electricity")
    if has("канализ", "водоотвед", "сток"):
        found.append("sewerage")
    if has("газ"):
        found.append("gas")
    if has("мусор", "тко", "отход", "вывоз"):
        found.append("waste")
    if has("управля", "управляйк") or "ук" in words or "жэк" in words:
        found.append("management")
    return found[0] if len(set(found)) == 1 else None


def mentions_water(text: str) -> bool:
    return any(word.startswith(("вод", "водоснаб")) for word in _norm(text).split())


WATER_OPTIONS = (("service:cold_water", "Холодная вода"), ("service:hot_water", "Горячая вода"),
                 ("service:sewerage", "Водоотведение"))


def detect_contact_topic(text: str) -> str | None:
    words = _norm(text).split()

    def has(*roots: str) -> bool:
        return any(word.startswith(root) for word in words for root in roots)

    readings = has("показан", "счетчик", "водомер", "электросчетчик")
    if readings and has("срок", "когда", "числ", "дат", "последн", "до какого"):
        return "meter_deadline"
    if readings and has("переда", "сдат", "сдава", "отправ", "подат", "ввест", "куда", "где", "как", "кому"):
        return "meter_readings"
    if has("авари", "протек", "затоп", "отключ", "перебо", "пропал", "засор", "прорыв", "неисправ") or \
            (has("нет") and has("вод", "свет", "электр", "отоплен", "газ", "тепл")) or \
            (has("холодн") and has("батар")):
        return "service_issue"
    contact = has("контакт", "телефон", "позвон", "звонит", "связат", "связь", "найт", "узнат", "почт",
                  "сайт", "обрат", "куда", "кому", "кто", "номер", "адрес", "какая", "какой")
    supplier = has("поставщик", "ресурсоснаб", "поставля", "водоканал", "энергосбыт", "рсо")
    management = has("управля", "управляйк") or "ук" in words or "жэк" in words or "уо" in words
    if supplier and (contact or len(words) <= 4):
        return "supplier_contacts"
    if management and (contact or len(words) <= 4):
        return "management_contacts"
    if contact and has("вод", "свет", "электр", "газ", "отоплен", "тепл", "мусор", "тко") and \
            has("кто", "кому", "куда", "телефон", "контакт", "поставля", "обслуж"):
        return "supplier_contacts"
    return None


def find_address(text: str) -> str | None:
    """Address-looking fragment (street marker or «дом N»), starting at the city if it precedes it."""
    lowered = text.lower().replace("ё", "е")
    street = re.search(rf"(?<![\w-]){_STREET}\.?(?![\w-])", lowered)
    house_marker = re.search(r"(?<![\w-])(?:дом|д\.)\s*\d", lowered)
    anchor = street or house_marker
    if anchor is None or query_house_number(text[anchor.start():]) is None:
        return None
    start = anchor.start()
    segment = lowered.rfind(",", 0, start) + 1
    before = lowered[segment:start].split()
    if street is not None and before and re.fullmatch(
            r"[а-я-]+(?:ая|яя|ий|ый|ой|ое|ее|ом|ей|ую)|\d+-?[яйе]", before[-1]):
        start = lowered.rfind(before[-1], segment, start)  # «Примерная улица», «Ленинский проспект», «3-я улица»
    elif street is None and not lowered[segment:start].strip() and segment > 0:
        start = lowered.rfind(",", 0, segment - 1) + 1  # «Гагарина, дом 24»: the street is the previous part
    elif street is None and before:
        start = segment
    city = find_city(text)
    if city is not None:
        pattern = r"(?<![\w-])" + r"[\s,.]+".join(re.escape(part) for part in city[3].split()) + r"(?![\w-])"
        match = re.search(pattern, lowered)
        if match and match.start() < start:
            start = match.start()
    cleaned = clean_address(text[start:])
    return cleaned or None


def _option(value: str, label: str) -> dict:
    return {"value": value, "label": label[:128]}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def empty_state() -> dict:
    return {"v": 1, "flow": None, "topic_id": None, "question": None, "service": None, "awaiting": None,
            "options": [], "candidates": [], "prompt": None,
            "context": {"territory_id": None, "role": None, "service_code": None, "document_kind": None},
            "memory": {"city": None, "territory_id": None, "address": None, "house": None},
            "consent_offered": False, "llm_declined": False, "flow_at": None, "memory_at": None}


def _fresh_flow(state: dict) -> dict:
    fresh = empty_state()
    fresh["memory"] = deepcopy(state.get("memory") or fresh["memory"])
    fresh["consent_offered"] = bool(state.get("consent_offered"))
    fresh["llm_declined"] = bool(state.get("llm_declined"))
    fresh["memory_at"] = state.get("memory_at")
    return fresh


def normalize_state(raw: dict | None, moment: datetime | None = None) -> dict:
    moment = moment or _now()
    state = empty_state()
    if isinstance(raw, dict) and raw.get("v") == 1:
        for key in state:
            if key in raw:
                state[key] = deepcopy(raw[key])
    try:
        if state["memory_at"] and moment - datetime.fromisoformat(state["memory_at"]) > MEMORY_TTL:
            state["memory"] = empty_state()["memory"]
        if state["flow_at"] and moment - datetime.fromisoformat(state["flow_at"]) > FLOW_TTL:
            state = _fresh_flow(state)
    except (TypeError, ValueError):
        state = empty_state()
    return state


@dataclass
class DialogDeps:
    knowledge: object
    answer: Callable[[str, dict, str | None], dict]
    lookup: object | None = None
    extract: Callable[[str, dict], dict] | None = None
    llm_offer: bool = False
    user_scope: str | None = None
    effects: dict = field(default_factory=dict)


def _reply(status: str, text: str, options: list[dict] | None = None, **extra) -> dict:
    reply = {"status": status, "text": text.strip()[:3500], "options": options or [], "card": None,
             "links": [], "sources": [], "actions": [], "awaiting": None, "topic_id": None, "menu": False}
    reply.update(extra)
    return reply


def _menu_reply(state: dict, text: str = "Чем помочь? Выберите тему или напишите вопрос своими словами.") -> dict:
    state["awaiting"] = None
    state["options"] = [_option(value, label) for value, label in MENU]
    return _reply("needs_input", text, list(state["options"]), menu=True)


def _ask(state: dict, awaiting: str, text: str, options: list[tuple[str, str]] | list[dict]) -> dict:
    state["awaiting"] = awaiting
    state["options"] = [item if isinstance(item, dict) else _option(*item) for item in options]
    state["prompt"] = text
    return _reply("needs_input", text, list(state["options"]), awaiting=awaiting, topic_id=state["topic_id"])


def _match_option(state: dict, raw: str) -> dict | None:
    options = state.get("options") or []
    key = _norm(raw)
    for option in options:
        if raw == option["value"] or key == _norm(option["label"]):
            return option
    if re.fullmatch(r"\d{1,2}", key) and 1 <= int(key) <= len(options) and state.get("awaiting"):
        return options[int(key) - 1]
    return None


def _address_query(state: dict, address: str) -> str:
    city = state["memory"].get("city")
    if city and find_city(address) is None:
        return f"{city}, {address}"
    return address


_TOPIC_INTRO = {
    "meter_readings": ("Показания передают организации, которая выставляет эту услугу в квитанции "
                       "(поставщик, расчётный центр или УК): обычно через личный кабинет, приложение или по "
                       "телефону из квитанции. Что известно о вашем доме:"),
    "meter_deadline": ("Единой даты нет: срок передачи показаний устанавливает организация, которая выставляет "
                       "счёт, и обычно он напечатан в квитанции. Уточнить его можно здесь:"),
    "service_issue": ("О перебоях и авариях в доме обычно сообщают в диспетчерскую управляющей организации; "
                      "телефон аварийной службы также печатают в квитанции. Контакты вашего дома:"),
}
_SERVICE_PROMPT = {
    "supplier_contacts": "Найду поставщика по адресу дома. По какой услуге нужен поставщик?",
    "meter_readings": ("Показания передают организации, которая выставляет услугу в квитанции. Подскажу, кто это "
                       "в вашем доме. Показания какой услуги нужно передать?"),
    "meter_deadline": ("Единой даты нет — срок устанавливает организация, которая выставляет счёт. Подскажу, кто это "
                       "в вашем доме. По какой услуге?"),
    "service_issue": "Подскажу, куда обратиться по вашему дому. С какой услугой проблема?",
}
_LOOKUP_REASON = {
    "no_key": "поиск по адресу пока не подключён",
    "quota": "на сегодня исчерпан лимит запросов к справочнику домов",
    "user_quota": "сегодня вы уже проверили несколько новых адресов — попробуйте завтра",
    "timeout": "справочник домов отвечает слишком долго",
    "network": "справочник домов сейчас недоступен",
    "service": "справочник домов вернул неожиданный ответ",
}


def _general_house_links(deps: DialogDeps) -> tuple[list[dict], list[dict]]:
    sources = [item for item in deps.knowledge.sources if item["id"] in {"gis-zhkh-house-card", "gis-zhkh-house-search"}]
    links = [{"label": "Как найти дом в ГИС ЖКХ" if item["id"] == "gis-zhkh-house-search"
              else "Что есть в карточке дома ГИС ЖКХ", "url": item["url"]} for item in sources if item.get("url")]
    return links, sources


def _lookup_failed(state: dict, deps: DialogDeps, code: str) -> dict:
    links, sources = _general_house_links(deps)
    text = (f"Не получилось найти дом: {_LOOKUP_REASON.get(code, 'справочник домов недоступен')}.\n"
            "Управляющую и ресурсоснабжающие организации дома можно посмотреть в открытой части ГИС ЖКХ "
            "(поиск дома по адресу). Поставщик услуги также указан в квитанции как получатель платы.")
    options = [("retry_lookup", "Попробовать ещё раз"), ("change_address", "Другой адрес"), BACK] \
        if code in {"timeout", "network", "service"} else [("change_address", "Другой адрес"), BACK]
    reply = _ask(state, "after_card", text, options)
    reply.update(status="unsupported", links=links, sources=sources)
    return reply


def _continue_contacts(state: dict, deps: DialogDeps) -> dict:
    topic = state["topic_id"]
    memory = state["memory"]
    if state["service"] is None:
        if topic == "management_contacts":
            state["service"] = "management"
        elif state.get("question") and mentions_water(state["question"]):
            return _ask(state, "service", _SERVICE_PROMPT.get(topic, "По какой услуге?") + " Какая именно вода?",
                        list(WATER_OPTIONS) + [("service:management", "Управляющая компания")])
        else:
            return _ask(state, "service", _SERVICE_PROMPT.get(topic, "По какой услуге?"),
                        [(f"service:{code}", label) for code, label in SERVICE_OPTIONS])
    house = memory.get("house")
    if house is None:
        address = memory.get("address")
        if not address or query_house_number(address) is None:
            city = memory.get("city")
            where = (f"Напишите улицу и номер дома в городе {city} (или полный адрес с другим городом)."
                     if city else "Напишите адрес дома: город, улица, номер дома и корпус, если есть.")
            prefix = "Не вижу номера дома. " if address else ""
            text = (f"{prefix}{where} Квартиру указывать не нужно.\n"
                    "Адрес дома передаётся только в открытые справочники домов (HouseScore, Dominfo), "
                    "чтобы найти УК и поставщиков.")
            options = [("reset", "Новый вопрос")]
            return _ask(state, "address", text, options)
        if deps.lookup is None:
            return _lookup_failed(state, deps, "no_key")
        query = _address_query(state, address)
        try:
            candidates = deps.lookup.find_houses(query, deps.user_scope)
        except LookupUnavailable as exc:
            return _lookup_failed(state, deps, exc.code)
        if not candidates:
            memory["address"] = None
            return _ask(state, "address", f"Не нашёл дом по адресу «{query}». Проверьте город, улицу и номер дома "
                                          "и напишите адрес ещё раз.", [BACK])
        choice = choose_house(query, candidates)
        if choice["status"] == "exact":
            memory["house"] = choice["house"]
            house = choice["house"]
        else:
            state["candidates"] = choice["options"]
            options = [(f"house:{index}", item["address"]) for index, item in enumerate(choice["options"])]
            text = ("Дом с таким номером не найден. Похожие адреса:" if choice["status"] == "not_found"
                    else "Уточните дом — выберите адрес из списка:")
            return _ask(state, "house_choice", text, options + [("change_address", "Другой адрес")])
    if deps.lookup is None:
        return _lookup_failed(state, deps, "no_key")
    try:
        details = deps.lookup.house_details(house)
    except LookupUnavailable as exc:
        return _lookup_failed(state, deps, exc.code)
    card = {**build_service_card(details, state["service"]), "intro": _TOPIC_INTRO.get(topic)}
    parts = []
    if topic in _TOPIC_INTRO:
        parts.append(_TOPIC_INTRO[topic])
    parts.append(render_card_text(card))
    if card["warnings"]:
        parts.append("Важно: " + " ".join(card["warnings"][:2]))
    links = list(card["links"])
    sources = []
    if card["provider"] is None and state["service"] != "management":
        general_links, sources = _general_house_links(deps)
        links = (links + general_links)[:3]
    options = [("change_service", "Другая услуга"), ("change_address", "Другой адрес"), BACK]
    reply = _ask(state, "after_card", "\n\n".join(parts), options)
    reply.update(status="answered", card=card, links=links, sources=sources)
    return reply


def _start_contacts(state: dict, deps: DialogDeps, topic: str, text: str | None) -> dict:
    state["flow"] = "contacts"
    state["topic_id"] = topic
    state["question"] = text
    if text:
        service = find_service(text)
        if service and not (topic != "management_contacts" and service == "management"):
            state["service"] = service
        address = find_address(text)
        if address:
            _set_address(state, address)
    return _continue_contacts(state, deps)


def _set_address(state: dict, address: str) -> None:
    memory = state["memory"]
    city = find_city(address)
    if city is not None:
        memory["city"] = city[0]
        if city[1]:
            memory["territory_id"] = city[1]
    memory["address"] = clean_address(address)
    memory["house"] = None
    state["candidates"] = []


def _render_answer(state: dict, question: str, result: dict) -> dict:
    """Engine/receipt AnswerResult -> dialogue reply, turning clarifications into options."""
    status = result["status"]
    state["topic_id"] = result.get("topic_id") or state["topic_id"]
    text = result["text"]
    record = {"question": question[:2000], "result": result}
    if status == "needs_clarification" and result.get("clarification"):
        clarification = result["clarification"]
        field_name = clarification["field"]
        if field_name == "territory_id":
            options = [(f"territory:{item['value']}", item["label"]) for item in clarification["options"]]
            prompt = clarification["prompt"] + " Можно выбрать или написать город."
            reply = _ask(state, "territory", prompt, options + [BACK])
        elif field_name == "role":
            reply = _ask(state, "role", clarification["prompt"], [(f"role:{value}", label) for value, label in ROLE_OPTIONS])
        elif field_name == "service_code":
            reply = _ask(state, "engine_service", clarification["prompt"],
                         [(f"engine_service:{value}", label) for value, label in ENGINE_SERVICE_OPTIONS])
        elif field_name == "topic_id":
            reply = _ask(state, "topic", "Уточните, что именно вас интересует:",
                         [(f"topic:{item['value']}", item["label"]) for item in clarification["options"]] + [BACK])
        else:
            reply = _ask(state, field_name, clarification["prompt"] + " Напишите ответ одним сообщением.", [BACK])
        reply["_answer"] = record
        return reply
    lines = [text]
    steps = result.get("steps") or []
    if steps:
        lines.append("\n".join(f"{index}. {item}" for index, item in enumerate(steps, 1)))
    if result.get("limitations"):
        lines.append("Ограничения: " + " ".join(result["limitations"]))
    links = [{"label": item["title"][:60], "url": item["url"]} for item in result.get("sources", []) if item.get("url")]
    links += [{"label": item["label"], "url": item["url"]} for item in result.get("actions", [])
              if item.get("type") == "open_link" and item.get("url")]
    if status == "unsupported" and not result.get("topic_id"):
        reply = _menu_reply(state, "\n\n".join(lines + ["Выберите тему из списка или переформулируйте вопрос."]))
        reply["status"] = "unsupported"
    elif status == "unsupported":
        # No verified local instruction: offer the managing company's contacts instead of a dead end.
        state["awaiting"] = None
        state["options"] = [_option("topic:management_contacts", "Контакты УК"), _option(*BACK)]
        lines.append("Местный порядок подскажет управляющая организация дома — могу найти её контакты по адресу.")
        reply = _reply(status, "\n\n".join(lines), list(state["options"]), topic_id=state["topic_id"])
    else:
        state["awaiting"] = None
        state["options"] = [_option(*BACK)]
        reply = _reply(status, "\n\n".join(lines), list(state["options"]), topic_id=state["topic_id"])
    unique = []
    for link in links:
        if link["url"] not in {item["url"] for item in unique}:
            unique.append(link)
    reply.update(links=unique[:3], sources=result.get("sources", []), actions=result.get("actions", []))
    reply["_answer"] = record
    return reply


def _faq(state: dict, deps: DialogDeps, llm: dict | None = None, intent: str | None = None) -> dict:
    state["flow"] = "faq"
    question = state["question"] or "Вопрос по ЖКХ"
    context = {"territory_id": state["context"]["territory_id"] or state["memory"].get("territory_id"),
               "role": state["context"]["role"], "topic_id": state["topic_id"], "organization_id": None,
               "service_code": state["context"]["service_code"], "document_kind": state["context"]["document_kind"]}
    if intent is None and llm is not None:
        intent = _fallback_intent(question)  # The turn was already read by the model; skip classify().
    result = deps.answer(question, context, intent)
    unclear = (result["status"] == "unsupported" and not result.get("topic_id")) or (
        result["status"] == "needs_clarification" and (result.get("clarification") or {}).get("field") == "topic_id")
    if unclear and llm and llm.get("topic_id") and state["topic_id"] is None:
        if llm["topic_id"] in CONTACT_TOPICS:
            return _start_contacts(state, deps, llm["topic_id"], state["question"])
        context["topic_id"] = llm["topic_id"]
        result = deps.answer(question, context, "faq")
    return _render_answer(state, question, result)


def _new_question(state: dict, deps: DialogDeps, text: str, llm: dict | None) -> dict:
    fresh = _fresh_flow(state)
    state.clear()
    state.update(fresh)
    state["question"] = text[:2000]
    city = find_city(text)
    if city is not None:
        state["memory"]["city"] = city[0]
        if city[1]:
            state["memory"]["territory_id"] = city[1]
            state["context"]["territory_id"] = city[1]
    topic = detect_contact_topic(text)
    if topic is None and len(_norm(text).split()) <= 3 and find_service(text):
        # A bare service name (often a tap on an old keyboard) means «who supplies it».
        topic = "management_contacts" if find_service(text) == "management" else "supplier_contacts"
    if topic is None and llm and llm.get("topic_id") in CONTACT_TOPICS and llm.get("intent") != "smalltalk":
        topic = llm["topic_id"]
    if topic:
        return _start_contacts(state, deps, topic, text)
    address = find_address(text)
    city_only = city is not None and len(_norm(text).split()) <= 3
    if address or city_only:
        # Only an address or a city, no question: ask what to look up there.
        if address:
            _set_address(state, address)
        else:
            _set_city_only(state, city)
        where = f"по адресу «{address}»" if address else f"в городе {city[0]}"
        return _ask(state, "topic", f"Что найти {where}?", [
            ("topic:management_contacts", "Контакты УК"), ("topic:supplier_contacts", "Поставщик услуги"),
            ("topic:meter_readings", "Куда передать показания"), BACK])
    return _faq(state, deps, llm)


def _set_city_only(state: dict, city: tuple) -> None:
    memory = state["memory"]
    memory["city"] = city[0]
    if city[1]:
        memory["territory_id"] = city[1]
    memory["address"] = None
    memory["house"] = None
    state["candidates"] = []


def _llm_read(state: dict, deps: DialogDeps, text: str) -> dict | None:
    if deps.extract is None or state.get("awaiting") in {"address", "house_choice"} or find_address(text):
        return None
    summary = {"awaiting": state.get("awaiting"), "topic_id": state.get("topic_id"),
               "options": [item["label"] for item in state.get("options", [])][:10],
               "known": {"service": state.get("service"), "city": state["memory"].get("city")}}
    try:
        return deps.extract(text, summary)
    except Exception:  # ModelUnavailable or any transport failure: deterministic path continues.
        return None


def _apply_option(state: dict, deps: DialogDeps, value: str) -> dict:
    kind, _, argument = value.partition(":")
    if kind == "topic":
        if argument in CONTACT_TOPICS:
            question = state["question"] if state.get("awaiting") == "topic" else None
            fresh = _fresh_flow(state)
            state.clear()
            state.update(fresh)
            return _start_contacts(state, deps, argument, question)
        question = state["question"] if state.get("awaiting") == "topic" and state.get("question") else None
        fresh = _fresh_flow(state)
        state.clear()
        state.update(fresh)
        state["topic_id"] = argument
        title = next((item["title"] for item in deps.knowledge.topics if item["id"] == argument), "Вопрос")
        state["question"] = question or title
        return _faq(state, deps)
    if kind == "intent":
        fresh = _fresh_flow(state)
        state.clear()
        state.update(fresh)
        state["question"] = "Почему выросла сумма в квитанции?"
        return _faq(state, deps, intent=argument)
    if kind == "service":
        state["service"] = argument
        return _continue_contacts(state, deps)
    if kind == "house":
        candidates = state.get("candidates") or []
        if argument.isdigit() and int(argument) < len(candidates):
            state["memory"]["house"] = candidates[int(argument)]
            state["memory"]["address"] = candidates[int(argument)]["address"]
            state["candidates"] = []
        return _continue_contacts(state, deps)
    if kind == "territory":
        state["context"]["territory_id"] = argument
        state["memory"]["territory_id"] = argument
        return _faq(state, deps)
    if kind == "role":
        state["context"]["role"] = argument
        return _faq(state, deps)
    if kind == "engine_service":
        state["context"]["service_code"] = argument
        return _faq(state, deps)
    return _menu_reply(state)


def _global(state: dict, deps: DialogDeps, action: str) -> dict:
    if action == "reset":
        fresh = _fresh_flow(state)
        state.clear()
        state.update(fresh)
        return _menu_reply(state)
    if action.startswith("consent:"):
        enabled = action == "consent:on"
        deps.effects["consent"] = enabled
        state["consent_offered"] = True
        state["options"] = [item for item in state.get("options", []) if not item["value"].startswith("consent:")]
        note = ("Умные ответы включены: текст вопроса без адреса, телефонов и номеров передаётся DeepSeek. "
                "Отключить: «Без нейросети» или /llm_off." if enabled else
                "Хорошо, отвечаю без нейросети — по локальному справочнику и открытым данным.")
        if state.get("awaiting") and state.get("prompt"):
            reply = _reply("needs_input", note + "\n\n" + state["prompt"], list(state["options"]),
                           awaiting=state["awaiting"], topic_id=state["topic_id"])
            return reply
        return _menu_reply(state, note)
    if action == "change_address":
        state["memory"]["address"] = None
        state["memory"]["house"] = None
        state["candidates"] = []
        if state.get("flow") != "contacts":
            state["flow"] = "contacts"
            state["topic_id"] = state.get("topic_id") if state.get("topic_id") in CONTACT_TOPICS else "management_contacts"
        return _continue_contacts(state, deps)
    if action == "change_service":
        if state.get("flow") != "contacts":
            state["flow"] = "contacts"
            state["topic_id"] = "supplier_contacts"
        if state["topic_id"] == "management_contacts":
            state["topic_id"] = "supplier_contacts"
        state["service"] = None
        return _continue_contacts(state, deps)
    if action == "retry_lookup":
        if state.get("flow") == "contacts":
            return _continue_contacts(state, deps)
    return _menu_reply(state)


def _answer_pending(state: dict, deps: DialogDeps, text: str, llm: dict | None) -> dict | None:
    """Interpret free text as the answer to the pending question; None means «a new question»."""
    awaiting = state.get("awaiting")
    if llm and llm.get("option_index") and state.get("options") and llm.get("intent") in {None, "answer"}:
        return _apply_option(state, deps, state["options"][llm["option_index"] - 1]["value"])
    new_topic = detect_contact_topic(text)
    if awaiting == "service":
        service = find_service(text) or (llm or {}).get("service")
        if service:
            state["service"] = service
            address = find_address(text)
            if address:
                _set_address(state, address)
            return _continue_contacts(state, deps)
        if mentions_water(text) and not new_topic:
            return _ask(state, "service", "Какая именно вода?", list(WATER_OPTIONS) + [BACK])
        return None if new_topic or len(_norm(text).split()) > 2 else _ask(
            state, "service", "Не понял услугу. Выберите её кнопкой или напишите, например: «холодная вода», «свет».",
            [(f"service:{code}", label) for code, label in SERVICE_OPTIONS])
    if awaiting in {"address", "house_choice"}:
        other_service = find_service(text) not in {None, state.get("service")} or mentions_water(text)
        if new_topic and (new_topic != state["topic_id"] or other_service) and find_address(text) is None:
            return None
        address = find_address(text)
        if address is None and query_house_number(text) is not None and len(text) <= 120:
            address = clean_address(text)
        if address:
            _set_address(state, address)
            return _continue_contacts(state, deps)
        city = find_city(text)
        if city is not None and len(_norm(text).split()) <= 4:
            state["memory"]["city"] = city[0]
            if city[1]:
                state["memory"]["territory_id"] = city[1]
            state["memory"]["address"] = None
            return _continue_contacts(state, deps)
        looks_like_street = re.search(rf"(?<![\w-]){_STREET}\.?(?![\w-])", text.lower()) is not None
        if awaiting == "address" and looks_like_street and len(text) <= 120 and "?" not in text:
            state["memory"]["address"] = clean_address(text)  # Street without a number: ask for the number.
            return _continue_contacts(state, deps)
        if awaiting == "address" and new_topic == state["topic_id"]:
            return _ask(state, "address", "Чтобы найти контакты, нужен адрес дома: город, улица и номер дома.",
                        state["options"])
        return None
    if awaiting == "after_card":
        service = find_service(text)
        if service and len(_norm(text).split()) <= 3 and state.get("flow") == "contacts":
            if state["topic_id"] == "management_contacts" and service != "management":
                state["topic_id"] = "supplier_contacts"
            state["service"] = service
            return _continue_contacts(state, deps)
        address = find_address(text)
        if address and not new_topic:
            _set_address(state, address)
            return _continue_contacts(state, deps)
        city = find_city(text)
        if city is not None and len(_norm(text).split()) <= 3 and state.get("flow") == "contacts":
            _set_city_only(state, city)  # «Люберцы» after a card: another house in that city.
            return _continue_contacts(state, deps)
        return None
    if awaiting == "territory":
        city = find_city(text)
        if city is None and llm and llm.get("city"):
            city = find_city(llm["city"]) or (llm["city"], None, 0)
        if city is not None:
            state["memory"]["city"] = city[0]
            if city[1]:
                state["context"]["territory_id"] = city[1]
                state["memory"]["territory_id"] = city[1]
                return _faq(state, deps)
            state["awaiting"] = None
            state["options"] = [_option(*BACK)]
            return _reply("unsupported",
                          f"Для региона «{city[0]}» у меня пока нет проверенной местной инструкции — "
                          "проверенные сведения есть для Москвы и Московской области. Порядок зависит от региона: "
                          "уточните его в МФЦ или на официальном портале вашего региона.",
                          list(state["options"]), topic_id=state["topic_id"])
        return None if new_topic or len(_norm(text).split()) > 3 else _ask(
            state, "territory", "Не узнал город. Напишите город или выберите регион кнопкой.", state["options"])
    if awaiting == "role":
        words = _norm(text)
        role = ("owner" if re.search(r"собствен|владел|хозя", words) else
                "tenant" if re.search(r"аренд|нанимат|снима|съем|жилец|квартирант", words) else
                "other" if re.search(r"друг|иное|никто", words) else None)
        if role:
            state["context"]["role"] = role
            return _faq(state, deps)
        return None if len(_norm(text).split()) > 2 else _ask(state, "role", "Выберите роль кнопкой.", state["options"])
    if awaiting == "engine_service":
        service = find_service(text)
        mapped = {"sewerage": "drainage", "gas": "other", "management": "maintenance"}.get(service, service)
        if mapped:
            state["context"]["service_code"] = mapped
            return _faq(state, deps)
        return None if len(_norm(text).split()) > 2 else _ask(state, "engine_service", "Выберите услугу кнопкой.", state["options"])
    if awaiting == "document_kind":
        if new_topic or len(text) > 200:
            return None
        state["context"]["document_kind"] = " ".join(text.split())[:200]
        return _faq(state, deps)
    return None


def step(raw_state: dict | None, text: str | None, choice: str | None, deps: DialogDeps,
         moment: datetime | None = None) -> tuple[dict, dict]:
    """Advance the dialogue by one user turn. Returns (new state, reply)."""
    moment = moment or _now()
    state = normalize_state(raw_state, moment)
    raw = (choice or text or "").strip()[:2000]
    key = _norm(raw)
    if not raw:
        if state.get("awaiting") and state.get("prompt"):
            reply = _reply("needs_input", state["prompt"], list(state["options"]),
                           awaiting=state["awaiting"], topic_id=state["topic_id"])
        else:
            reply = _menu_reply(state, "Здравствуйте! Я помогу разобраться с ЖКХ: найду УК и поставщиков по "
                                       "адресу дома, объясню квитанцию и подскажу, куда обратиться.")
    elif raw in GLOBAL_WORDS.values() or key in GLOBAL_WORDS:
        reply = _global(state, deps, GLOBAL_WORDS.get(key, raw))
    else:
        option = _match_option(state, raw)
        if option is not None:
            action = option["value"]
            reply = _global(state, deps, action) if action in GLOBAL_WORDS.values() else \
                _apply_option(state, deps, action)
        elif choice is not None and ":" in choice and choice.split(":", 1)[0] in {"topic", "intent"}:
            reply = _apply_option(state, deps, choice)  # Quick start from the mini-app, e.g. ?topic=
        elif key in SMALLTALK:
            reply = _menu_reply(state, "Пожалуйста! Чем ещё помочь?" if key.startswith("спасибо") else
                                "Здравствуйте! Чем помочь? Выберите тему или напишите вопрос.")
        else:
            llm = _llm_read(state, deps, raw)
            if llm and llm.get("intent") == "reset":
                reply = _global(state, deps, "reset")
            elif llm and llm.get("intent") == "smalltalk" and not detect_contact_topic(raw):
                reply = _menu_reply(state, "Чем помочь? Выберите тему или напишите вопрос.")
            else:
                reply = _answer_pending(state, deps, raw, llm) if state.get("awaiting") else None
                if reply is None:
                    reply = _new_question(state, deps, raw, llm)
    if deps.llm_offer and not state.get("consent_offered") and reply.get("status") != "error":
        state["consent_offered"] = True
        reply["text"] += ("\n\nМогу понимать вопросы точнее с помощью нейросети DeepSeek: ей передаётся только "
                          "текст вопроса без адреса, телефонов и номеров. Включить?")
        reply["options"] = reply["options"] + [_option(*item) for item in CONSENT_OPTIONS]
        state["options"] = state["options"] + [_option(*item) for item in CONSENT_OPTIONS]
    if not state.get("prompt") or not state.get("awaiting"):
        state["prompt"] = reply["text"] if state.get("awaiting") else None
    stamp = moment.isoformat()
    state["flow_at"] = stamp
    state["memory_at"] = stamp
    reply["awaiting"] = state.get("awaiting")
    return state, reply


def public_reply(reply: dict) -> dict:
    """Drop internal keys before the reply leaves the server."""
    return {key: value for key, value in reply.items() if not key.startswith("_")}

