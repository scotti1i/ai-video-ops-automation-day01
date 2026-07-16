import ast
import json
import sqlite3
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from video_ops.adapters import read_model
from video_ops.adapters.script_producers import MockScriptProducer, OpenAIScriptProducer
from video_ops.adapters.sqlite_repo import SQLiteRepository
from video_ops.api.schemas import GenerateBatchRequest
from video_ops.application.batch_generation import (
    edit_candidate,
    regenerate_candidate,
    select_candidates,
)
from video_ops.domain.models import (
    MetricSnapshot,
    Product,
    Publication,
    PublicationStatus,
    StoryboardShot,
    Video,
    VideoStage,
)
from video_ops.domain.script_quality import risk_claims
from video_ops.domain.states import performance_summary, stage_summary

BLENDER_BRIEF = "为每天早上赶时间的上班族推广便携榨汁杯，重点讲随行杯直接饮用，目标 25 秒，美区英文"


def test_application_service_depends_on_domain_ports_not_adapters() -> None:
    source = Path("src/video_ops/application/service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not {name for name in imports if name.startswith("video_ops.adapters")}


def _publication(
    publication_id: str,
    *,
    views: int,
    orders: int,
) -> Publication:
    metric = MetricSnapshot(
        id=f"metric-{publication_id}",
        publication_id=publication_id,
        captured_at="2026-07-14T08:00:00+00:00",
        views=views,
        orders=orders,
    )
    return Publication(
        id=publication_id,
        video_id="video-test",
        account_id=f"account-{publication_id}",
        status=PublicationStatus.SUCCEEDED,
        external_id=f"external-{publication_id}",
        idempotency_key=f"key-{publication_id}",
        created_at="2026-07-14T07:00:00+00:00",
        updated_at="2026-07-14T08:00:00+00:00",
        metrics=[metric],
    )


def test_seed_builds_full_workspace_and_computes_each_stage_once(
    repository: SQLiteRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = read_model.stage_summary
    calls: list[str] = []

    def counted(video: Video):
        calls.append(video.id)
        return original(video)

    monkeypatch.setattr(read_model, "stage_summary", counted)
    snapshot = repository.snapshot()

    assert stat.S_IMODE(repository.path.stat().st_mode) == 0o600
    assert len(snapshot.videos) == 12
    assert len(snapshot.accounts) == 4
    assert len(snapshot.products) == 3
    assert len(calls) == len(snapshot.videos)
    assert len(set(calls)) == len(snapshot.videos)
    assert {item.video.id for item in snapshot.videos} >= {
        "video-hero",
        "video-import-script",
    }
    batch = next(item for item in snapshot.batches if item.id == "batch-hero")
    assert set(batch.video_ids) == {"video-child-scene", "video-child-hook"}


def test_performance_keeps_traffic_and_orders_as_independent_video_peaks() -> None:
    traffic_only = _publication("traffic", views=220_000, orders=0)
    order_only = _publication("orders", views=8_000, orders=31)
    video = Video(
        id="video-test",
        code="VID-999",
        title="发布级表现",
        goal="不跨账号拼接结论",
        account_ids=["account-traffic", "account-orders"],
        created_at="2026-07-14T07:00:00+00:00",
        updated_at="2026-07-14T08:00:00+00:00",
        publications=[traffic_only, order_only],
    )

    summary = performance_summary(video, traffic_threshold=100_000, order_threshold=20)

    assert summary.label == "流量成交双高"
    assert summary.source_publication_id is None
    assert summary.best_views == 220_000
    assert summary.best_orders == 31


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (
            [PublicationStatus.SUCCEEDED, PublicationStatus.UNKNOWN],
            VideoStage.NEEDS_RECONCILIATION,
        ),
        (
            [PublicationStatus.SCHEDULED, PublicationStatus.UNKNOWN],
            VideoStage.NEEDS_RECONCILIATION,
        ),
        (
            [PublicationStatus.FAILED, PublicationStatus.UNKNOWN],
            VideoStage.NEEDS_RECONCILIATION,
        ),
        (
            [PublicationStatus.SUCCEEDED, PublicationStatus.FAILED],
            VideoStage.PUBLISH_FAILED,
        ),
        (
            [PublicationStatus.SCHEDULED, PublicationStatus.FAILED],
            VideoStage.PUBLISH_FAILED,
        ),
        (
            [PublicationStatus.SUCCEEDED, PublicationStatus.PUBLISHING],
            VideoStage.PUBLISHING,
        ),
        (
            [PublicationStatus.SCHEDULED, PublicationStatus.PUBLISHING],
            VideoStage.PUBLISHING,
        ),
        (
            [PublicationStatus.SUCCEEDED, PublicationStatus.DRAFT],
            VideoStage.READY_TO_PUBLISH,
        ),
        (
            [PublicationStatus.SUCCEEDED, PublicationStatus.SCHEDULED],
            VideoStage.SCHEDULED,
        ),
    ],
)
def test_mixed_publications_keep_the_most_actionable_stage(
    repository: SQLiteRepository,
    statuses: list[PublicationStatus],
    expected: VideoStage,
) -> None:
    video = next(
        item.video for item in repository.snapshot().videos if item.video.id == "video-hero"
    )
    base = video.publications[0]
    publications = [
        base.model_copy(update={"id": f"publication-mixed-{index}", "status": status})
        for index, status in enumerate(statuses)
    ]

    summary = stage_summary(video.model_copy(update={"publications": publications}))

    assert summary.stage == expected


