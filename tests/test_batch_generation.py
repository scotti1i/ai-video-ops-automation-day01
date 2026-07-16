import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from video_ops.adapters.mock_platform import MockPlatformAdapter
from video_ops.adapters.script_producers import (
    MockScriptProducer,
    default_script_producers,
)
from video_ops.adapters.sqlite_repo import SQLiteRepository
from video_ops.application.batch_generation import (
    edit_candidate,
    regenerate_candidate,
    select_candidates,
)
from video_ops.application.errors import ApplicationError
from video_ops.application.service import VideoOperationsService
from video_ops.domain.models import StoryboardShot

BLENDER_BRIEF = "为每天早上赶时间的上班族推广便携榨汁杯，重点讲随行杯直接饮用，目标 25 秒，美区英文"


def _generate(service: VideoOperationsService, count: int = 10):
    return service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF,
        reference_url="https://example.com/reference-video",
        count=count,
        producer="mock",
    )


def test_video_title_can_be_saved_and_touches_record(
    service: VideoOperationsService,
) -> None:
    before = service.create_video(
        title="标题保存",
        goal="验证标题更新",
        account_ids=[],
        product_id=None,
        brief="",
        sources=[],
    )

    updated = service.update_video_title(before.id, "  用户能认出的内容标题  ")

    assert updated.title == "用户能认出的内容标题"
    assert updated.updated_at != before.updated_at
    with pytest.raises(ApplicationError, match="标题不能为空"):
        service.update_video_title(before.id, "   ")


def test_generation_context_includes_product_description_and_reference_only_url(
    service: VideoOperationsService,
) -> None:
    video = service.create_video(
        title="商品完整 Context",
        goal="验证商品资料",
        account_ids=[],
        product_id="product-blender",
        brief="早晨通勤",
        sources=[],
    )

    context = service._generation_context(video)

    assert "商品描述：USB-C 充电的随行榨汁杯，杯体可拆洗。" in context
    assert "卖点：随行杯直接饮用；杯体可拆洗；USB-C 充电" in context
    assert "商品链接（仅来源引用，未解析）" in context


def test_batch_generation_creates_candidates_without_workspace_videos(
    service: VideoOperationsService,
) -> None:
    before_ids = {item.video.id for item in service.snapshot().videos}
    batch, candidates = _generate(service)
    snapshot = service.snapshot()
    stored = next(item for item in snapshot.batches if item.id == batch.id)

    assert {item.video.id for item in snapshot.videos} == before_ids
    assert stored.video_ids == []
    assert stored.product_id == "product-blender"
    assert stored.brief == BLENDER_BRIEF
    assert stored.reference_url == "https://example.com/reference-video"
    assert stored.script_settings is not None
    assert stored.script_settings.language == "en-US"
    assert stored.script_settings.duration_seconds == 25
    assert len(stored.candidates) == len(candidates) == 10
    assert len({item.title for item in candidates}) == 10
    assert len({item.angle for item in candidates}) == 10
    assert len({item.hypothesis for item in candidates}) == 10
    assert len({item.script for item in candidates}) == 10
    assert len({"\n".join(item.script.splitlines()[1:]) for item in candidates}) == 10
    assert len({item.shots[0].visual for item in candidates}) == 10
    assert len({item.shots[2].visual for item in candidates}) == 10
    assert all(
        [shot.role for shot in item.shots]
        == ["hook", "value", "problem", "proof", "objection", "cta"]
        for item in candidates
    )
    assert all(item.quality.status == "ready_to_test" for item in candidates)
    combined = "\n".join(
        text
        for item in candidates
        for shot in item.shots
        for text in (shot.voiceover, shot.visual, shot.on_screen_text)
    )
    forbidden = (
        "Context",
        "最常见顾虑",
        "核心卖点",
        "placeholder",
        "I stopped",
        "I overslept",
        "You asked",
        "有人问",
    )
    assert all(value not in combined for value in forbidden)
    assert all(len(shot.on_screen_text) <= 24 for item in candidates for shot in item.shots)


