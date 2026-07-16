"""Video 清单交换合同：JSON/CSV 同构、先预览再提交。"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Mapping
from typing import Any

from video_ops.application.errors import ApplicationError
from video_ops.application.service import VideoOperationsService
from video_ops.domain.models import Video, WorkspaceSnapshot

INTERCHANGE_SCHEMA = "video-ops.video-list/v1"
FORMULA_CELL = re.compile(r"^\s*[=+\-@]")
FIELDS = (
    "external_video_id",
    "code",
    "title",
    "goal",
    "brief",
    "account_refs",
    "product_ref",
    "parent_external_video_id",
    "variation_note",
)
ALIASES = {
    "external_video_id": ("external_video_id", "video_id", "外部视频ID"),
    "code": ("code", "编号", "视频编号"),
    "title": ("title", "标题", "视频名称"),
    "goal": ("goal", "目标", "本次目标"),
    "brief": ("brief", "context", "Context", "上下文"),
    "account_refs": ("account_refs", "account_ids", "accounts", "账号", "账号ID"),
    "product_ref": ("product_ref", "product_id", "product", "商品", "商品ID"),
    "parent_external_video_id": (
        "parent_external_video_id",
        "parent_video_id",
        "parent",
        "父视频ID",
    ),
    "variation_note": ("variation_note", "variation", "裂变说明"),
}


def export_interchange_json(snapshot: WorkspaceSnapshot) -> str:
    payload = {
        "schema": INTERCHANGE_SCHEMA,
        "workspace_ref": snapshot.id,
        "videos": export_interchange_records(snapshot),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def export_interchange_csv(snapshot: WorkspaceSnapshot) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(FIELDS))
    writer.writeheader()
    for record in export_interchange_records(snapshot):
        record = {**record, "account_refs": json.dumps(record["account_refs"], ensure_ascii=False)}
        writer.writerow({key: _csv_cell(value) for key, value in record.items()})
    return output.getvalue()


def export_interchange_records(snapshot: WorkspaceSnapshot) -> list[dict[str, Any]]:
    videos = {item.video.id: item.video for item in snapshot.videos}
    return [_export_video(item.video, videos) for item in snapshot.videos]


def _export_video(video: Video, videos: dict[str, Video]) -> dict[str, Any]:
    parent = videos.get(video.parent_video_id or "")
    parent_ref = _external_id(parent) if parent else video.parent_video_id
    brief = video.contexts[-1].brief if video.contexts else video.goal
    return {
        "external_video_id": _external_id(video),
        "code": video.code,
        "title": video.title,
        "goal": video.goal,
        "brief": brief,
        "account_refs": video.account_ids,
        "product_ref": video.product_id,
        "parent_external_video_id": parent_ref,
        "variation_note": video.variation_note,
    }


def _external_id(video: Video | None) -> str | None:
    return (video.external_video_id or video.id) if video else None


def preview_import(
    snapshot: WorkspaceSnapshot,
    *,
    data_format: str,
    payload: str,
    mapping: dict[str, str],
) -> dict[str, Any]:
    records = _parse_records(data_format, payload)
    detected_fields = _detected_fields(records)
    resolved_mapping = _resolve_mapping(detected_fields, mapping)
    normalized = [_normalize(record, resolved_mapping) for record in records]
    payload_ids = {item["external_video_id"] for item in normalized if item["external_video_id"]}
    identities = video_identity_map(snapshot)
    seen: set[str] = set()
    rows = [
        _preview_row(snapshot, item, index, identities, payload_ids, seen)
        for index, item in enumerate(normalized, start=1)
    ]
    counts = {
        status: sum(row["status"] == status for row in rows)
        for status in ("ready", "conflict", "invalid")
    }
    return {
        "schema": INTERCHANGE_SCHEMA,
        "format": data_format,
        "detected_fields": detected_fields,
        "mapping": resolved_mapping,
        "rows": rows,
        "summary": {
            "total": len(rows),
            **counts,
            "missing_references": sum(
                any(bool(value) for value in row["missing_references"].values())
                for row in rows
            ),
        },
    }


def video_identity_map(snapshot: WorkspaceSnapshot) -> dict[str, str]:
    result: dict[str, str] = {}
    for view in snapshot.videos:
        result[view.video.id] = view.video.id
        if view.video.external_video_id:
            result[view.video.external_video_id] = view.video.id
    return result


def commit_import(
    service: VideoOperationsService,
    preview: dict[str, Any],
) -> dict[str, Any]:
    identities = video_identity_map(service.snapshot())
    skipped = [row for row in preview["rows"] if row["status"] != "ready"]
    pending = [row for row in preview["rows"] if row["status"] == "ready"]
    created = []
    while pending:
        ready, deferred = _parents_ready(pending, identities)
        if not ready:
            skipped.extend(_unresolved_rows(deferred))
            break
        for row in ready:
            video = _create_imported_video(service, row, identities)
            identities[row["normalized"]["external_video_id"]] = video.id
            created.append(video)
        pending = deferred
    summary = {**preview["summary"], "created": len(created), "skipped": len(skipped)}
    return {"created": created, "skipped": skipped, "summary": summary}


def _parents_ready(
    rows: list[dict[str, Any]],
    identities: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ready = []
    deferred = []
    for row in rows:
        parent_ref = row["normalized"]["parent_external_video_id"]
        (ready if not parent_ref or parent_ref in identities else deferred).append(row)
    return ready, deferred


def _unresolved_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "status": "invalid",
            "errors": [*row["errors"], "父视频在本次导入中无法建立"],
        }
        for row in rows
    ]


def _create_imported_video(
    service: VideoOperationsService,
    row: dict[str, Any],
    identities: dict[str, str],
) -> Video:
    item = row["normalized"]
    parent_ref = item["parent_external_video_id"]
    return service.create_video(
        title=item["title"],
        goal=item["goal"],
        account_ids=item["account_refs"],
        product_id=item["product_ref"] or None,
        brief=item["brief"] or item["goal"],
        sources=[{
            "kind": "import",
            "label": f"导入数据第 {row['row_number']} 行",
            "content": f"外部视频 ID：{item['external_video_id']}",
            "href": None,
            "file_name": None,
        }],
        parent_video_id=identities.get(parent_ref),
        variation_note=item["variation_note"] or None,
        external_video_id=item["external_video_id"],
    )


def _parse_records(data_format: str, payload: str) -> list[dict[str, Any]]:
    rows = _csv_records(payload) if data_format == "csv" else _json_records(payload)
    if not rows:
        raise ApplicationError("empty_import", "导入文件里没有可识别的数据行。")
    if any(not isinstance(row, Mapping) for row in rows):
        raise ApplicationError("invalid_import", "每条导入记录都必须是字段对象。")
    result = [dict(row) for row in rows]
    if result and "video" in result[0] and "external_video_id" not in result[0]:
        raise ApplicationError(
            "invalid_import",
            "完整工作区备份不是可回灌清单，请使用‘导出可回灌 JSON’。",
        )
    return result


def _csv_cell(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return "" if value is None else value
    return f"'{value}" if FORMULA_CELL.match(value) or value.startswith("'") else value


def _restore_csv_cell(value: str | None) -> str | None:
    if value and value.startswith("'") and (
        value[1:].startswith("'") or FORMULA_CELL.match(value[1:])
    ):
        return value[1:]
    return value


def _csv_records(payload: str) -> list[dict[str, Any]]:
    rows = csv.DictReader(io.StringIO(payload.lstrip("\ufeff")))
    return [
        {key: _restore_csv_cell(value) for key, value in row.items()}
        for row in rows
    ]


def _json_records(payload: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ApplicationError("invalid_import", f"JSON 无法解析：{exc.msg}。") from exc
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        records = parsed.get("videos", parsed.get("records"))
        if isinstance(records, list):
            return records
    raise ApplicationError("invalid_import", "JSON 必须是数组，或包含 videos/records 数组。")


def _detected_fields(records: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(key for record in records[:20] for key in record))


def _resolve_mapping(detected: list[str], requested: dict[str, str]) -> dict[str, str]:
    canonical_requested = {_canonical_field(key): value for key, value in requested.items()}
    unknown = set(canonical_requested) - set(FIELDS)
    if unknown:
        names = "、".join(sorted(unknown))
        raise ApplicationError("invalid_mapping", f"不支持映射到这些字段：{names}。")
    result = dict(canonical_requested)
    for canonical in FIELDS:
        if canonical not in result:
            result[canonical] = next(
                (name for name in ALIASES[canonical] if name in detected),
                "",
            )
    return {key: value for key, value in result.items() if value}


def _canonical_field(field: str) -> str:
    for canonical, aliases in ALIASES.items():
        if field == canonical or field in aliases:
            return canonical
    return field


def _normalize(record: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    value = {
        field: _field_string(field, record.get(source))
        for field, source in mapping.items()
    }
    account_source = mapping.get("account_refs", "")
    value["account_refs"] = _account_refs(record.get(account_source))
    for field in FIELDS:
        value.setdefault(field, [] if field == "account_refs" else "")
    return value


def _field_string(field: str, value: Any) -> str:
    if field == "variation_note":
        return "" if value is None else str(value)
    return _string(value)


def _preview_row(
    snapshot: WorkspaceSnapshot,
    normalized: dict[str, Any],
    row_number: int,
    identities: dict[str, str],
    payload_ids: set[str],
    seen: set[str],
) -> dict[str, Any]:
    external_id = normalized["external_video_id"]
    missing = _missing_references(snapshot, normalized, identities, payload_ids)
    errors = _validation_errors(normalized, missing)
    conflicts = []
    if external_id in identities:
        conflicts.append("该外部视频 ID 已导入")
    if external_id and external_id in seen:
        conflicts.append("清单内外部视频 ID 重复")
    if external_id:
        seen.add(external_id)
    status = "invalid" if errors else ("conflict" if conflicts else "ready")
    return {
        "row_number": row_number,
        "status": status,
        "normalized": normalized,
        "missing_references": missing,
        "errors": errors,
        "conflicts": conflicts,
    }


def _missing_references(
    snapshot: WorkspaceSnapshot,
    normalized: dict[str, Any],
    identities: dict[str, str],
    payload_ids: set[str],
) -> dict[str, Any]:
    account_ids = {item.id for item in snapshot.accounts}
    missing_accounts = [item for item in normalized["account_refs"] if item not in account_ids]
    product_ref = normalized["product_ref"]
    product_ids = {item.id for item in snapshot.products}
    missing_product = product_ref if product_ref and product_ref not in product_ids else ""
    parent_ref = normalized["parent_external_video_id"]
    parent_known = not parent_ref or parent_ref in identities or parent_ref in payload_ids
    return {
        "account_refs": missing_accounts,
        "product_ref": missing_product,
        "parent_external_video_id": "" if parent_known else parent_ref,
    }


def _validation_errors(normalized: dict[str, Any], missing: dict[str, Any]) -> list[str]:
    errors = []
    required = {
        "external_video_id": "缺少稳定外部视频 ID",
        "title": "缺少视频名称",
        "goal": "缺少本次目标",
    }
    errors.extend(message for field, message in required.items() if not normalized[field])
    if len(normalized["title"]) > 100:
        errors.append("视频名称不能超过 100 个字符")
    if normalized["parent_external_video_id"] == normalized["external_video_id"]:
        errors.append("父视频不能指向自己")
    if missing["account_refs"]:
        errors.append(f"账号引用不存在：{'、'.join(missing['account_refs'])}")
    if missing["product_ref"]:
        errors.append(f"商品引用不存在：{missing['product_ref']}")
    if missing["parent_external_video_id"]:
        errors.append(f"父视频引用不存在：{missing['parent_external_video_id']}")
    return errors


def _account_refs(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _string(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
    return [item.strip() for item in re.split(r"[,;|，；]", text) if item.strip()]


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()
