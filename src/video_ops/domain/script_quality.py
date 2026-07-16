"""确定性脚本质量门：只判断是否值得测试，不预测转化。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from video_ops.domain.models import (
    ScriptQuality,
    ScriptQualityCheck,
    StoryboardShot,
)


class QualityBrief(Protocol):
    product_id: str | None
    duration_seconds: int

    @property
    def allowed_claims(self) -> tuple[str, ...]: ...


class ClaimAuditMode(StrEnum):
    CLOSED_TEMPLATE = "closed_template"
    FREE_TEXT = "free_text"


@dataclass(frozen=True)
class QualityFacts:
    unsupported: list[str]
    claims_ok: bool
    claims_detail: str
    hook_ok: bool
    value_ok: bool
    reason_ok: bool
    proof_ok: bool
    objection_ok: bool
    total_seconds: int
    consistent: bool
    cta_ok: bool
    content_ok: bool


QUALITY_RULES = (
    ("claims", "商品声明范围已核对", 10),
    ("hook", "前 3 秒有钩子", 15),
    ("value", "前 6 秒说清价值", 10),
    ("single_reason", "只保留一个购买理由", 10),
    ("proof", "画面能证明卖点", 15),
    ("objection", "回答真实购买顾虑", 10),
    ("duration", "时长符合目标", 10),
    ("consistency", "口播与完整脚本一致", 5),
    ("cta", "行动语自然且可执行", 5),
    ("content", "口播内容足够完整", 10),
)

RISK_PATTERNS = (
    re.compile(r"(?:减肥|瘦身|治疗|治愈|根治|降血糖|降血压|抗癌)"),
    # healthy 是宽泛生活方式描述，不作为医疗效果；英文风险词必须完整命中。
    re.compile(
        r"\b(?:weight\s+loss|lose\s+weight|cure[sd]?|treat(?:s|ed|ment)?|"
        r"heal(?:s|ed|ing)?|lower\s+blood\s+(?:sugar|pressure)|anti-cancer)\b",
        re.I,
    ),
    re.compile(r"(?:\$|¥|￥)\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:美元|元|折|dollars?)", re.I),
    re.compile(r"(?:限时|优惠|折扣|买一送一|免费|立减)"),
    re.compile(
        r"\b(?:limited\s+time|free|discount(?:s|ed)?|buy\s+one|get\s+one)\b|"
        r"\b\d+%\s*off\b",
        re.I,
    ),
    re.compile(r"(?:销量|已售|好评|五星|用户都说|万人推荐)"),
    re.compile(r"\b(?:\d+\s*sold|reviews?|five[- ]star|customers\s+say)\b", re.I),
    re.compile(r"(?:保证|一定|永久|百分之百|第一|最好)"),
    re.compile(r"\b(?:guarantee[ds]?|best|number\s+one)\b|(?:100%|#1)", re.I),
    re.compile(r"\b\d+\s*seconds?\b", re.I),
    re.compile(
        r"(?:Context|Brief|primary_selling_point|测试角度|上一版|占位|最常见顾虑|核心卖点)",
        re.I,
    ),
    re.compile(r"\b(?:stated\s+product\s+feature|placeholder)\b", re.I),
    re.compile(r"(?:亲测|我用了|我试过|有人问|粉丝问|评论区.{0,8}问|用了\d+天)"),
    re.compile(
        r"\b(?:I\s+(?:tried|used|tested|stopped|overslept|love)|you\s+asked|"
        r"my\s+followers\s+asked|after\s+\d+\s+days?)\b",
        re.I,
    ),
    re.compile(r"(?:轻松|快速|立刻|马上|瞬间|秒(?:完成|搞定))"),
    re.compile(r"\b(?:effortless(?:ly)?|instant(?:ly)?|quick(?:ly)?)\b", re.I),
)

CLAIM_SIGNALS = (
    (
        re.compile(r"(?:随行杯|直接饮用)"),
        re.compile(
            r"(?:同一个?杯|直接(?:喝|饮用)|不(?:用|再).{0,8}(?:倒杯|换杯|容器)|"
            r"same\s+(?:blender\s+)?cup|cup\s+you\s+drink\s+from|"
            r"no\s+second\s+(?:bottle|cup|container)|"
            r"blender\s+cup.{0,24}(?:drink|sip)|"
            r"(?:marked|original|exact)\s+cup.{0,24}(?:drink|sip))",
            re.I,
        ),
    ),
    (
        re.compile(r"(?:可拆|拆洗|拆开清洗)"),
        re.compile(
            r"(?:拆开|拆下|分开(?:冲洗|清洗)|杯体可拆|comes?\s+apart|"
            r"remov(?:e|able)|pieces?\s+apart|rinse|wash)",
            re.I,
        ),
    ),
    (
        re.compile(r"(?:USB[ -]?C|充电)", re.I),
        re.compile(r"(?:USB[ -]?C|充电|charg(?:e|es|ed|ing))", re.I),
    ),
)

INDEPENDENT_AUDIT_MARKER = "商品声明需独立核对"


def normalized_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).lower()


def _claim_is_allowed(claim: str, allowed: tuple[str, ...]) -> bool:
    value = normalized_text(claim)
    return bool(value) and any(value == normalized_text(source) for source in allowed)


def risk_claims(script: str, allowed: tuple[str, ...]) -> list[str]:
    risks: list[str] = []
    for pattern in RISK_PATTERNS:
        for match in pattern.finditer(script):
            claim = match.group(0)
            if not _claim_is_allowed(claim, allowed):
                risks.append(claim)
    return list(dict.fromkeys(risks))


def _claim_appears(claim: str, text: str) -> bool:
    if normalized_text(claim) in normalized_text(text):
        return True
    english_terms = [item.lower() for item in re.findall(r"[A-Za-z0-9]+", claim) if len(item) >= 3]
    if english_terms and all(
        re.search(rf"\b{re.escape(item)}\b", text, re.I) for item in english_terms
    ):
        return True
    signal = next((pattern for source, pattern in CLAIM_SIGNALS if source.search(claim)), None)
    return bool(signal and signal.search(text))


def _claims_grounded(claims: list[str], shots: list[StoryboardShot]) -> bool:
    if not claims:
        return False
    value_text = "\n".join(item.voiceover for item in shots if item.role == "value")
    proof_text = "\n".join(
        item.voiceover for item in shots if item.role in {"problem", "proof"}
    )
    return all(
        _claim_appears(claim, value_text) and _claim_appears(claim, proof_text) for claim in claims
    )


def _check(key: str, passed: bool, detail: str) -> ScriptQualityCheck:
    label, weight = next((label, weight) for name, label, weight in QUALITY_RULES if name == key)
    return ScriptQualityCheck(
        key=key,
        label=label,
        passed=passed,
        score=weight if passed else 0,
        max_score=weight,
        detail=detail,
    )


def _meaningful_text(value: str) -> bool:
    latin_words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", value)
    chinese = re.findall(r"[\u4e00-\u9fff]", value)
    if len(chinese) > len(latin_words) * 2:
        return len(chinese) >= 6
    return len(latin_words) >= 3


def _shot_paced(shot: StoryboardShot) -> bool:
    latin_words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", shot.voiceover)
    chinese = re.findall(r"[\u4e00-\u9fff]", shot.voiceover)
    if len(chinese) <= len(latin_words) * 2:
        limit = 210 if shot.role == "hook" else 180
        return len(latin_words) * 60 / shot.duration_seconds <= limit
    limit = 7 if shot.role == "hook" else 6
    return len(chinese) / shot.duration_seconds <= limit


def _content_sufficient(
    script: str,
    duration_seconds: int,
    shots: list[StoryboardShot],
) -> bool:
    latin_words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", script)
    chinese = re.findall(r"[\u4e00-\u9fff]", script)
    if len(chinese) <= len(latin_words) * 2:
        words_per_minute = len(latin_words) * 60 / max(1, duration_seconds)
        return 100 <= words_per_minute <= 180 and all(_shot_paced(item) for item in shots)
    chars_per_second = len(chinese) / max(1, duration_seconds)
    return 2 <= chars_per_second <= 6 and all(_shot_paced(item) for item in shots)


def _proof_has_action(shot: StoryboardShot) -> bool:
    action = re.compile(
        r"(?:拍|展示|放入|加入|连接|接入|拆|旋|分离|洗|盖|拿|举|饮|倒|拔|按|对比|冲|装|摆|移|特写|镜头|"
        r"show|add|blend|close|carry|connect|unplug|rinse|remove|compare|place|pour|wash|"
        r"camera|close-up|unlock)",
        re.I,
    )
    return bool(action.search(shot.visual) and _meaningful_text(shot.voiceover))


def _cta_has_action(shots: list[StoryboardShot]) -> bool:
    text = "\n".join(item.voiceover for item in shots if item.role == "cta")
    action = re.compile(
        r"(?:点击|查看|收藏|试试|尝试|对比|选择|判断|打开|进入|留言|下单|"
        r"tap|click|check|save|try|compare|choose|decide|judge|open|see|shop|learn)",
        re.I,
    )
    return bool(text.strip() and action.search(text))


def _objection_is_useful(shots: list[StoryboardShot]) -> bool:
    text = " ".join(item.voiceover.strip() for item in shots if item.role == "objection")
    if not _meaningful_text(text) or not re.search(r"[?？]", text):
        return False
    answer = re.split(r"[?？]", text, maxsplit=1)[-1]
    return _meaningful_text(answer)


def _claim_facts(
    brief: QualityBrief,
    script: str,
    shots: list[StoryboardShot],
    claims_used: list[str],
    audit_mode: ClaimAuditMode,
) -> tuple[list[str], bool, str]:
    auditable_text = "\n".join(
        [
            script,
            *(item.visual for item in shots),
            *(item.on_screen_text for item in shots),
        ]
    )
    unsupported = [
        item for item in claims_used if not _claim_is_allowed(item, brief.allowed_claims)
    ]
    unsupported = list(
        dict.fromkeys([*unsupported, *risk_claims(auditable_text, brief.allowed_claims)])
    )
    claims_ok = not unsupported and (bool(claims_used) if brief.product_id else not claims_used)
    if not brief.product_id and not claims_used:
        detail = "未关联商品，按非带货脚本检查"
    elif unsupported:
        integrity = re.compile(
            r"(?:Context|Brief|primary_selling_point|占位|最常见顾虑|placeholder|"
            r"亲测|我用了|我试过|有人问|you asked|I (?:tried|used|tested|stopped|overslept))",
            re.I,
        )
        prefix = (
            "内容完整性问题" if any(integrity.search(item) for item in unsupported) else "待补证据"
        )
        detail = f"{prefix}：{'、'.join(unsupported)}"
        if audit_mode == ClaimAuditMode.FREE_TEXT:
            detail += "；自由文本尚未完成独立声明审计"
    elif audit_mode == ClaimAuditMode.FREE_TEXT:
        claims_ok = False
        unsupported = list(dict.fromkeys([*unsupported, INDEPENDENT_AUDIT_MARKER]))
        detail = "自由文本尚未完成独立声明审计"
    elif not claims_used:
        detail = "已关联商品，但模型没有申报商品声明"
    elif not _claims_grounded(claims_used, shots):
        claims_ok = False
        ungrounded = [item for item in claims_used if not _claims_grounded([item], shots)]
        unsupported = list(dict.fromkeys([*unsupported, *ungrounded]))
        detail = f"卖点未同时出现在价值段与证明段口播：{'、'.join(ungrounded)}"
    else:
        detail = "封闭模板仅能使用所选卖点"
    return unsupported, claims_ok, detail


def _quality_facts(
    brief: QualityBrief,
    script: str,
    shots: list[StoryboardShot],
    claims_used: list[str],
    audit_mode: ClaimAuditMode,
) -> QualityFacts:
    unsupported, claims_ok, claims_detail = _claim_facts(
        brief,
        script,
        shots,
        claims_used,
        audit_mode,
    )
    first = shots[0] if shots else None
    second = shots[1] if len(shots) > 1 else None
    total = sum(item.duration_seconds for item in shots)
    value_ok = bool(
        second
        and second.role == "value"
        and sum(item.duration_seconds for item in shots[:2]) <= 6
        and _meaningful_text(second.voiceover)
    )
    cta_text = "\n".join(item.voiceover for item in shots if item.role == "cta")
    narration = "\n".join(item.voiceover.strip() for item in shots).strip()
    proofs = [item for item in shots if item.role == "proof"]
    return QualityFacts(
        unsupported=unsupported,
        claims_ok=claims_ok,
        claims_detail=claims_detail,
        hook_ok=bool(
            first
            and first.role == "hook"
            and first.duration_seconds <= 3
            and _meaningful_text(first.voiceover)
        ),
        value_ok=value_ok,
        reason_ok=len(claims_used) == 1 if brief.product_id else len(claims_used) <= 1,
        proof_ok=bool(proofs) and all(_proof_has_action(item) for item in proofs),
        objection_ok=_objection_is_useful(shots),
        total_seconds=total,
        consistent=normalized_text(script) == normalized_text(narration),
        cta_ok=_cta_has_action(shots) and not risk_claims(cta_text, brief.allowed_claims),
        content_ok=_content_sufficient(script, total, shots),
    )


def _quality_checks(brief: QualityBrief, facts: QualityFacts) -> list[ScriptQualityCheck]:
    return [
        _check("claims", facts.claims_ok, facts.claims_detail),
        _check("hook", facts.hook_ok, "首镜在 3 秒内完成有效钩子"),
        _check(
            "value",
            facts.value_ok,
            "前两镜在 6 秒内说清价值" if facts.value_ok else "第二镜未在累计 6 秒内说清价值",
        ),
        _check(
            "single_reason",
            facts.reason_ok,
            "本条只主打一个商品事实" if facts.reason_ok else "没有明确单一购买理由",
        ),
        _check(
            "proof",
            facts.proof_ok,
            "证明镜头包含具体可拍动作" if facts.proof_ok else "证明镜头没有具体动作",
        ),
        _check(
            "objection",
            facts.objection_ok,
            "提出真实顾虑并给出有限回答" if facts.objection_ok else "异议段缺少具体问题或有限回答",
        ),
        _check(
            "duration",
            abs(facts.total_seconds - brief.duration_seconds) <= 2,
            f"目标 {brief.duration_seconds} 秒，当前 {facts.total_seconds} 秒",
        ),
        _check(
            "consistency",
            facts.consistent,
            "完整脚本与逐镜口播一致" if facts.consistent else "完整脚本与逐镜口播不一致",
        ),
        _check(
            "cta",
            facts.cta_ok,
            "包含自然且具体的行动语" if facts.cta_ok else "CTA 缺少具体动作或包含未授权促销",
        ),
        _check(
            "content",
            facts.content_ok,
            "口播词速适合目标时长" if facts.content_ok else "口播过短或过载，无法匹配目标时长",
        ),
    ]


def evaluate_quality(
    brief: QualityBrief,
    script: str,
    shots: list[StoryboardShot],
    claims_used: list[str],
    audit_mode: ClaimAuditMode = ClaimAuditMode.FREE_TEXT,
) -> tuple[ScriptQuality, list[str]]:
    facts = _quality_facts(brief, script, shots, claims_used, audit_mode)
    checks = _quality_checks(brief, facts)
    score = sum(item.score for item in checks)
    risks = [item.detail for item in checks if not item.passed]
    status = "ready_to_test" if all(item.passed for item in checks) else "needs_revision"
    quality = ScriptQuality(status=status, score=score, checks=checks, risks=risks)
    return quality, facts.unsupported