def test_key_angles_change_the_full_narrative_not_only_the_hook(
    service: VideoOperationsService,
) -> None:
    _, candidates = _generate(service)
    by_angle = {item.angle: item for item in candidates}

    assert by_angle["结果先看"].script.startswith("This smoothie never left")
    assert "Rewind one minute" in by_angle["结果先看"].script
    assert "no cuts" in by_angle["一镜实测"].script
    assert "On the left" in by_angle["双路对比"].script
    assert "On the right" in by_angle["双路对比"].script
    assert "leakproof" in by_angle["购买标准"].script
    assert "nothing more" not in by_angle["异议先答"].script
    labels = ("Problem:", "Result:", "Rewind:", "Start:", "Test it:")
    assert all(label not in item.script for item in candidates for label in labels)


def test_one_batch_is_capped_at_ten_distinct_angles(
    service: VideoOperationsService,
) -> None:
    _, candidates = _generate(service, count=10)

    assert len({item.angle for item in candidates}) == 10
    assert len({item.title for item in candidates}) == 10
    assert len({item.script for item in candidates}) == 10
    assert all("证据版" not in item.title for item in candidates)
    assert all("证据版" not in item.angle for item in candidates)
    with pytest.raises(ApplicationError) as error:
        _generate(service, count=11)
    assert error.value.code == "invalid_input"


@pytest.mark.parametrize(
    ("point", "forbidden", "expected_ready"),
    (
        ("随行杯直接饮用", ("USB-C", "dishwasher", "removable body"), True),
        ("杯体可拆洗", ("same cup", "second bottle", "USB-C", "charging port"), False),
        ("USB-C 充电", ("same cup", "second bottle", "rinse", "wash", "removable"), True),
    ),
)
def test_known_mechanisms_keep_ten_angles_claim_specific(
    service: VideoOperationsService,
    point: str,
    forbidden: tuple[str, ...],
    expected_ready: bool,
) -> None:
    _, candidates = service.generate_batch(
        product_id="product-blender",
        brief=(f"为每天早上赶时间的上班族推广便携榨汁杯，重点讲{point}，目标 25 秒，美区英文"),
        reference_url=None,
        count=10,
        producer="mock",
    )

    scripts = "\n".join(item.script for item in candidates).lower()
    assert all(
        (item.quality.status == "ready_to_test") is expected_ready for item in candidates
    )
    assert len({item.script for item in candidates}) == 10
    assert all(term.lower() not in scripts for term in forbidden)
    if not expected_ready:
        assert all(item.claims_needing_evidence == ["商品声明需独立核对"] for item in candidates)


def test_mock_script_never_leaks_internal_instruction(
    service: VideoOperationsService,
) -> None:
    _, candidates = _generate(service, count=3)
    forbidden = ("COMMERCE_BRIEF", "测试角度", "上一版未通过", "只修复这些问题")

    assert all(value not in item.script for item in candidates for value in forbidden)


def test_failed_quality_rewrites_once_with_failure_reasons(
    service: VideoOperationsService,
) -> None:
    class RewriteOnceProducer:
        def __init__(self) -> None:
            self.instructions: list[str] = []

        def produce(self, context: str, instruction: str):
            self.instructions.append(instruction)
            if len(self.instructions) == 1:
                return SimpleNamespace(
                    script="Guaranteed weight loss.",
                    shots=[
                        StoryboardShot(
                            order=1,
                            duration_seconds=20,
                            role="hook",
                            visual="只有口播",
                            voiceover="Guaranteed weight loss.",
                        )
                    ],
                    provider="rewrite-test",
                    claims=("Guaranteed weight loss",),
                )
            return MockScriptProducer().produce(context, instruction)

    producer = RewriteOnceProducer()
    service.script_producer_factories["rewrite-test"] = lambda: producer

    _, candidates = service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF,
        reference_url=None,
        count=1,
        producer="rewrite-test",
    )

    assert len(producer.instructions) == 2
    assert "上一版未通过" in producer.instructions[1]
    assert "待补证据" in producer.instructions[1]
    assert candidates[0].quality.status == "needs_revision"
    assert "自由文本尚未完成独立声明审计" in candidates[0].quality.risks