def test_database_rejects_duplicate_external_id_per_account(
    repository: SQLiteRepository,
) -> None:
    snapshot = repository.snapshot()
    hero = next(item.video for item in snapshot.videos if item.video.id == "video-hero")
    existing = next(item for item in hero.publications if item.account_id == "account-mock-shop")
    duplicate = existing.model_copy(
        update={
            "id": "publication-duplicate",
            "video_id": "video-organizer",
            "idempotency_key": "duplicate-idempotency-key",
        }
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.add_publication(duplicate)


def test_existing_database_migrates_stable_external_video_id(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE videos (
                id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                goal TEXT NOT NULL, product_id TEXT, parent_video_id TEXT,
                variation_note TEXT, batch_id TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    repository = SQLiteRepository(path)
    repository.initialize()
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(videos)")}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(videos)")}
    assert "external_video_id" in columns
    assert "videos_external_id_idx" in indexes


def test_existing_database_migrates_publication_lease_columns(tmp_path: Path) -> None:
    path = tmp_path / "legacy-publications.db"
    repository = SQLiteRepository(path)
    repository.initialize()
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE publications DROP COLUMN claim_token")
        connection.execute("ALTER TABLE publications DROP COLUMN lease_expires_at")

    repository.initialize()

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(publications)")}
    assert {"claim_token", "lease_expires_at"} <= columns


def test_existing_database_migrates_script_candidate_columns(tmp_path: Path) -> None:
    path = tmp_path / "legacy-candidates.db"
    repository = SQLiteRepository(path)
    repository.initialize()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE script_candidates")
        connection.execute("ALTER TABLE scripts DROP COLUMN quality_json")
        connection.execute("ALTER TABLE scripts DROP COLUMN claims_used_json")
        connection.execute("ALTER TABLE scripts DROP COLUMN claims_needing_evidence_json")
        connection.execute("ALTER TABLE batches DROP COLUMN reference_url")
        connection.execute("ALTER TABLE batches DROP COLUMN brief")
        connection.execute("ALTER TABLE batches DROP COLUMN product_id")
        connection.execute("ALTER TABLE batches DROP COLUMN script_settings_json")
        connection.execute(
            "INSERT INTO batches (id, name, created_at) VALUES ('legacy-batch', 'legacy', 'now')"
        )

    repository.initialize()

    with sqlite3.connect(path) as connection:
        batch_columns = {row[1] for row in connection.execute("PRAGMA table_info(batches)")}
        script_columns = {row[1] for row in connection.execute("PRAGMA table_info(scripts)")}
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {"product_id", "brief", "reference_url", "script_settings_json"} <= batch_columns
    assert {
        "quality_json",
        "claims_used_json",
        "claims_needing_evidence_json",
    } <= script_columns
    assert "script_candidates" in tables
    legacy = next(item for item in repository.snapshot().batches if item.id == "legacy-batch")
    assert legacy.script_settings is None


def _risky_shots() -> list[StoryboardShot]:
    return [
        StoryboardShot(
            order=1,
            duration_seconds=20,
            role="hook",
            visual="只有人物口播，没有商品演示",
            voiceover="This is guaranteed best.",
        )
    ]


def test_formal_script_keeps_quality_and_claims_across_every_new_version(service) -> None:
    batch, candidates = service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF,
        reference_url=None,
        count=1,
        producer="mock",
    )
    original = candidates[0]
    risky_shots = _risky_shots()
    risky = edit_candidate(
        service,
        batch.id,
        original.id,
        title=None,
        script="This is guaranteed best.",
        shots=risky_shots,
    )
    video = select_candidates(service, batch.id, [risky.id])[0]

    formal = next(item.video for item in service.snapshot().videos if item.video.id == video.id)
    selected_script = formal.scripts[-1]
    assert selected_script.quality == risky.quality
    assert selected_script.claims_used == risky.claims_used
    assert selected_script.claims_needing_evidence == risky.claims_needing_evidence

    edited = service.update_artifacts(
        video.id,
        risky.script,
        [item.model_dump() for item in risky.shots],
        "正式脚本编辑",
    )
    imported = service.import_artifacts(
        video.id,
        script=original.script,
        shots=[item.model_dump() for item in original.shots],
    )
    generated = service.generate_artifacts(video.id, instruction="重写开头", producer="mock")

    for version in (edited.scripts[-1], imported.scripts[-1], generated.scripts[-1]):
        assert version.quality is not None
        assert version.quality.status == "needs_revision"
        assert "自由文本尚未完成独立声明审计" in "；".join(version.quality.risks)
        assert version.claims_used == risky.claims_used


