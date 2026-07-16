"""数据回流故事线：曲线可复现、快照节流、种子版本化、表现提炼进裂变。"""

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from video_ops.adapters.mock_platform import MockPlatformAdapter, _profile_for
from video_ops.adapters.sqlite_repo import SQLiteRepository
from video_ops.application.seed import seed_demo
from video_ops.application.service import VideoOperationsService
from video_ops.domain.models import AccountGroup, MetricSnapshot

APP_ROOT = Path(__file__).parents[1]
SEED_PATH = APP_ROOT / "data" / "sample" / "workspace-seed.json"
PUBLISHED = datetime(2026, 7, 10, 2, 0, tzinfo=UTC)


def _adapter_at(hours: float) -> MockPlatformAdapter:
    moment = PUBLISHED + timedelta(hours=hours)
    return MockPlatformAdapter(clock=lambda: moment)


def _find_external_id(profile_name: str) -> str:
    for index in range(300):
        candidate = f"story-{index}"
        if _profile_for(candidate).name == profile_name:
            return candidate
    raise AssertionError(f"没有找到 {profile_name} 档位的外部编号")


def _metric_series(external_id: str, checkpoints: list[float]) -> list[MetricSnapshot]:
    previous = None
    rows = []
    for hours in checkpoints:
        previous = _adapter_at(hours).collect_metrics("publication-x", external_id, previous)
        rows.append(previous)
    return rows


def test_mock_metric_curve_is_reproducible_for_same_publication() -> None:
    checkpoints = [6.0, 30.0, 90.0]

    def run() -> list[tuple]:
        return [
            (item.views, item.orders, item.revenue, item.likes)
            for item in _metric_series("sample-video-hero-1", checkpoints)
        ]

    assert run() == run()


def test_mock_profiles_split_hit_and_flop_roughly_two_six_two() -> None:
    hit = _profile_for(_find_external_id("爆款"))
    flop = _profile_for(_find_external_id("扑街"))
    assert hit.plateau_views > flop.plateau_views * 10

    names = [_profile_for(f"dist-{index}").name for index in range(400)]
    assert 0.1 < names.count("爆款") / len(names) < 0.3
    assert 0.1 < names.count("扑街") / len(names) < 0.3
    assert 0.4 < names.count("普通") / len(names) < 0.8


def test_mock_story_grows_then_plateaus_and_orders_never_decrease() -> None:
    external_id = _find_external_id("爆款")
    rows = _metric_series(external_id, [2, 10, 24, 48, 96, 240, 720])
    views = [item.views for item in rows]
    orders = [item.orders for item in rows]

    assert views == sorted(views)
    assert orders == sorted(orders)
    assert views[-1] > views[0] > 0
    # 平台期：尾段增幅远小于中段爬升
    assert views[-1] - views[-2] < views[3] - views[2]
    # 订单来自转化链路，收入等于订单乘以 19.9–49.9 的哈希单价
    final = rows[-1]
    assert final.orders > 0
    assert 19.9 <= final.revenue / final.orders <= 49.9
    # 爆款平台期高于扑街平台期
    flop_final = _metric_series(_find_external_id("扑街"), [720])[-1]
    assert final.views > flop_final.views


def test_metric_snapshots_are_throttled_to_thirty_minutes(service, repository) -> None:
    publication = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop"],
        scheduled_at=None,
    )[0]
    first = service.sync_publication(publication.id)
    second = service.sync_publication(publication.id)
    assert len(first.metrics) == len(second.metrics) == 1

    backdated = (datetime.now(UTC) - timedelta(minutes=31)).isoformat()
    with repository.transaction() as connection:
        connection.execute(
            "UPDATE metrics SET captured_at = ? WHERE publication_id = ?",
            (backdated, publication.id),
        )
    third = service.sync_publication(publication.id)
    assert len(third.metrics) == 2


def test_seeded_metric_history_survives_new_syncs(service: VideoOperationsService) -> None:
    hero = next(item.video for item in service.snapshot().videos if item.video.id == "video-hero")
    publication = next(item for item in hero.publications if item.metrics)
    seeded_views = [item.views for item in publication.metrics]

    synced = service.sync_publication(publication.id)

    assert [item.views for item in synced.metrics[: len(seeded_views)]] == seeded_views
    assert len(synced.metrics) == len(seeded_views) + 1
    assert (synced.metrics[-1].views or 0) >= max(seeded_views)
    assert (synced.metrics[-1].orders or 0) >= 34