def test_rewrite_names_primary_claim_and_removes_extra_selling_points(
    service: VideoOperationsService,
) -> None:
    class MultiClaimOnceProducer:
        def __init__(self) -> None:
            self.instructions: list[str] = []

        def produce(self, context: str, instruction: str):
            self.instructions.append(instruction)
            plan = MockScriptProducer().produce(context, instruction)
            if len(self.instructions) == 1:
                values = dict(plan.__dict__)
                values["claims"] = ("随行杯直接饮用", "USB-C 充电", "杯体可拆洗")
                return SimpleNamespace(**values)
            return plan

    producer = MultiClaimOnceProducer()
    service.script_producer_factories["multi-claim"] = lambda: producer

    _, candidates = service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF,
        reference_url=None,
        count=1,
        producer="multi-claim",
    )

    revision = producer.instructions[1]
    assert "只保留商品事实“随行杯直接饮用”" in revision
    assert "删除“USB-C 充电、杯体可拆洗”" in revision
    assert candidates[0].claims_used == ["随行杯直接饮用"]


def test_model_context_exposes_only_this_candidates_primary_selling_point(
    service: VideoOperationsService,
) -> None:
    payloads: list[dict] = []

    class CapturingProducer:
        def produce(self, context: str, instruction: str):
            payloads.append(json.loads(context.removeprefix("COMMERCE_BRIEF_JSON\n")))
            return MockScriptProducer().produce(context, instruction)

    service.script_producer_factories["capture"] = CapturingProducer
    service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF,
        reference_url=None,
        count=1,
        producer="capture",
    )

    payload = payloads[0]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["allowed_product_claims"] == ["随行杯直接饮用"]
    assert "description" not in payload
    assert "selling_points" not in payload
    assert "USB-C 充电" not in serialized
    assert "杯体可拆洗" not in serialized
    assert payload["audience"] == "每天早上赶时间的上班族"
    assert "早上" in payload["scenario"]


def test_closed_claim_metadata_requires_value_and_proof_grounding(
    service: VideoOperationsService,
) -> None:
    class ForgedClaimsProducer(MockScriptProducer):
        def produce(self, context: str, instruction: str):
            plan = super().produce(context, instruction)
            lines = (
                "A rushed morning needs a simpler routine.",
                "This keeps the next step easy to follow.",
                "Show the product in one continuous shot while the routine stays clear.",
                "Keep the camera close and show each movement without a cut.",
                "Does it feel practical? The full sequence stays easy to see.",
                "Check the details and decide if it fits.",
            )
            shots = [
                item.model_copy(update={"voiceover": lines[index]})
                for index, item in enumerate(plan.shots)
            ]
            values = dict(plan.__dict__)
            values.update(script="\n".join(lines), shots=shots)
            return SimpleNamespace(**values)

    service.script_producer_factories["forged-closed"] = ForgedClaimsProducer
    _, candidates = service.generate_batch(
        product_id="product-blender",
        brief=BLENDER_BRIEF,
        reference_url=None,
        count=1,
        producer="forged-closed",
    )

    candidate = candidates[0]
    checks = {item.key: item for item in candidate.quality.checks}
    assert candidate.quality.status == "needs_revision"
    assert not checks["claims"].passed
    assert checks["claims"].detail == "卖点未同时出现在价值段与证明段口播：随行杯直接饮用"
    assert candidate.claims_needing_evidence == ["随行杯直接饮用"]


@pytest.mark.parametrize(
    "extra_claim",
    (
        "The battery lasts all week.",
        "Every piece is dishwasher-safe.",
        "The cup has a 20oz capacity.",
    ),
)
def test_editing_closed_mock_with_unreported_claims_requires_audit(
    service: VideoOperationsService,
    extra_claim: str,
) -> None:
    batch, candidates = _generate(service, count=1)
    candidate = candidates[0]
    shots = [item.model_copy() for item in candidate.shots]
    shots[2] = shots[2].model_copy(update={"voiceover": f"{shots[2].voiceover} {extra_claim}"})
    script = "\n".join(item.voiceover for item in shots)

    edited = edit_candidate(
        service,
        batch.id,
        candidate.id,
        title=None,
        script=script,
        shots=shots,
    )

    claims_check = next(item for item in edited.quality.checks if item.key == "claims")
    assert edited.quality.status == "needs_revision"
    assert claims_check.detail == "自由文本尚未完成独立声明审计"


