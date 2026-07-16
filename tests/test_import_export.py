import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from video_ops.adapters.sqlite_repo import SQLiteRepository
from video_ops.api.app import _commit_workspace_import
from video_ops.api.importer import (
    export_interchange_csv,
    export_interchange_json,
    preview_import,
)
from video_ops.api.schemas import WorkspaceImportRequest
from video_ops.application.errors import ApplicationError
from video_ops.application.seed import seed_demo
from video_ops.application.service import VideoOperationsService

SEED_PATH = Path(__file__).parents[1] / "data/sample/workspace-seed.json"


def _request(service: VideoOperationsService):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(service=service)))


def _payload() -> str:
    return json.dumps(
        [
            {
                "external_video_id": "video-hero",
                "title": "早上五分钟的榨汁难题",
                "goal": "不应覆盖已有视频",
            },
            {
                "external_video_id": "external-new-1",
                "title": "早上五分钟的榨汁难题",
                "goal": "同名但不同外部 ID 应建立新记录",
            },
        ],
        ensure_ascii=False,
    )


def _target_service(path: Path) -> VideoOperationsService:
    repository = SQLiteRepository(path)
    seed_demo(repository, SEED_PATH)
    return VideoOperationsService(repository)


def _source_video(service: VideoOperationsService):
    return service.create_video(
        title="导出回灌的裂变视频",
        goal="验证稳定外部 ID 和父子关系",
        account_ids=["account-mock-shop"],
        product_id="product-blender",
        brief="这段 Context 必须通过 JSON/CSV 回灌",
        sources=[],
        parent_video_id="video-hero",
        variation_note="只换开场人物",
    )


def test_import_preview_uses_external_id_not_title_without_mutation(
    service: VideoOperationsService,
) -> None:
    before = service.snapshot()
    preview = preview_import(before, data_format="json", payload=_payload(), mapping={})
    assert [row["status"] for row in preview["rows"]] == ["conflict", "ready"]
    assert service.snapshot() == before


def test_import_commit_skips_existing_and_is_idempotent(
    service: VideoOperationsService,
) -> None:
    original = next(
        item.video for item in service.snapshot().videos if item.video.id == "video-hero"
    )
    body = WorkspaceImportRequest(format="json", payload=_payload())
    first = asyncio.run(_commit_workspace_import(body, _request(service)))
    second = asyncio.run(_commit_workspace_import(body, _request(service)))

    assert len(first["created"]) == 1
    assert len(first["skipped"]) == 1
    assert not second["created"]
    unchanged = next(
        item.video for item in service.snapshot().videos if item.video.id == original.id
    )
    assert unchanged.scripts == original.scripts
    assert unchanged.storyboards == original.storyboards
    assert unchanged.publications == original.publications


@pytest.mark.parametrize("data_format", ["json", "csv"])
def test_export_preview_commit_roundtrip_is_idempotent(
    service: VideoOperationsService,
    tmp_path: Path,
    data_format: str,
) -> None:
    source = _source_video(service)
    payload = (
        export_interchange_json(service.snapshot())
        if data_format == "json"
        else export_interchange_csv(service.snapshot())
    )
    target = _target_service(tmp_path / f"target-{data_format}.db")
    body = WorkspaceImportRequest(format=data_format, payload=payload)
    preview = preview_import(
        target.snapshot(), data_format=data_format, payload=payload, mapping={}
    )
    assert preview["summary"] == {
        "total": 13,
        "ready": 1,
        "conflict": 12,
        "invalid": 0,
        "missing_references": 0,
    }
    first = asyncio.run(_commit_workspace_import(body, _request(target)))
    imported = first["created"][0]
    assert imported.external_video_id == source.id
    assert imported.parent_video_id == "video-hero"
    assert imported.account_ids == ["account-mock-shop"]
    assert imported.product_id == "product-blender"
    assert imported.contexts[-1].brief == "这段 Context 必须通过 JSON/CSV 回灌"

    target.import_artifacts(imported.id, script="已有脚本版本")
    target.import_publication(
        imported.id,
        "account-mock-shop",
        f"platform-{data_format}",
        f"https://example.invalid/{data_format}",
        "2026-07-15T00:00:00+00:00",
    )
    before_repeat = next(
        item.video for item in target.snapshot().videos if item.video.id == imported.id
    )
    second = asyncio.run(_commit_workspace_import(body, _request(target)))
    after_repeat = next(
        item.video for item in target.snapshot().videos if item.video.id == imported.id
    )
    assert not second["created"]
    assert after_repeat.scripts == before_repeat.scripts
    assert after_repeat.storyboards == before_repeat.storyboards
    assert after_repeat.publications == before_repeat.publications


