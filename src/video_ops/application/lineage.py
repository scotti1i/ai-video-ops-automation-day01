"""裂变只引用父视频产物，不复制或覆盖父产物。"""

from __future__ import annotations

import json

from video_ops.domain.models import CommentSnapshot, Video


def build_lineage_sources(
    parent: Video,
    comment_ids: list[str],
    *,
    performance_brief: str | None = None,
) -> list[dict]:
    sources = [
        source(
            "lineage",
            f"父视频 {parent.code}",
            parent.goal,
        )
    ]
    sources.extend(parent_context_sources(parent))
    sources.extend(parent_artifact_sources(parent))
    # 表现提炼放在父数据 JSON 之前：先给结论，再给原始数字。
    if performance_brief:
        sources.append(source("performance_brief", "表现提炼", performance_brief))
    sources.extend(parent_metric_sources(parent))
    comments = [
        comment
        for publication in parent.publications
        for comment in publication.comments
        if comment.id in comment_ids
    ]
    sources.extend(comment_sources(comments))
    return sources


def parent_context_sources(parent: Video) -> list[dict]:
    sources: list[dict] = []
    for context in parent.contexts:
        sources.append(source("parent_context", f"父 Context v{context.version}", context.brief))
        sources.extend(
            source(
                "parent_context_source",
                f"继承 · {item.label}",
                item.content,
                href=item.href,
                file_name=item.file_name,
            )
            for item in context.sources
        )
    return sources


def parent_artifact_sources(parent: Video) -> list[dict]:
    sources: list[dict] = []
    if parent.scripts:
        script = parent.scripts[-1]
        sources.append(source("parent_script", f"父脚本 v{script.version}", script.content))
    if parent.storyboards:
        board = parent.storyboards[-1]
        content = json.dumps(
            [shot.model_dump() for shot in board.shots],
            ensure_ascii=False,
        )
        sources.append(source("parent_storyboard", f"父分镜 v{board.version}", content))
    sources.extend(
        source(
            "parent_media",
            f"父成片 · {media.file_name}",
            f"checksum={media.checksum}",
            file_name=media.file_name,
        )
        for media in parent.media
    )
    return sources


def parent_metric_sources(parent: Video) -> list[dict]:
    sources: list[dict] = []
    for index, publication in enumerate(parent.publications, start=1):
        metric = publication.metrics[-1] if publication.metrics else None
        summary = {
            "status": publication.status,
            "captured_at": metric.captured_at if metric else None,
            "views": metric.views if metric else None,
            "orders": metric.orders if metric else None,
            "revenue": metric.revenue if metric else None,
        }
        sources.append(
            source(
                "parent_metric",
                f"父数据 · 发布 {index}",
                json.dumps(summary, ensure_ascii=False),
            )
        )
    return sources


def comment_sources(comments: list[CommentSnapshot]) -> list[dict]:
    return [
        source("comment", "选中评论", comment.content)
        for comment in comments
    ]


def source(
    kind: str,
    label: str,
    content: str,
    *,
    href: str | None = None,
    file_name: str | None = None,
) -> dict:
    return {
        "kind": kind,
        "label": label,
        "content": content,
        "href": href,
        "file_name": file_name,
    }