def test_storyboard_only_performance_claim_is_included_in_claim_audit(
    service: VideoOperationsService,
) -> None:
    batch, candidates = _generate(service, count=1)
    candidate = candidates[0]
    shots = [item.model_copy() for item in candidate.shots]
    shots[2] = shots[2].model_copy(
        update={"visual": f"{shots[2].visual} Quickly finish the product action."}
    )

    edited = edit_candidate(
        service,
        batch.id,
        candidate.id,
        title=None,
        script=candidate.script,
        shots=shots,
    )

    claims_check = next(item for item in edited.quality.checks if item.key == "claims")
    assert not claims_check.passed
    assert "Quickly" in claims_check.detail
    assert "Quickly" in edited.claims_needing_evidence


def test_partial_garbage_cannot_hide_behind_valid_value_and_proof(
    service: VideoOperationsService,
) -> None:
    batch, candidates = _generate(service, count=1)
    candidate = candidates[0]
    shots = [item.model_copy() for item in candidate.shots]
    shots[0] = shots[0].model_copy(
        update={"voiceover": "Banana cloud dances under a paper moon tonight."}
    )
    shots[4] = shots[4].model_copy(
        update={"voiceover": "Purple windows whisper softly beside the silent road."}
    )

    edited = edit_candidate(
        service,
        batch.id,
        candidate.id,
        title=None,
        script="\n".join(item.voiceover for item in shots),
        shots=shots,
    )

    failed = {item.key for item in edited.quality.checks if not item.passed}
    assert {"claims", "objection"} <= failed
    assert edited.quality.status == "needs_revision"


def test_garbage_role_labels_cannot_pass_the_quality_gate(
    service: VideoOperationsService,
) -> None:
    batch, candidates = _generate(service, count=1)
    candidate = candidates[0]
    lines = ("Banana", "Cloud", "Nothing happens", "Still nothing", "No proof", "Go away")
    roles = ("hook", "value", "proof", "proof", "objection", "cta")
    durations = (3, 3, 6, 5, 5, 3)
    shots = [
        StoryboardShot(
            order=index,
            duration_seconds=durations[index - 1],
            role=roles[index - 1],
            visual="Nothing happens on an empty background",
            voiceover=lines[index - 1],
        )
        for index in range(1, 7)
    ]

    edited = edit_candidate(
        service,
        batch.id,
        candidate.id,
        title=None,
        script="\n".join(lines),
        shots=shots,
    )

    failed = {item.key for item in edited.quality.checks if not item.passed}
    assert {"hook", "value", "proof", "cta", "content"} <= failed
    assert edited.quality.status == "needs_revision"


def test_fluent_unrelated_copy_cannot_pass_with_forged_metadata(
    service: VideoOperationsService,
) -> None:
    batch, candidates = _generate(service, count=1)
    candidate = candidates[0]
    lines = (
        "Quiet rivers shape silver lanterns above the distant garden tonight.",
        "Blue notebooks follow patient windows through another ordinary afternoon.",
        "Soft shadows circle wooden tables while the hallway remains calm.",
        "Golden paper crosses open rooms beneath a slowly turning ceiling.",
        "Gentle calendars keep silent colors beside the empty doorway today.",
        "Check the purple hallway before the quiet evening closes tonight.",
    )
    roles = ("hook", "value", "proof", "proof", "objection", "cta")
    durations = (3, 3, 6, 5, 5, 3)
    shots = [
        StoryboardShot(
            order=index,
            duration_seconds=durations[index - 1],
            role=roles[index - 1],
            visual="Show a hand placing one plain object on a wooden table",
            voiceover=lines[index - 1],
        )
        for index in range(1, 7)
    ]

    edited = edit_candidate(
        service,
        batch.id,
        candidate.id,
        title=None,
        script="\n".join(lines),
        shots=shots,
    )

    checks = {item.key: item.passed for item in edited.quality.checks}
    assert checks["claims"] is False
    assert all(checks[key] for key in ("hook", "value", "proof", "cta"))
    assert checks["objection"] is False
    assert checks["content"] is False
    assert edited.quality.status == "needs_revision"


def test_producer_failure_never_falls_back_to_mock(
    service: VideoOperationsService,
) -> None:
    class BrokenProducer:
        def produce(self, _context: str, _instruction: str):
            raise RuntimeError("model unavailable")

    service.script_producer_factories["broken"] = BrokenProducer

    with pytest.raises(ApplicationError) as error:
        service.generate_batch(
            product_id="product-blender",
            brief=BLENDER_BRIEF,
            reference_url=None,
            count=1,
            producer="broken",
        )

    assert error.value.code == "model_failed"