def _write_seed(path: Path, payload: dict) -> Path:
    # 种子会按相对路径读取样例素材，复制到临时目录保持结构一致。
    for name in ("video-brief.txt", "existing-script.md"):
        shutil.copy2(SEED_PATH.parent / name, path.parent / name)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _marker_group() -> AccountGroup:
    return AccountGroup(id="group-marker", name="重建探针", sort_order=99)


def test_seed_same_version_skips_and_new_version_backs_up_then_rebuilds(tmp_path) -> None:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    payload["version"] = 1
    seed_v1 = _write_seed(tmp_path / "seed-v1.json", payload)
    repo = SQLiteRepository(tmp_path / "demo.db")
    seed_demo(repo, seed_v1)
    repo.add_group(_marker_group())

    seed_demo(repo, seed_v1)  # 版本一致：跳过重建
    assert any(item.id == "group-marker" for item in repo.snapshot().account_groups)
    assert not (tmp_path / "demo.db.bak").exists()

    payload["version"] = 2
    seed_v2 = _write_seed(tmp_path / "seed-v2.json", payload)
    seed_demo(repo, seed_v2)  # 版本升级：备份旧库并重建
    assert (tmp_path / "demo.db.bak").exists()
    assert all(item.id != "group-marker" for item in repo.snapshot().account_groups)


def test_legacy_database_without_seed_version_is_rebuilt(tmp_path) -> None:
    repo = SQLiteRepository(tmp_path / "demo.db")
    seed_demo(repo, SEED_PATH)
    repo.add_group(_marker_group())
    with repo.transaction() as connection:
        connection.execute("UPDATE workspace SET seed_version = NULL")

    seed_demo(repo, SEED_PATH)

    assert (tmp_path / "demo.db.bak").exists()
    assert all(item.id != "group-marker" for item in repo.snapshot().account_groups)


def test_seed_v2_curated_artifacts_and_batch_note_land_verbatim(tmp_path) -> None:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    payload["version"] = 9
    payload["batches"][0]["note"] = "本批只测场景变量"
    hero = next(item for item in payload["videos"] if item["key"] == "hero")
    hero["script"] = {"content": "第一行钩子\n第二行证明", "note": "手工打磨 v1"}
    hero["storyboard"] = {
        "shots": [
            {
                "order": 1,
                "duration_seconds": 3,
                "visual": "特写榨汁杯",
                "voiceover": "第一行钩子",
                "on_screen_text": "钩子",
                "role": "hook",
            },
            {
                "order": 2,
                "duration_seconds": 5,
                "visual": "中景操作",
                "voiceover": "第二行证明",
                "role": "proof",
            },
        ],
        "note": "手工分镜 v1",
    }
    repo = SQLiteRepository(tmp_path / "demo.db")
    seed_demo(repo, _write_seed(tmp_path / "seed.json", payload))
    snapshot = repo.snapshot()

    video = next(item.video for item in snapshot.videos if item.video.id == "video-hero")
    assert video.scripts[0].content == "第一行钩子\n第二行证明"
    assert video.scripts[0].note == "手工打磨 v1"
    assert [shot.role for shot in video.storyboards[0].shots] == ["hook", "proof"]
    assert video.storyboards[0].note == "手工分镜 v1"
    batch = next(item for item in snapshot.batches if item.id == "batch-hero")
    assert batch.note == "本批只测场景变量"
    # 缺席字段仍走原生成路径
    other = next(item.video for item in snapshot.videos if item.video.id == "video-organizer")
    assert other.scripts[0].note == "演示工作区自带版本"


def test_performance_brief_summarizes_best_publication(repository: SQLiteRepository) -> None:
    snapshot = repository.snapshot()
    hero = next(item for item in snapshot.videos if item.video.id == "video-hero")

    brief = hero.performance_brief
    assert brief is not None
    assert "最佳发布播放 18.6万" in brief
    assert "订单 34 单" in brief
    assert "订单/播放口径" in brief
    assert "全工作台中位数的" in brief and "倍" in brief
    assert "能不能只换场景再测试一版" in brief

    unpublished = next(item for item in snapshot.videos if item.video.id == "video-organizer")
    assert unpublished.performance_brief is None


def test_branch_context_carries_performance_brief_before_parent_metrics(
    service: VideoOperationsService,
) -> None:
    child = service.branch_video(
        "video-hero",
        variation="只换场景再测一版",
        comment_ids=[],
    )

    sources = child.contexts[0].sources
    kinds = [item.kind for item in sources]
    assert "performance_brief" in kinds
    assert kinds.index("performance_brief") < kinds.index("parent_metric")
    brief_source = sources[kinds.index("performance_brief")]
    assert brief_source.label == "表现提炼"
    assert "最佳发布播放" in brief_source.content
