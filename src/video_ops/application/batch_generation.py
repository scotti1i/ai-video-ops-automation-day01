"""带货脚本候选：先比较和选稿，再原子地创建正式视频。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit

from video_ops.application.errors import ApplicationError
from video_ops.application.identifiers import new_id
from video_ops.application.lineage import build_lineage_sources
from video_ops.domain.commerce_copy import candidate_title
from video_ops.domain.models import (
    ArtifactSource,
    Batch,
    ContextSnapshot,
    ContextSource,
    Product,
    ScriptArtifact,
    ScriptCandidate,
    ScriptQuality,
    ScriptSettings,
    StoryboardArtifact,
    StoryboardShot,
    Video,
    WorkspaceSnapshot,
)
from video_ops.domain.ports import (
    CandidateVersionConflict,
    ClosedClaimTemplateProducer,
    ScriptProducer,
    WorkspaceRepository,
)
from video_ops.domain.script_quality import (
    INDEPENDENT_AUDIT_MARKER,
    ClaimAuditMode,
    evaluate_quality,
)
from video_ops.domain.script_quality import (
    normalized_text as _normalized,
)


@dataclass(frozen=True)
class Angle:
    label: str
    direction: str
    hypothesis: str


@dataclass(frozen=True)
class BatchSpec:
    position: int
    title: str
    angle: Angle
    primary_selling_point: str


@dataclass(frozen=True)
class CommerceBrief:
    product_id: str | None
    product_title: str
    description: str
    selling_points: tuple[str, ...]
    primary_selling_point: str
    audience: str
    scenario: str
    script_settings: ScriptSettings
    constraints: tuple[str, ...]
    context: str
    reference_url: str | None

    @property
    def duration_seconds(self) -> int:
        return self.script_settings.duration_seconds

    @property
    def language(self) -> str:
        return self.script_settings.language

    @property
    def allowed_claims(self) -> tuple[str, ...]:
        values = [self.description, *self.selling_points]
        return tuple(dict.fromkeys(item.strip() for item in values if item.strip()))

    def producer_context(self, spec: BatchSpec) -> str:
        payload = {
            "product_id": self.product_id,
            "product_title": self.product_title,
            "primary_selling_point": spec.primary_selling_point,
            "allowed_product_claims": [spec.primary_selling_point]
            if spec.primary_selling_point
            else [],
            "audience": self.audience,
            "scenario": self.scenario,
            "duration_seconds": self.duration_seconds,
            "language": self.language,
            "writing_tone": self.script_settings.writing_tone,
            "narrative_blocks": self.script_settings.narrative_blocks,
            "constraints": self.constraints,
            "context": self.context,
            "reference_url": self.reference_url,
            "angle": spec.angle.label,
            "hypothesis": spec.angle.hypothesis,
        }
        return "COMMERCE_BRIEF_JSON\n" + json.dumps(payload, ensure_ascii=False)


ANGLES = (
    Angle("痛点直击", "用具体麻烦开场", "具体问题比泛泛介绍更容易被识别"),
    Angle("结果先看", "结果先出现", "先看到结果能缩短理解路径"),
    Angle("一镜实测", "连续动作证明卖点", "连续证据比形容词更可信"),
    Angle("双路对比", "只改变一个变量", "单变量对比更容易看懂差异"),
    Angle("购买标准", "给出选择标准", "明确标准能帮助用户自我筛选"),
    Angle("使用场景", "场景内完成证明", "具体现场能帮助用户代入"),
    Angle("购买问答", "问题与答案同屏", "问答能承接已有购买意图"),
    Angle("连续证据", "用连续性防止误读", "连续证据能减少剪辑带来的怀疑"),
    Angle("核对清单", "逐项核对证据", "检查清单能让判断更具体"),
    Angle("异议先答", "先处理真实顾虑", "证据边界清楚更容易建立信任"),
)


class BatchService(Protocol):
    repository: WorkspaceRepository
    script_producer_factories: dict[str, Callable[[], ScriptProducer]]

    def snapshot(self) -> WorkspaceSnapshot: ...

    def create_video(self, **values) -> Video: ...


def _now() -> str:
    return datetime.now(UTC).isoformat()


def fallback_storyboard_shots(script: str) -> list[StoryboardShot]:
    """把外部 Markdown 变成可编辑分镜，不把元数据念进口播。"""
    lines = script.splitlines()
    if lines and lines[0].strip() == "---":
        end = next(
            (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
            None,
        )
        lines = lines[end + 1 :] if end is not None else lines
    chunks = [item.strip() for item in lines if item.strip() and not item.lstrip().startswith("#")]
    if len(chunks) < 2:
        clean = " ".join(chunks) or script.strip()
        midpoint = max(1, len(clean) // 2)
        chunks = [clean[:midpoint], clean[midpoint:]]
    return [
        StoryboardShot(
            order=index,
            duration_seconds=6,
            visual="按旁白匹配现有素材或补拍画面",
            voiceover=chunk,
            # 屏幕字是点题短语而非口播截断；导入稿留空，由编辑补写
            on_screen_text="",
        )
        for index, chunk in enumerate(chunks[:8], start=1)
        if chunk
    ]


def _find_product(snapshot: WorkspaceSnapshot, product_id: str | None) -> Product | None:
    if not product_id:
        return None
    product = next((item for item in snapshot.products if item.id == product_id), None)
    if product is None:
        raise ApplicationError("invalid_product", "选择的商品不存在或已经被移除。")
    return product


def _duration(brief: str) -> int:
    match = re.search(r"(?<!\d)(\d{1,2})\s*(?:秒|s\b|sec(?:onds?)?\b)", brief, re.I)
    return min(60, max(15, int(match.group(1)))) if match else 25


def _language(brief: str) -> str:
    english = re.search(r"(?:美区|美国市场|US\b|English|英文)", brief, re.I)
    return "en-US" if english else "zh-CN"


def resolve_script_settings(
    context: str,
    values: ScriptSettings | dict | None,
) -> ScriptSettings:
    if isinstance(values, ScriptSettings):
        return values
    data = values or {}
    duration = data.get("duration_seconds") or _duration(context)
    return ScriptSettings(
        language=data.get("language") or _language(context),
        writing_tone=data.get("writing_tone", "natural"),
        duration_seconds=duration,
        narrative_blocks=data.get("narrative_blocks", ["problem", "proof", "objection"]),
    )


def _audience(brief: str) -> str:
    patterns = (
        r"(?:给|面向|为)(.{2,30}?)(?:讲|推广|制作|做|看)",
        r"目标(?:用户|人群)[：:]?([^，。\n]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, brief)
        if match:
            return match.group(1).strip()
    return "目标用户"


def _scenario(brief: str) -> str:
    known = ("早上", "早晨", "早餐", "通勤", "办公室", "旅行", "厨房", "健身", "宿舍", "出门")
    found = [item for item in known if item in brief]
    return "、".join(found[:3]) if found else "日常使用现场"


def _reference_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ApplicationError("invalid_input", "参考视频只接受 http 或 https 地址。")
    return value.strip()


def _primary_point(product: Product | None, brief: str) -> str:
    if not product:
        return ""
    for point in product.selling_points:
        if point in brief:
            return point
    return product.selling_points[0] if product.selling_points else product.description


def compile_brief(
    snapshot: WorkspaceSnapshot,
    product_id: str | None,
    brief: str,
    reference_url: str | None,
    script_settings: ScriptSettings | dict | None = None,
) -> CommerceBrief:
    product = _find_product(snapshot, product_id)
    context = brief.strip() or (product.description if product else "探索一个可拍摄的短视频方向")
    primary = _primary_point(product, context)
    constraints = (
        f"商品台词只能使用本条主卖点：{primary}" if primary else "本条不写商品声明",
        "不编造价格、优惠、销量、评价、健康效果或保证性效果",
        "参考 URL 只作来源记录，未解析时不能当成内容证据",
    )
    return CommerceBrief(
        product_id=product_id,
        product_title=product.title if product else "本次内容",
        description=product.description if product else "",
        selling_points=tuple(product.selling_points if product else ()),
        primary_selling_point=primary,
        audience=_audience(context),
        scenario=_scenario(context),
        script_settings=resolve_script_settings(context, script_settings),
        constraints=constraints,
        context=context,
        reference_url=_reference_url(reference_url),
    )


def build_specs(brief: CommerceBrief, count: int) -> list[BatchSpec]:
    return [
        BatchSpec(
            position=index,
            title=candidate_title(
                brief.primary_selling_point,
                angle.label,
                product_title=brief.product_title,
                scenario=brief.scenario,
                has_product=bool(brief.product_id),
            ),
            angle=angle,
            primary_selling_point=brief.primary_selling_point,
        )
        for index, angle in enumerate(ANGLES[:count], start=1)
    ]


def _produce(
    service: BatchService,
    brief: CommerceBrief,
    spec: BatchSpec,
    producer: str,
    revision: str = "",
):
    factory = service.script_producer_factories.get(producer)
    if not factory:
        raise ApplicationError("unsupported", "当前脚本生产器不可用。")
    instruction = f"测试角度：{spec.angle.label}。{spec.angle.direction}。{revision}"
    context = brief.producer_context(spec)
    instance = factory()
    audit_mode = (
        ClaimAuditMode.CLOSED_TEMPLATE
        if isinstance(instance, ClosedClaimTemplateProducer)
        and instance.has_closed_claim_template(context)
        else ClaimAuditMode.FREE_TEXT
    )
    result = instance.produce(context, instruction)
    return result, audit_mode


def _candidate_from_result(
    batch_id: str,
    brief: CommerceBrief,
    spec: BatchSpec,
    result,
    audit_mode: ClaimAuditMode,
    candidate_id: str | None = None,
) -> ScriptCandidate:
    claims = list(dict.fromkeys(getattr(result, "claims", ()) or ()))
    quality, unsupported = evaluate_quality(brief, result.script, result.shots, claims, audit_mode)
    now = _now()
    return ScriptCandidate(
        id=candidate_id or new_id("candidate"),
        batch_id=batch_id,
        position=spec.position,
        title=spec.title,
        angle=spec.angle.label,
        hypothesis=spec.angle.hypothesis,
        script=result.script.strip(),
        shots=result.shots,
        provider=result.provider,
        claims_used=claims,
        claims_needing_evidence=unsupported,
        quality=quality,
        created_at=now,
        updated_at=now,
    )


def _revision_instruction(
    candidate: ScriptCandidate,
    spec: BatchSpec,
) -> str:
    primary = spec.primary_selling_point
    extras = [
        item
        for item in [*candidate.claims_used, *candidate.claims_needing_evidence]
        if item != INDEPENDENT_AUDIT_MARKER and _normalized(item) != _normalized(primary)
    ]
    failures = "；".join(candidate.quality.risks)
    claim_fix = ""
    if primary:
        claim_fix = f"只保留商品事实“{primary}”"
        if extras:
            claim_fix += f"，删除“{'、'.join(dict.fromkeys(extras))}”"
        claim_fix += "。"
    return f"上一版未通过：{failures}。{claim_fix}只修复这些问题并完整重写一次。"


def _generate_one(
    service: BatchService,
    batch_id: str,
    brief: CommerceBrief,
    spec: BatchSpec,
    producer: str,
    candidate_id: str | None = None,
) -> ScriptCandidate:
    result, audit_mode = _produce(service, brief, spec, producer)
    candidate = _candidate_from_result(batch_id, brief, spec, result, audit_mode, candidate_id)
    if candidate.quality.status == "ready_to_test":
        return candidate
    revision = _revision_instruction(candidate, spec)
    result, audit_mode = _produce(service, brief, spec, producer, revision)
    rewritten = _candidate_from_result(batch_id, brief, spec, result, audit_mode, candidate_id)
    return rewritten.model_copy(update={"created_at": candidate.created_at})


def generate_script_batch(
    service: BatchService,
    *,
    product_id: str | None,
    brief: str,
    reference_url: str | None,
    count: int,
    producer: str,
    script_settings: dict | None = None,
) -> tuple[Batch, list[ScriptCandidate]]:
    if count < 1 or count > len(ANGLES):
        raise ApplicationError("invalid_input", "脚本数量必须在 1 到 10 之间。")
    commerce = compile_brief(service.snapshot(), product_id, brief, reference_url, script_settings)
    batch = Batch(
        id=new_id("batch"),
        name=f"{commerce.product_title}脚本候选",
        product_id=product_id,
        brief=commerce.context,
        reference_url=commerce.reference_url,
        script_settings=commerce.script_settings,
        created_at=_now(),
    )
    service.repository.add_batch(batch)
    candidates: list[ScriptCandidate] = []
    for spec in build_specs(commerce, count):
        try:
            candidate = _generate_one(service, batch.id, commerce, spec, producer)
        except ApplicationError:
            raise
        except Exception as error:
            raise ApplicationError(
                "model_failed", f"第 {spec.position} 条脚本生成失败。", retryable=True
            ) from error
        service.repository.add_candidate(candidate)
        candidates.append(candidate)
    stored = next(item for item in service.snapshot().batches if item.id == batch.id)
    return stored, candidates


def _find_batch(service: BatchService, batch_id: str) -> Batch:
    batch = next((item for item in service.snapshot().batches if item.id == batch_id), None)
    if batch is None:
        raise ApplicationError("not_found", "没有找到这批脚本候选。")
    return batch


def _find_candidate(batch: Batch, candidate_id: str) -> ScriptCandidate:
    candidate = next((item for item in batch.candidates if item.id == candidate_id), None)
    if candidate is None:
        raise ApplicationError("not_found", "没有找到这条脚本候选。")
    return candidate


def _save_candidate_update(service: BatchService, candidate: ScriptCandidate) -> None:
    if service.repository.update_candidate(candidate):
        return
    latest_batch = _find_batch(service, candidate.batch_id)
    latest = _find_candidate(latest_batch, candidate.id)
    if latest.selected_video_id:
        raise ApplicationError("conflict", "这条候选已进入工作台，请在正式视频中继续编辑。")
    raise ApplicationError("conflict", "这条候选已发生变化，请刷新后重试。")


def edit_candidate(
    service: BatchService,
    batch_id: str,
    candidate_id: str,
    *,
    title: str | None,
    script: str,
    shots: list[StoryboardShot],
) -> ScriptCandidate:
    batch = _find_batch(service, batch_id)
    current = _find_candidate(batch, candidate_id)
    if current.selected_video_id:
        raise ApplicationError("conflict", "这条候选已进入工作台，请在正式视频中继续编辑。")
    normalized_title = title.strip() if title is not None else current.title
    if not normalized_title or len(normalized_title) > 100 or not script.strip() or not shots:
        raise ApplicationError("invalid_input", "标题、脚本或分镜不符合要求。")
    commerce = compile_brief(
        service.snapshot(),
        batch.product_id,
        batch.brief,
        batch.reference_url,
        batch.script_settings,
    )
    quality, unsupported = evaluate_quality(
        commerce,
        script.strip(),
        shots,
        current.claims_used,
        ClaimAuditMode.FREE_TEXT,
    )
    updated = current.model_copy(
        update={
            "title": normalized_title,
            "script": script.strip(),
            "shots": shots,
            "provider": "user-edit",
            "claims_needing_evidence": unsupported,
            "quality": quality,
            "updated_at": _now(),
        }
    )
    _save_candidate_update(service, updated)
    return updated


def regenerate_candidate(
    service: BatchService,
    batch_id: str,
    candidate_id: str,
    *,
    producer: str,
) -> ScriptCandidate:
    batch = _find_batch(service, batch_id)
    current = _find_candidate(batch, candidate_id)
    if current.selected_video_id:
        raise ApplicationError("conflict", "这条候选已进入工作台，不能再从候选区重写。")
    commerce = compile_brief(
        service.snapshot(),
        batch.product_id,
        batch.brief,
        batch.reference_url,
        batch.script_settings,
    )
    spec = build_specs(commerce, current.position)[-1]
    generated = _generate_one(service, batch.id, commerce, spec, producer, current.id)
    updated = generated.model_copy(
        update={"title": current.title, "created_at": current.created_at}
    )
    _save_candidate_update(service, updated)
    return updated


def _selection_sources(batch: Batch, candidate: ScriptCandidate) -> list[ContextSource]:
    values = [
        ContextSource(id=new_id("source"), kind="brief", label="这批想做什么", content=batch.brief),
        ContextSource(
            id=new_id("source"),
            kind="variation",
            label="本条测试角度",
            content=f"{candidate.angle}：{candidate.hypothesis}",
        ),
    ]
    if batch.script_settings:
        values.append(
            ContextSource(
                id=new_id("source"),
                kind="script_settings",
                label="本批创作设定",
                content=json.dumps(batch.script_settings.model_dump(), ensure_ascii=False),
            )
        )
    if batch.reference_url:
        values.append(
            ContextSource(
                id=new_id("source"),
                kind="video",
                label="参考视频",
                content="只保存来源；未接提取器，不作为商品声明证据",
                href=batch.reference_url,
            )
        )
    return values


def _artifact_source(candidate: ScriptCandidate) -> ArtifactSource:
    if candidate.provider == "user-edit":
        return ArtifactSource.USER
    return ArtifactSource.MOCK if candidate.provider.startswith("mock") else ArtifactSource.MODEL


def assess_free_artifact(
    service: BatchService,
    video: Video,
    content: str,
    shots: list[StoryboardShot],
    claimed: list[str] | None,
) -> tuple[ScriptQuality | None, list[str], list[str]]:
    previous = video.scripts[-1] if video.scripts else None
    claims = list(claimed or (previous.claims_used if previous else []))
    if not video.product_id and not (previous and previous.quality):
        return None, claims, []
    snapshot = service.snapshot()
    batch = next((item for item in snapshot.batches if item.id == video.batch_id), None)
    context = video.contexts[-1] if video.contexts else None
    brief_text = batch.brief if batch else (context.brief if context else video.goal)
    reference_url = batch.reference_url if batch else None
    brief = compile_brief(
        snapshot,
        video.product_id,
        brief_text,
        reference_url,
        batch.script_settings if batch else None,
    )
    quality, unsupported = evaluate_quality(
        brief,
        content,
        shots,
        claims,
        ClaimAuditMode.FREE_TEXT,
    )
    return quality, claims, unsupported


def _selected_video(
    batch: Batch,
    candidate: ScriptCandidate,
    video_id: str,
    now: str,
) -> Video:
    return Video(
        id=video_id,
        code="pending",
        title=candidate.title,
        goal=f"{candidate.angle}：{candidate.hypothesis}",
        account_ids=[],
        product_id=batch.product_id,
        variation_note=f"{candidate.angle}：{candidate.hypothesis}",
        batch_id=batch.id,
        created_at=now,
        updated_at=now,
    )


def _selection_artifacts(
    batch: Batch,
    candidate: ScriptCandidate,
    video_id: str,
    now: str,
) -> tuple[ContextSnapshot, ScriptArtifact, StoryboardArtifact]:
    source = _artifact_source(candidate)
    context = ContextSnapshot(
        id=new_id("context"),
        video_id=video_id,
        version=1,
        brief=batch.brief,
        sources=_selection_sources(batch, candidate),
        created_at=now,
    )
    note = f"候选 #{candidate.position} · {candidate.angle} · {candidate.provider}"
    script = ScriptArtifact(
        id=new_id("script"),
        video_id=video_id,
        version=1,
        source=source,
        content=candidate.script,
        note=note,
        quality=candidate.quality,
        claims_used=candidate.claims_used,
        claims_needing_evidence=candidate.claims_needing_evidence,
        created_at=now,
    )
    storyboard = StoryboardArtifact(
        id=new_id("storyboard"),
        video_id=video_id,
        version=1,
        source=source,
        shots=candidate.shots,
        note=note,
        created_at=now,
    )
    return context, script, storyboard


def _materialize(service: BatchService, batch: Batch, candidate: ScriptCandidate) -> str:
    now = _now()
    video_id = new_id("video")
    video = _selected_video(batch, candidate, video_id, now)
    context, script, storyboard = _selection_artifacts(batch, candidate, video_id, now)
    try:
        return service.repository.select_candidate(
            candidate.id,
            candidate.updated_at,
            video,
            context,
            script,
            storyboard,
        )
    except CandidateVersionConflict as error:
        raise ApplicationError("conflict", "这条候选刚被修改，请刷新后重新选择。") from error


def select_candidates(
    service: BatchService,
    batch_id: str,
    candidate_ids: list[str],
) -> list[Video]:
    batch = _find_batch(service, batch_id)
    unique_ids = list(dict.fromkeys(candidate_ids))
    if not unique_ids:
        raise ApplicationError("invalid_input", "请至少选择一条脚本候选。")
    candidates = [_find_candidate(batch, item) for item in unique_ids]
    video_ids = [_materialize(service, batch, item) for item in candidates]
    snapshot = service.snapshot()
    views = {item.video.id: item.video for item in snapshot.videos}
    return [views[item] for item in video_ids]


def save_video_title(service: BatchService, video_id: str, title: str) -> Video:
    current = next((item for item in service.snapshot().videos if item.video.id == video_id), None)
    if current is None:
        raise ApplicationError("not_found", "没有找到这条视频。")
    normalized = title.strip()
    if not normalized or len(normalized) > 100:
        raise ApplicationError("invalid_input", "视频标题不能为空且不能超过 100 个字符。")
    if normalized == current.video.title:
        return current.video
    service.repository.update_video_title(video_id, normalized, _now())
    return next(item.video for item in service.snapshot().videos if item.video.id == video_id)


def create_variation_batch(
    service: BatchService,
    video_id: str,
    *,
    name: str,
    variations: list[str],
) -> Batch:
    parent = next((item for item in service.snapshot().videos if item.video.id == video_id), None)
    if parent is None:
        raise ApplicationError("not_found", "没有找到这条视频。")
    normalized = [item.strip() for item in variations if item.strip()]
    if not name.strip() or not normalized:
        raise ApplicationError("invalid_input", "批次名称和至少一个变化方向不能为空。")
    batch = Batch(id=new_id("batch"), name=name.strip(), created_at=_now())
    service.repository.add_batch(batch)
    children = []
    for variation in normalized:
        suffix = f" · {variation[:24]}"
        children.append(
            service.create_video(
                title=f"{parent.video.title[: 100 - len(suffix)]}{suffix}",
                goal=variation,
                account_ids=parent.video.account_ids,
                product_id=parent.video.product_id,
                brief=f"批量裂变自 {parent.video.code}：{variation}",
                sources=build_lineage_sources(parent.video, []),
                parent_video_id=parent.video.id,
                variation_note=variation,
                batch_id=batch.id,
            )
        )
    return batch.model_copy(update={"video_ids": [item.id for item in children]})