def test_non_product_batch_has_no_fake_claim_or_placeholder(
    service: VideoOperationsService,
) -> None:
    _, candidates = service.generate_batch(
        product_id=None,
        brief="给新手讲清早晨拍摄流程，25 秒",
        reference_url=None,
        count=2,
        producer="mock",
    )

    assert all(item.claims_used == [] for item in candidates)
    assert all(item.claims_needing_evidence == [] for item in candidates)
    assert all(item.quality.status == "ready_to_test" for item in candidates)
    assert all("Context 中明确提供" not in item.script for item in candidates)
    assert all("stated product feature" not in item.script for item in candidates)
    assert all("发布后再用真实数据" not in item.script for item in candidates)


def test_edit_rechecks_unsupported_health_offer_and_english_claims(
    service: VideoOperationsService,
) -> None:
    batch, candidates = _generate(service, count=1)
    candidate = candidates[0]
    lines = [item.voiceover for item in candidate.shots]
    lines[2] = "Guaranteed weight loss in 10 seconds with 50% off."
    shots = [
        item.model_copy(update={"voiceover": lines[index]})
        for index, item in enumerate(candidate.shots)
    ]
    script = "\n".join(lines)

    edited = edit_candidate(
        service,
        batch.id,
        candidate.id,
        title=None,
        script=script,
        shots=shots,
    )

    assert edited.quality.status == "needs_revision"
    assert edited.claims_needing_evidence
    evidence = " ".join(edited.claims_needing_evidence).lower()
    assert "weight loss" in evidence
    assert "50% off" in evidence
    assert "10 seconds" in evidence


def test_select_is_idempotent_and_keeps_quality_on_formal_video(
    service: VideoOperationsService,
) -> None:
    batch, candidates = _generate(service, count=2)
    first = select_candidates(service, batch.id, [candidates[0].id])
    repeated = select_candidates(service, batch.id, [candidates[0].id])

    assert first[0].id == repeated[0].id
    assert len(service.snapshot().videos) == 13
    assert first[0].batch_id == batch.id
    assert first[0].scripts[0].quality == candidates[0].quality
    assert first[0].storyboards[0].shots == candidates[0].shots
    assert first[0].contexts[0].sources[1].kind == "variation"


def test_concurrent_select_creates_only_one_video(
    service: VideoOperationsService,
) -> None:
    batch, candidates = _generate(service, count=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: select_candidates(service, batch.id, [candidates[0].id])[0],
                range(2),
            )
        )

    assert results[0].id == results[1].id
    selected = [item.video for item in service.snapshot().videos if item.video.batch_id == batch.id]
    assert len(selected) == 1