def test_unknown_product_mechanism_is_conservatively_unverified(service) -> None:
    service.repository.add_product(
        Product(
            id="product-unknown",
            title="未知商品",
            description="只有原始资料",
            selling_points=["磁吸折叠结构"],
        )
    )

    _, candidates = service.generate_batch(
        product_id="product-unknown",
        brief="面向通勤用户推广未知商品，重点讲磁吸折叠结构，25 秒，美区英文",
        reference_url=None,
        count=1,
        producer="mock",
    )

    assert candidates[0].quality.status == "needs_revision"
    assert "自由文本尚未完成独立声明审计" in "；".join(candidates[0].quality.risks)
    assert candidates[0].claims_needing_evidence == ["商品声明需独立核对"]


def test_english_risk_words_require_full_word_boundaries() -> None:
    assert risk_claims("a healthy morning routine by the freezer", ()) == []
    assert risk_claims("this can heal you", ()) == ["heal"]
    assert risk_claims("a guaranteed treatment", ()) == ["treatment", "guaranteed"]


def test_openai_prompt_budgets_first_two_shots_inside_six_seconds() -> None:
    instructions = OpenAIScriptProducer._instructions()

    assert "第一镜必须是 hook 且不超过 3 秒" in instructions
    assert "第二镜必须是 value" in instructions
    assert "前两镜累计不超过 6 秒" in instructions
    assert "只允许使用primary_selling_point" in instructions


def test_missing_model_claims_are_not_silently_filled(service) -> None:
    class MissingClaimsProducer:
        def produce(self, context: str, instruction: str):
            plan = MockScriptProducer().produce(context, instruction)
            values = dict(plan.__dict__)
            values["claims"] = ()
            return SimpleNamespace(**values)

    service.script_producer_factories["missing-claims"] = MissingClaimsProducer
    _, candidates = service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF,
        reference_url=None,
        count=1,
        producer="missing-claims",
    )

    assert candidates[0].claims_used == []
    assert candidates[0].quality.status == "needs_revision"
    claims_check = next(item for item in candidates[0].quality.checks if item.key == "claims")
    assert not claims_check.passed


def test_provider_string_cannot_spoof_closed_claim_audit(service) -> None:
    class SpoofedMockProducer:
        def produce(self, context: str, instruction: str):
            return MockScriptProducer().produce(context, instruction)

    service.script_producer_factories["spoofed-mock"] = SpoofedMockProducer
    _, candidates = service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF,
        reference_url=None,
        count=1,
        producer="spoofed-mock",
    )

    candidate = candidates[0]
    claims_check = next(item for item in candidate.quality.checks if item.key == "claims")
    assert candidate.provider == "mock"
    assert candidate.quality.status == "needs_revision"
    assert claims_check.detail == "自由文本尚未完成独立声明审计"
    assert candidate.claims_needing_evidence == ["商品声明需独立核对"]


