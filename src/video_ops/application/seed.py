"""把紧凑样例目录展开为完整的可操作工作空间。

种子契约 v2：根部 "version" 声明版本；video 条目可带 "script"/"storyboard"
直接入库为 v1 产物，batches 条目可带 "note"。字段缺席时回退现有生成路径，
无 version 字段的旧种子按版本 1 处理。
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from video_ops.adapters.script_producers import MockScriptProducer
from video_ops.adapters.sqlite_repo import SQLiteRepository
from video_ops.application.batch_generation import fallback_storyboard_shots
from video_ops.domain.models import (
    Account,
    AccountGroup,
    ArtifactSource,
    Batch,
    CommentSnapshot,
    ContextSnapshot,
    ContextSource,
    MediaArtifact,
    MetricSnapshot,
    Product,
    Publication,
    PublicationOrigin,
    PublicationStatus,
    ScriptArtifact,
    StoryboardArtifact,
    StoryboardShot,
    Video,
)

LOGGER = logging.getLogger(__name__)


def load_seed(path: Path) -> dict:
    seed = json.loads(path.read_text(encoding="utf-8"))
    required = {"workspace", "account_groups", "accounts", "products", "videos", "batches"}
    missing = required - seed.keys()
    if missing:
        raise ValueError(f"样例数据缺少字段: {', '.join(sorted(missing))}")
    return seed


def seed_demo(repository: SQLiteRepository, path: Path, *, force: bool = False) -> None:
    repository.initialize()
    seed = load_seed(path)
    version = int(seed.get("version") or 1)
    if force:
        repository.reset()
    elif repository.snapshot().videos:
        # 库无版本记录（None）视为过期，同样触发备份重建。
        if repository.seed_version() == version:
            return
        _backup_stale_database(repository.path, version)
        repository.reset()
    _seed_workspace(repository, seed)
    parent_map: dict[str, str] = {}
    for index, item in enumerate(seed["videos"], start=1):
        video = _seed_video(repository, path.parent, item, index, parent_map)
        parent_map[item["key"]] = video.id
    repository.set_seed_version(version)


def _backup_stale_database(path: Path, version: int) -> None:
    """种子版本变化时把旧库备份成 <name>.bak，旧演示数据可回看。"""
    if not path.exists():
        return
    backup = path.with_name(f"{path.name}.bak")
    shutil.copy2(path, backup)
    backup.chmod(0o600)
    LOGGER.info("样例种子已升级到 v%s：旧库备份到 %s 后重建", version, backup)


def _seed_workspace(repository: SQLiteRepository, seed: dict) -> None:
    workspace = seed["workspace"]
    repository.configure_workspace(
        workspace_id=workspace["id"],
        name=workspace["name"],
        mode=workspace["mode"],
        traffic_threshold=workspace["traffic_threshold"],
        order_threshold=workspace["order_threshold"],
    )
    for item in seed["account_groups"]:
        repository.add_group(AccountGroup(**item))
    for item in seed["accounts"]:
        repository.add_account(Account(**item))
    for item in seed["products"]:
        repository.add_product(Product(**item))
    for item in seed["batches"]:
        repository.add_batch(Batch(**item, video_ids=[]))


def _seed_video(
    repository: SQLiteRepository,
    sample_dir: Path,
    item: dict,
    index: int,
    parent_map: dict[str, str],
) -> Video:
    video_id = f"video-{item['key']}"
    valid_states = {
        "needs_script",
        "needs_media",
        "ready",
        "failed",
        "scheduled",
        "published_wait",
        "published_high",
        "published_youtube",
        "published_multi",
    }
    if item["state"] not in valid_states:
        raise ValueError(f"未知样例状态: {item['state']}")
    parent_id = parent_map.get(item.get("parent_key", ""))
    video = Video(
        id=video_id,
        code=f"VID-{index:03d}",
        title=item["title"],
        goal=item["goal"],
        account_ids=item["account_ids"],
        product_id=item.get("product_id"),
        parent_video_id=parent_id,
        variation_note=item.get("variation"),
        batch_id=item.get("batch"),
        created_at=item["created_at"],
        updated_at=item["created_at"],
    )
    repository.add_video(video)
    repository.add_context(_context_for(video, sample_dir, item))
    if item["state"] == "needs_script":
        return video
    _seed_artifacts(repository, video, sample_dir, item)
    if item["state"] == "needs_media":
        return video
    repository.add_media(_media_for(video))
    if item["state"] == "ready":
        return video
    _seed_publications(repository, video, item["state"])
    return video


def _context_for(video: Video, sample_dir: Path, item: dict) -> ContextSnapshot:
    sources = [
        ContextSource(
            id=f"source-{item['key']}-brief",
            kind="text",
            label="本次目标",
            content=item["goal"],
        )
    ]
    if item["key"] == "hero":
        for name in ["video-brief.txt", "existing-script.md"]:
            sources.append(
                ContextSource(
                    id=f"source-hero-{name}",
                    kind="file",
                    label=name,
                    content=(sample_dir / name).read_text(encoding="utf-8"),
                    file_name=name,
                )
            )
    if video.parent_video_id:
        sources.append(
            ContextSource(
                id=f"source-{item['key']}-parent",
                kind="lineage",
                label="父视频",
                content=f"继承自 {video.parent_video_id}；本轮变化：{item.get('variation', '')}",
            )
        )
    return ContextSnapshot(
        id=f"context-{item['key']}-v1",
        video_id=video.id,
        version=1,
        brief=item["goal"],
        sources=sources,
        created_at=video.created_at,
    )


def _seed_artifacts(
    repository: SQLiteRepository,
    video: Video,
    sample_dir: Path,
    item: dict,
) -> None:
    source, note, content, shots = _default_artifact_plan(sample_dir, item)
    # 种子契约 v2：条目自带 script/storyboard 时逐字入库，缺席回退生成路径。
    script_spec = item.get("script") or {}
    storyboard_spec = item.get("storyboard") or {}
    if script_spec.get("content"):
        content = str(script_spec["content"])
        shots = fallback_storyboard_shots(content)
    if storyboard_spec.get("shots"):
        shots = [StoryboardShot(**shot) for shot in storyboard_spec["shots"]]
    script = ScriptArtifact(
        id=f"script-{item['key']}-v1",
        video_id=video.id,
        version=1,
        source=source,
        content=content,
        note=script_spec.get("note") or note,
        created_at=video.created_at,
    )
    storyboard = StoryboardArtifact(
        id=f"storyboard-{item['key']}-v1",
        video_id=video.id,
        version=1,
        source=source,
        shots=shots,
        note=storyboard_spec.get("note") or note,
        created_at=video.created_at,
    )
    repository.add_artifact_pair(script, storyboard)


def _default_artifact_plan(sample_dir: Path, item: dict) -> tuple[ArtifactSource, str, str, list]:
    """种子未提供产物时的回退：MockScriptProducer 或导入样例文件。"""
    if item["key"] == "import-script":
        content = (sample_dir / "existing-script.md").read_text(encoding="utf-8")
        return (
            ArtifactSource.IMPORT,
            "导入已有脚本",
            content,
            fallback_storyboard_shots(content),
        )
    plan = MockScriptProducer().produce(item["goal"], item["goal"])
    return ArtifactSource.MOCK, "演示工作区自带版本", plan.script, plan.shots


def _media_for(video: Video) -> MediaArtifact:
    key = video.id.removeprefix("video-")
    return MediaArtifact(
        id=f"media-{key}",
        video_id=video.id,
        file_name=f"{video.code.lower()}-final.mp4",
        mime_type="video/mp4",
        size_bytes=18_400_000 + len(key) * 160_000,
        checksum=f"sample-{key}-sha256",
        storage_path=f"sample://media/{key}.mp4",
        source=ArtifactSource.EXTERNAL,
        status="ready",
        created_at=video.created_at,
    )


def _seed_publications(repository: SQLiteRepository, video: Video, state: str) -> None:
    for index, account_id in enumerate(video.account_ids, start=1):
        publication = _publication_for(video, account_id, state, index)
        repository.add_publication(publication)
        if publication.status != PublicationStatus.SUCCEEDED:
            continue
        for metric in _metrics_for(publication, state, index):
            repository.add_metric(metric)
        for comment in _comments_for(publication, state, index):
            repository.upsert_comment(comment)


def _publication_for(video: Video, account_id: str, state: str, index: int) -> Publication:
    created = datetime.fromisoformat(video.created_at)
    status = PublicationStatus.SUCCEEDED
    error = None
    scheduled_at = None
    if state == "failed":
        status = PublicationStatus.FAILED
        error = "演示账号连接已失效；重新连接后可重试。"
    elif state == "scheduled":
        status = PublicationStatus.SCHEDULED
        scheduled_at = (datetime.now(UTC) + timedelta(days=4)).isoformat()
    external_id = None if status != PublicationStatus.SUCCEEDED else f"sample-{video.id}-{index}"
    return Publication(
        id=f"publication-{video.id}-{index}",
        video_id=video.id,
        account_id=account_id,
        status=status,
        origin=PublicationOrigin.SAMPLE,
        scheduled_at=scheduled_at,
        published_at=(created + timedelta(hours=2)).isoformat() if external_id else None,
        external_id=external_id,
        url=f"https://example.invalid/videos/{external_id}" if external_id else None,
        error=error,
        warnings=["演示数据，不代表真实平台结果"],
        raw_ref=f"sample://publications/{external_id}" if external_id else None,
        idempotency_key=f"sample-key-{video.id}-{account_id}",
        created_at=video.created_at,
        updated_at=video.created_at,
    )


def _metrics_for(publication: Publication, state: str, index: int) -> list[MetricSnapshot]:
    if state == "published_wait":
        return []
    captured = datetime.fromisoformat(publication.created_at) + timedelta(hours=8)
    if state == "published_high" and index == 1:
        values = [(68_200, 9, 269.1), (186_420, 34, 1_016.6)]
    elif state == "published_multi" and index == 1:
        values = [(129_800, 25, 747.5)]
    else:
        values = [(8_420 + index * 2_100, 0, 0.0)]
    return [
        MetricSnapshot(
            id=f"metric-{publication.id}-{position}",
            publication_id=publication.id,
            captured_at=(captured + timedelta(hours=position * 16)).isoformat(),
            views=views,
            likes=max(18, views // 48),
            comments=max(2, views // 1400),
            shares=max(1, views // 2600),
            orders=orders if index == 1 else None,
            revenue=revenue if index == 1 else None,
            raw={"sample": True, "snapshot": position + 1},
        )
        for position, (views, orders, revenue) in enumerate(values)
    ]


# 每条视频有自己的观众声音，避免全工作台复用同一对评论穿帮
_COMMENT_POOLS: dict[str, list[tuple[str, str, str, int]]] = {
    "hero": [
        ("a", "Mia", "能不能只换场景再测试一版？想看办公室版。", 37),
        ("b", "Jordan", "前两秒直接给结果会不会更好？", 21),
    ],
    "youtube-review": [
        ("a", "Sofia", "刀头那一圈到底好不好冲？想看个特写。", 18),
        ("b", "Leo", "用两周之后，杯口的胶圈会不会藏色？", 9),
    ],
    "multi-account": [
        ("a", "Ken", "线是藏住了，插头那一坨怎么办？", 26),
        ("b", "Amber", "求链接，我工位就是视频开头那样。", 14),
    ],
}


def _comments_for(publication: Publication, state: str, index: int) -> list[CommentSnapshot]:
    if state not in {"published_high", "published_youtube", "published_multi"} or index != 1:
        return []
    captured = datetime.fromisoformat(publication.created_at) + timedelta(hours=10)
    key = publication.video_id.removeprefix("video-")
    values = _COMMENT_POOLS.get(key, _COMMENT_POOLS["hero"])
    return [
        CommentSnapshot(
            id=f"comment-{publication.id}-{suffix}",
            publication_id=publication.id,
            external_id=f"sample-comment-{suffix}",
            author=author,
            content=content,
            likes=likes,
            commented_at=captured.isoformat(),
            captured_at=captured.isoformat(),
            raw={"sample": True},
        )
        for suffix, author, content, likes in values
    ]