def test_select_rolls_back_video_and_marker_when_storyboard_write_fails(
    service: VideoOperationsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch, candidates = _generate(service, count=1)
    before_ids = {item.video.id for item in service.snapshot().videos}

    def fail_storyboard(_connection, _storyboard):
        raise RuntimeError("simulated storyboard failure")

    monkeypatch.setattr(service.repository, "_insert_storyboard", fail_storyboard)
    with pytest.raises(RuntimeError, match="storyboard failure"):
        select_candidates(service, batch.id, [candidates[0].id])

    snapshot = service.snapshot()
    stored = next(item for item in snapshot.batches if item.id == batch.id)
    assert {item.video.id for item in snapshot.videos} == before_ids
    assert stored.candidates[0].selected_video_id is None


def test_selected_candidate_cannot_be_edited_or_regenerated(
    service: VideoOperationsService,
) -> None:
    batch, candidates = _generate(service, count=1)
    candidate = candidates[0]
    select_candidates(service, batch.id, [candidate.id])

    with pytest.raises(ApplicationError) as edit_error:
        edit_candidate(
            service,
            batch.id,
            candidate.id,
            title=None,
            script=candidate.script,
            shots=candidate.shots,
        )
    with pytest.raises(ApplicationError) as rewrite_error:
        regenerate_candidate(service, batch.id, candidate.id, producer="mock")

    assert edit_error.value.code == "conflict"
    assert rewrite_error.value.code == "conflict"


def test_select_wins_race_and_freezes_candidate_across_repository_instances(
    service: VideoOperationsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch, candidates = _generate(service, count=1)
    candidate = candidates[0]
    edit_reached_write = Event()
    allow_edit_write = Event()
    original_update = service.repository.update_candidate

    def delayed_update(updated):
        edit_reached_write.set()
        if not allow_edit_write.wait(timeout=5):
            raise TimeoutError("编辑请求未被释放")
        return original_update(updated)

    monkeypatch.setattr(service.repository, "update_candidate", delayed_update)
    second_repo = SQLiteRepository(service.repository.path)
    second_service = VideoOperationsService(
        second_repo,
        platform_adapters={"mock-social": MockPlatformAdapter()},
        script_producer_factories=default_script_producers(),
    )
    changed_script = candidate.script.replace("same cup", "same cup today")

    with ThreadPoolExecutor(max_workers=2) as pool:
        edit_future = pool.submit(
            edit_candidate,
            service,
            batch.id,
            candidate.id,
            title=None,
            script=changed_script,
            shots=candidate.shots,
        )
        assert edit_reached_write.wait(timeout=5)
        selected = select_candidates(second_service, batch.id, [candidate.id])
        allow_edit_write.set()
        with pytest.raises(ApplicationError) as error:
            edit_future.result(timeout=5)

    assert error.value.code == "conflict"
    stored_batch = next(item for item in second_service.snapshot().batches if item.id == batch.id)
    stored_candidate = next(item for item in stored_batch.candidates if item.id == candidate.id)
    assert stored_candidate.selected_video_id == selected[0].id
    assert stored_candidate.script == candidate.script
    assert selected[0].scripts[0].content == candidate.script


def test_edit_wins_race_and_stale_selection_rolls_back(
    service: VideoOperationsService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch, candidates = _generate(service, count=1)
    candidate = candidates[0]
    select_reached_write = Event()
    allow_select_write = Event()
    original_select = service.repository.select_candidate

    def delayed_select(*args, **kwargs):
        select_reached_write.set()
        if not allow_select_write.wait(timeout=5):
            raise TimeoutError("选择请求未被释放")
        return original_select(*args, **kwargs)

    monkeypatch.setattr(service.repository, "select_candidate", delayed_select)
    second_repo = SQLiteRepository(service.repository.path)
    second_service = VideoOperationsService(
        second_repo,
        platform_adapters={"mock-social": MockPlatformAdapter()},
        script_producer_factories=default_script_producers(),
    )
    changed_script = candidate.script.replace("same cup", "same cup today")

    with ThreadPoolExecutor(max_workers=2) as pool:
        select_future = pool.submit(select_candidates, service, batch.id, [candidate.id])
        assert select_reached_write.wait(timeout=5)
        edited = edit_candidate(
            second_service,
            batch.id,
            candidate.id,
            title=None,
            script=changed_script,
            shots=candidate.shots,
        )
        allow_select_write.set()
        with pytest.raises(ApplicationError) as error:
            select_future.result(timeout=5)

    assert error.value.code == "conflict"
    snapshot = second_service.snapshot()
    stored_batch = next(item for item in snapshot.batches if item.id == batch.id)
    stored_candidate = next(item for item in stored_batch.candidates if item.id == candidate.id)
    assert stored_candidate.selected_video_id is None
    assert stored_candidate.script == edited.script == changed_script
    assert not [item for item in snapshot.videos if item.video.batch_id == batch.id]


def test_needs_revision_candidate_can_still_be_selected(
    service: VideoOperationsService,
) -> None:
    batch, candidates = _generate(service, count=1)
    candidate = candidates[0]
    shots = [
        StoryboardShot(
            order=1,
            duration_seconds=20,
            role="hook",
            visual="只有人物口播，没有商品演示",
            voiceover="This is guaranteed best.",
        )
    ]
    edited = edit_candidate(
        service,
        batch.id,
        candidate.id,
        title=None,
        script="This is guaranteed best.",
        shots=shots,
    )

    videos = select_candidates(service, batch.id, [edited.id])

    assert edited.quality.status == "needs_revision"
    assert videos[0].scripts[0].quality.status == "needs_revision"