def test_script_settings_persist_and_drive_rewrite_edit_and_selection(service) -> None:
    settings = {
        "language": "zh-CN",
        "writing_tone": "direct",
        "duration_seconds": 20,
        "narrative_blocks": ["proof", "objection", "problem"],
    }
    batch, candidates = service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF.replace("25", "30"),
        reference_url=None,
        count=1,
        producer="mock",
        script_settings=settings,
    )
    restarted = SQLiteRepository(service.repository.path).snapshot()
    stored = next(item for item in restarted.batches if item.id == batch.id)

    assert stored.script_settings is not None
    assert stored.script_settings.model_dump() == settings
    assert [item.role for item in candidates[0].shots] == [
        "hook",
        "value",
        "proof",
        "objection",
        "problem",
        "cta",
    ]
    assert "查看事实，再判断是否适合。" in candidates[0].script

    rewritten = regenerate_candidate(service, batch.id, candidates[0].id, producer="mock")
    assert [item.role for item in rewritten.shots][2:5] == settings["narrative_blocks"]
    long_shots = list(rewritten.shots)
    long_shots[-1] = long_shots[-1].model_copy(
        update={"duration_seconds": long_shots[-1].duration_seconds + 8}
    )
    edited = edit_candidate(
        service,
        batch.id,
        rewritten.id,
        title=None,
        script=rewritten.script,
        shots=long_shots,
    )
    duration_check = next(item for item in edited.quality.checks if item.key == "duration")
    assert not duration_check.passed
    assert duration_check.detail.startswith("目标 20 秒")

    video = select_candidates(service, batch.id, [edited.id])[0]
    source = next(item for item in video.contexts[0].sources if item.kind == "script_settings")
    assert json.loads(source.content) == settings


def test_auto_duration_follows_context_before_persisting_resolved_snapshot(service) -> None:
    batch, _ = service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF.replace("25 秒", "20 秒"),
        reference_url=None,
        count=1,
        producer="mock",
        script_settings={
            "language": None,
            "writing_tone": "natural",
            "duration_seconds": None,
            "narrative_blocks": ["problem", "proof", "objection"],
        },
    )

    assert batch.script_settings is not None
    assert batch.script_settings.duration_seconds == 20
    assert batch.script_settings.language == "en-US"


def test_all_exposed_script_settings_keep_supported_mock_angles_ready(service) -> None:
    tone_endings = {
        "natural": ("", ""),
        "direct": ("Check the facts", "查看事实"),
        "warm": ("See if it feels right", "看看商品详情"),
        "expert": ("Inspect the evidence", "核对证据"),
    }
    for language in ("en-US", "zh-CN"):
        for duration in (20, 25, 30):
            for tone, markers in tone_endings.items():
                _, candidates = service.generate_batch(
                    product_id="product-blender",
                    brief=BLENDER_BRIEF,
                    reference_url=None,
                    count=10,
                    producer="mock",
                    script_settings={
                        "language": language,
                        "writing_tone": tone,
                        "duration_seconds": duration,
                        "narrative_blocks": ["problem", "proof", "objection"],
                    },
                )
                failed = [
                    item.angle
                    for item in candidates
                    if item.quality.status != "ready_to_test"
                ]
                assert failed == [], (language, duration, tone, failed)
                assert all(
                    abs(sum(shot.duration_seconds for shot in item.shots) - duration) <= 2
                    for item in candidates
                )
                marker = markers[0 if language == "en-US" else 1]
                if marker:
                    assert all(marker in item.shots[-1].voiceover for item in candidates)


def test_script_settings_request_and_openai_instruction_are_strict() -> None:
    automatic = GenerateBatchRequest(script_settings={"duration_seconds": None})
    assert automatic.script_settings is not None
    assert automatic.script_settings.duration_seconds is None
    request = GenerateBatchRequest(
        script_settings={
            "language": None,
            "writing_tone": "warm",
            "duration_seconds": 30,
            "narrative_blocks": ["proof", "problem", "objection"],
        }
    )
    assert request.script_settings is not None
    assert request.script_settings.language is None
    with pytest.raises(ValidationError):
        GenerateBatchRequest(
            script_settings={
                "duration_seconds": 25,
                "narrative_blocks": ["proof", "proof", "objection"],
            }
        )

    context = "COMMERCE_BRIEF_JSON\n" + json.dumps(
        {
            "language": "en-US",
            "writing_tone": "warm",
            "narrative_blocks": ["proof", "problem", "objection"],
        }
    )
    instructions = OpenAIScriptProducer._instructions(context)
    assert "[hook,value,proof,problem,objection,cta]" in instructions
    assert "必须使用 en-US" in instructions
    assert "表达方式严格遵循 warm" in instructions