def test_preview_reports_missing_references(service: VideoOperationsService) -> None:
    payload = json.dumps([{
        "external_video_id": "external-missing-refs",
        "title": "引用缺失",
        "goal": "预览报告不存在的维度",
        "account_refs": ["account-missing"],
        "product_ref": "product-missing",
        "parent_external_video_id": "video-missing",
    }])
    row = preview_import(
        service.snapshot(), data_format="json", payload=payload, mapping={}
    )["rows"][0]
    assert row["status"] == "invalid"
    assert row["missing_references"] == {
        "account_refs": ["account-missing"],
        "product_ref": "product-missing",
        "parent_external_video_id": "video-missing",
    }


def test_preview_rejects_title_that_youtube_cannot_publish(
    service: VideoOperationsService,
) -> None:
    payload = json.dumps([{
        "external_video_id": "external-long-title",
        "title": "长" * 101,
        "goal": "导入前发现不可恢复的标题错误",
    }])

    row = preview_import(
        service.snapshot(), data_format="json", payload=payload, mapping={}
    )["rows"][0]

    assert row["status"] == "invalid"
    assert "视频名称不能超过 100 个字符" in row["errors"]


def test_csv_export_blocks_formulas_without_breaking_roundtrip(
    service: VideoOperationsService,
) -> None:
    video = service.create_video(
        title="=HYPERLINK(\"https://example.invalid\")",
        goal="+SUM(1,1)",
        account_ids=[],
        product_id=None,
        brief="",
        sources=[],
    )
    payload = export_interchange_csv(service.snapshot())

    assert "'=HYPERLINK" in payload
    row = next(
        item for item in preview_import(
            service.snapshot(), data_format="csv", payload=payload, mapping={}
        )["rows"]
        if item["normalized"]["external_video_id"] == video.id
    )
    assert row["normalized"]["title"] == video.title
    assert row["normalized"]["goal"] == video.goal


@pytest.mark.parametrize(
    ("prefix", "operator"),
    [(" ", "="), ("\t", "+"), ("\r", "-"), ("\n", "@")],
)
def test_csv_formula_guard_handles_leading_whitespace_reversibly(
    service: VideoOperationsService,
    prefix: str,
    operator: str,
) -> None:
    variation = f"{prefix}{operator}1+1"
    video = service.create_video(
        title="CSV 安全回灌",
        goal="保留原始裂变说明",
        account_ids=[],
        product_id=None,
        brief="",
        sources=[],
        variation_note=variation,
    )

    payload = export_interchange_csv(service.snapshot())
    assert f"'{variation}" in payload
    row = next(
        item for item in preview_import(
            service.snapshot(), data_format="csv", payload=payload, mapping={}
        )["rows"]
        if item["normalized"]["external_video_id"] == video.id
    )
    assert row["normalized"]["variation_note"] == variation


@pytest.mark.parametrize("variation", ["'=1+1", "'人工标记"])
def test_csv_formula_guard_preserves_original_leading_apostrophe(
    service: VideoOperationsService,
    variation: str,
) -> None:
    video = service.create_video(
        title="CSV 原始引号回灌",
        goal="区分安全前缀与用户原文",
        account_ids=[],
        product_id=None,
        brief="",
        sources=[],
        variation_note=variation,
    )

    payload = export_interchange_csv(service.snapshot())
    row = next(
        item for item in preview_import(
            service.snapshot(), data_format="csv", payload=payload, mapping={}
        )["rows"]
        if item["normalized"]["external_video_id"] == video.id
    )
    assert row["normalized"]["variation_note"] == variation


def test_import_resolves_parent_later_in_the_same_file(
    service: VideoOperationsService,
) -> None:
    payload = json.dumps([
        {
            "external_video_id": "external-child",
            "title": "子视频",
            "goal": "保留裂变说明",
            "parent_external_video_id": "external-parent",
            "variation_note": "换场景",
        },
        {
            "external_video_id": "external-parent",
            "title": "父视频",
            "goal": "先建立父记录",
        },
    ])
    body = WorkspaceImportRequest(format="json", payload=payload)
    result = asyncio.run(_commit_workspace_import(body, _request(service)))
    videos = {item.video.external_video_id: item.video for item in service.snapshot().videos}
    assert len(result["created"]) == 2
    assert videos["external-child"].parent_video_id == videos["external-parent"].id
    assert videos["external-child"].variation_note == "换场景"


def test_workspace_backup_is_not_misrepresented_as_importable(
    service: VideoOperationsService,
) -> None:
    payload = service.snapshot().model_dump_json()
    with pytest.raises(ApplicationError, match="完整工作区备份"):
        preview_import(service.snapshot(), data_format="json", payload=payload, mapping={})
