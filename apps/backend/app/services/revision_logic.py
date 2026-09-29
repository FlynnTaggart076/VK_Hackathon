"""Rebase receipt evidence on stable line IDs when a user edits a bill."""

from __future__ import annotations

from copy import deepcopy


SERVER_FIELDS = {"schema_version", "currency", "template_id", "template_version",
                 "formula_kind", "calculation_kind", "line_id", "adjustment_id"}


def _at(document: object, parts: list[str]):
    value = document
    for part in parts:
        try:
            value = value[int(part)] if isinstance(value, list) else value[part]
        except (IndexError, KeyError, ValueError, TypeError):
            return object()
    return value


def _map_path(parts: list[str], old: dict, new: dict) -> list[str] | None:
    if len(parts) < 2 or parts[0] not in {"services", "adjustments"}:
        return parts
    collection = parts[0]
    id_field = "line_id" if collection == "services" else "adjustment_id"
    try:
        old_id = old[collection][int(parts[1])][id_field]
    except (IndexError, KeyError, ValueError, TypeError):
        return None
    for index, item in enumerate(new[collection]):
        if item[id_field] == old_id:
            return [collection, str(index), *parts[2:]]
    return None


def _leaf_paths(value: object, prefix: list[str] | None = None):
    prefix = prefix or []
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaf_paths(child, [*prefix, key])
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaf_paths(child, [*prefix, str(index)])
    elif prefix and prefix[-1] not in SERVER_FIELDS:
        yield prefix


def _pointer(parts: list[str]) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)


def rebase_issues(old: dict, new: dict, issues: list[dict]) -> list[dict]:
    """Keep only the extraction issues that still describe the edited bill.

    Paths are followed by stable line IDs, so deleting or reordering lines never moves an
    issue onto another line. An issue is dropped when its line was removed, when the user
    changed exactly the value it points to (for example the service code of an unrecognised
    line), and when it is an extraction error: a saved manual edit supersedes a failed parse,
    and the bill is validated again anyway.
    """
    kept: list[dict] = []
    for item in issues:
        if item.get("severity") == "error":
            continue
        path = item.get("path")
        if not path:
            kept.append(item)
            continue
        parts = [part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:]]
        mapped = _map_path(parts, old, new)
        if not mapped:
            continue
        if len(parts) >= 3 and _at(old, parts) != _at(new, mapped):
            continue
        kept.append(dict(item, path=_pointer(mapped)))
    return kept


def rebase_evidence(old: dict, new: dict, evidence: list[dict]) -> list[dict]:
    old_by_new: dict[str, object] = {}
    for path in _leaf_paths(old):
        mapped = _map_path(path, old, new)
        if mapped:
            old_by_new[_pointer(mapped)] = _at(old, path)
    kept: dict[str, dict] = {}
    for item in evidence:
        parts = [part.replace("~1", "/").replace("~0", "~") for part in item["path"].split("/")[1:]]
        mapped = _map_path(parts, old, new)
        if not mapped:
            continue
        path = _pointer(mapped)
        if _at(old, parts) == _at(new, mapped):
            preserved = deepcopy(item)
            preserved["path"] = path
            kept[path] = preserved
    for parts in _leaf_paths(new):
        path = _pointer(parts)
        if path not in kept and (path not in old_by_new or old_by_new[path] != _at(new, parts)):
            kept[path] = {"path": path, "source": "manual", "page_number": None,
                          "bbox": None, "source_text": None, "needs_review": False,
                          "reason": "Значение изменено пользователем."}
    return list(kept.values())
