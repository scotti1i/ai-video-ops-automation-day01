"""把规范化表组装成一个只读工作空间快照。"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from statistics import median

from video_ops.domain.models import (
    Account,
    AccountGroup,
    Batch,
    CommentSnapshot,
    ContextSnapshot,
    MediaArtifact,
    MetricSnapshot,
    Product,
    Publication,
    ScriptArtifact,
    ScriptCandidate,
    StoryboardArtifact,
    Video,
    VideoView,
    WorkspaceSnapshot,
)
from video_ops.domain.states import (
    best_publication_metric,
    performance_brief,
    performance_summary,
    stage_summary,
)


def _rows(connection: sqlite3.Connection, query: str, params: tuple = ()):
    return connection.execute(query, params).fetchall()


def _json(value: str):
    return json.loads(value)


def _metrics(connection: sqlite3.Connection) -> dict[str, list[MetricSnapshot]]:
    result: dict[str, list[MetricSnapshot]] = defaultdict(list)
    for row in _rows(connection, "SELECT * FROM metrics ORDER BY captured_at"):
        data = dict(row)
        data["raw"] = _json(data.pop("raw_json"))
        result[row["publication_id"]].append(MetricSnapshot(**data))
    return result


def _comments(connection: sqlite3.Connection) -> dict[str, list[CommentSnapshot]]:
    result: dict[str, list[CommentSnapshot]] = defaultdict(list)
    for row in _rows(connection, "SELECT * FROM comments ORDER BY commented_at DESC"):
        data = dict(row)
        data["raw"] = _json(data.pop("raw_json"))
        result[row["publication_id"]].append(CommentSnapshot(**data))
    return result


def _publications(connection: sqlite3.Connection) -> dict[str, list[Publication]]:
    metric_map = _metrics(connection)
    comment_map = _comments(connection)
    result: dict[str, list[Publication]] = defaultdict(list)
    for row in _rows(connection, "SELECT * FROM publications ORDER BY created_at"):
        data = dict(row)
        data["warnings"] = _json(data.pop("warnings_json"))
        data["metrics"] = metric_map[row["id"]]
        data["comments"] = comment_map[row["id"]]
        result[row["video_id"]].append(Publication(**data))
    return result


def _contexts(connection: sqlite3.Connection) -> dict[str, list[ContextSnapshot]]:
    result: dict[str, list[ContextSnapshot]] = defaultdict(list)
    for row in _rows(connection, "SELECT * FROM contexts ORDER BY version"):
        data = dict(row)
        data["sources"] = _json(data.pop("sources_json"))
        result[row["video_id"]].append(ContextSnapshot(**data))
    return result


def _artifacts(connection: sqlite3.Connection, table: str, model, json_field: str | None = None):
    result = defaultdict(list)
    for row in _rows(connection, f"SELECT * FROM {table} ORDER BY version"):
        data = dict(row)
        if json_field:
            data[json_field] = _json(data.pop(f"{json_field}_json"))
        if table == "scripts":
            raw_quality = data.pop("quality_json", None)
            data["quality"] = _json(raw_quality) if raw_quality else None
            data["claims_used"] = _json(data.pop("claims_used_json", "[]"))
            data["claims_needing_evidence"] = _json(data.pop("claims_needing_evidence_json", "[]"))
        result[row["video_id"]].append(model(**data))
    return result


def _candidates(connection: sqlite3.Connection) -> dict[str, list[ScriptCandidate]]:
    result: dict[str, list[ScriptCandidate]] = defaultdict(list)
    for row in _rows(connection, "SELECT * FROM script_candidates ORDER BY position"):
        data = dict(row)
        data["shots"] = _json(data.pop("shots_json"))
        data["claims_used"] = _json(data.pop("claims_used_json"))
        data["claims_needing_evidence"] = _json(data.pop("claims_needing_evidence_json"))
        data["quality"] = _json(data.pop("quality_json"))
        result[row["batch_id"]].append(ScriptCandidate(**data))
    return result


def _media(connection: sqlite3.Connection) -> dict[str, list[MediaArtifact]]:
    result: dict[str, list[MediaArtifact]] = defaultdict(list)
    for row in _rows(connection, "SELECT * FROM media ORDER BY created_at"):
        result[row["video_id"]].append(MediaArtifact(**dict(row)))
    return result


def _video_accounts(connection: sqlite3.Connection) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for row in _rows(connection, "SELECT * FROM video_accounts ORDER BY account_id"):
        result[row["video_id"]].append(row["account_id"])
    return result


def _videos(connection: sqlite3.Connection, traffic: int, orders: int) -> list[VideoView]:
    context_map = _contexts(connection)
    script_map = _artifacts(connection, "scripts", ScriptArtifact)
    board_map = _artifacts(connection, "storyboards", StoryboardArtifact, "shots")
    media_map = _media(connection)
    publication_map = _publications(connection)
    account_map = _video_accounts(connection)
    videos: list[Video] = []
    for row in _rows(connection, "SELECT * FROM videos ORDER BY created_at DESC"):
        data = dict(row)
        video_id = row["id"]
        data.update(
            account_ids=account_map[video_id],
            contexts=context_map[video_id],
            scripts=script_map[video_id],
            storyboards=board_map[video_id],
            media=media_map[video_id],
            publications=publication_map[video_id],
        )
        videos.append(Video(**data))
    best_views = _best_views(videos)
    result: list[VideoView] = []
    for video in videos:
        peer_median, peer_scope = _peer_median(video, videos, best_views)
        result.append(
            VideoView(
                video=video,
                stage=stage_summary(video),
                performance=performance_summary(video, traffic, orders),
                performance_brief=performance_brief(
                    video,
                    peer_median_views=peer_median,
                    peer_scope=peer_scope,
                ),
            )
        )
    return result


def _best_views(videos: list[Video]) -> dict[str, int]:
    """每条视频最佳发布的播放数，作为中位数对照的基础。"""
    result: dict[str, int] = {}
    for video in videos:
        best = best_publication_metric(video)
        if best and best[1].views is not None:
            result[video.id] = best[1].views
    return result


def _peer_median(
    video: Video,
    videos: list[Video],
    best_views: dict[str, int],
) -> tuple[float | None, str]:
    """表现提炼的对照组：优先同批中位数，退回全工作台，均不含自己。"""

    def views_of(group: list[Video]) -> list[int]:
        return [
            best_views[item.id] for item in group if item.id != video.id and item.id in best_views
        ]

    if video.batch_id:
        batch_peers = views_of([item for item in videos if item.batch_id == video.batch_id])
        if batch_peers:
            return median(batch_peers), "同批"
    workspace_peers = views_of(videos)
    if workspace_peers:
        return median(workspace_peers), "全工作台"
    return None, "同批"


def build_snapshot(connection: sqlite3.Connection) -> WorkspaceSnapshot:
    workspace = connection.execute("SELECT * FROM workspace LIMIT 1").fetchone()
    if workspace is None:
        raise RuntimeError("工作空间尚未初始化")
    groups = [
        AccountGroup(**dict(row))
        for row in _rows(connection, "SELECT * FROM account_groups ORDER BY sort_order")
    ]
    accounts = [
        Account(**dict(row)) for row in _rows(connection, "SELECT * FROM accounts ORDER BY name")
    ]
    products = []
    for row in _rows(connection, "SELECT * FROM products ORDER BY title"):
        data = dict(row)
        data["selling_points"] = _json(data.pop("selling_points_json"))
        products.append(Product(**data))
    candidate_map = _candidates(connection)
    batches = []
    for row in _rows(connection, "SELECT * FROM batches ORDER BY created_at DESC"):
        data = dict(row)
        raw_settings = data.pop("script_settings_json", None)
        data["script_settings"] = _json(raw_settings) if raw_settings else None
        video_rows = _rows(
            connection,
            "SELECT id FROM videos WHERE batch_id = ?",
            (row["id"],),
        )
        video_ids = [item["id"] for item in video_rows]
        batches.append(
            Batch(
                **data,
                video_ids=video_ids,
                candidates=candidate_map[row["id"]],
            )
        )
    traffic = workspace["traffic_threshold"]
    orders = workspace["order_threshold"]
    workspace_data = dict(workspace)
    workspace_data.pop("seed_version", None)  # 种子版本是内部账本，不进对外快照
    return WorkspaceSnapshot(
        **workspace_data,
        account_groups=groups,
        accounts=accounts,
        products=products,
        batches=batches,
        videos=_videos(connection, traffic, orders),
    )
