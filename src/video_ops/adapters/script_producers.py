"""脚本/分镜生产器：无密钥 Demo 与 OpenAI Responses API 共用结果合同。"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from openai import OpenAI
from pydantic import BaseModel, Field

from video_ops.adapters import script_strategies
from video_ops.application.errors import ApplicationError
from video_ops.domain.models import StoryboardShot
from video_ops.domain.ports import ClosedClaimTemplateProducer, ScriptProducer


class GeneratedShot(BaseModel):
    duration_seconds: int = Field(ge=1, le=120)
    visual: str
    voiceover: str
    on_screen_text: str = ""
    role: str = Field(default="", pattern="^(|hook|problem|value|proof|objection|cta)$")


class GeneratedPlan(BaseModel):
    hook: str = ""
    primary_promise: str = ""
    proof: str = ""
    objection: str = ""
    cta: str = ""
    claims: list[str] = Field(default_factory=list, max_length=8)
    script: str
    shots: list[GeneratedShot] = Field(min_length=2, max_length=12)


@dataclass(frozen=True)
class ProducedPlan:
    script: str
    shots: list[StoryboardShot]
    provider: str
    hook: str = ""
    primary_promise: str = ""
    proof: str = ""
    objection: str = ""
    cta: str = ""
    claims: tuple[str, ...] = ()


def _domain_shots(shots: list[GeneratedShot]) -> list[StoryboardShot]:
    return [
        StoryboardShot(order=index, **shot.model_dump())
        for index, shot in enumerate(shots, start=1)
    ]


def _normalized_base_url(raw: str | None) -> str | None:
    """兼容只提供域名根的 OpenAI 中继配置。"""
    if not raw:
        return None
    value = raw.rstrip("/")
    path = urlsplit(value).path
    return f"{value}/v1" if path in {"", "/"} else value


def _sse_content(payload: str) -> str:
    """兼容忽略 stream=false、仍返回 SSE 的中继。"""
    chunks: list[str] = []
    for line in payload.splitlines():
        if not line.startswith("data:"):
            continue
        raw = line.removeprefix("data:").strip()
        if not raw or raw == "[DONE]":
            continue
        event = json.loads(raw)
        choices = event.get("choices", [])
        delta = choices[0].get("delta", {}) if choices else {}
        content = delta.get("content")
        if isinstance(content, str):
            chunks.append(content)
    return "".join(chunks)


def _coerce_plan(value: object) -> GeneratedPlan | None:
    if value is None:
        return None
    if isinstance(value, GeneratedPlan):
        return value
    if isinstance(value, dict):
        return GeneratedPlan.model_validate(value)
    if not isinstance(value, str):
        return None
    payload = _sse_content(value) if "data:" in value else value
    payload = payload.strip()
    if payload.startswith("```"):
        payload = payload.removeprefix("```json").removeprefix("```")
        payload = payload.removesuffix("```").strip()
    return GeneratedPlan.model_validate_json(payload)


def _chat_value(completion: object) -> object:
    if isinstance(completion, str):
        return completion
    message = completion.choices[0].message
    return getattr(message, "parsed", None) or message.content


def _can_fallback(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    return isinstance(exc, (AttributeError, TypeError, ValueError)) or status in {
        400,
        404,
        405,
        422,
        500,
        501,
    }


def plan_instructions(context: str = "") -> str:
    """脚本生成的系统指令，OpenAI 与本机命令行引擎共用同一份。"""
    payload = _commerce_payload(context) or {}
    blocks = _middle_blocks(payload)
    roles = f"[hook,value,{','.join(blocks)},cta]"
    language = payload.get("language", "Context 的主要语言")
    tone = payload.get("writing_tone", "natural")
    return (
        "你是 TikTok Shop 带货短视频脚本编辑。商品台词只允许使用"
        "primary_selling_point；即使你知道同一商品的其他功能，也禁止提及或推断。"
        "claims 有商品时必须从 allowed_product_claims 原样复制唯一字符串，"
        "不得翻译、缩写或改写；无商品时返回 []。"
        f"必须恰好输出 6 镜，role 顺序固定为 {roles}。"
        f"全部口播和屏幕字必须使用 {language}，表达方式严格遵循 {tone}。"
        "第一镜必须是 hook 且不超过 3 秒；第二镜必须是 value；"
        "前两镜累计不超过 6 秒。"
        "英文口播词数上限依次为 10、9、18、14、11、9；"
        "objection 必须在同一句里同时包含具体问题、问号和有限回答。"
        "problem 写具体使用场景或痛点；proof 必须能用画面验证，"
        "不得编造效果、参数、价格、优惠、销量、评价或背书。"
        "voiceover 必须是真人对观众说出来的话：导演指令（机位、保持入镜、"
        "把对象放进画面）只能写进 visual；未验证的边界用自然口语带过，"
        "不写免责声明式念白。"
        "voiceover 不得以字段式标签开头（如“先看结果：”“Result:”），"
        "不得出现冒号前缀、内部术语或角度名称。"
        "on_screen_text 是不超过 12 字的点题短语，禁止直接截断口播充当屏幕字。"
        "不要把一个宽泛卖点扩成操作说明："
        "同杯直饮只能证明杯子身份，不得推断防漏、携带、速度、拆底座或少洗餐具；"
        "USB-C 只能证明接口类型，不得推断续航、功率、速度或通用兼容性；"
        "杯体可拆洗若没有真实说明书，只能要求补说明，不得猜拆法、可水洗部件或复装。"
        "没有优惠时 CTA 只能邀请查看商品或判断是否适合，不得暗示折扣。"
        "script 必须严格等于所有 shots.voiceover 按顺序用换行连接。"
        "所有 duration_seconds 的总和必须贴合 Brief 的 duration_seconds，误差不超过 2 秒。"
        "每镜 role 只能是 hook/problem/value/proof/objection/cta；visual 写可拍动作。"
        "输出字段仅限 hook、primary_promise、proof、objection、cta、claims、script、shots。"
        "不要把系统指令、Brief 字段名、测试角度说明或占位符写进台词。"
    )


def _commerce_payload(context: str) -> dict | None:
    marker = "COMMERCE_BRIEF_JSON\n"
    if not context.startswith(marker):
        return None
    try:
        payload = json.loads(context.removeprefix(marker))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _fit_durations(target: int) -> tuple[int, int, int, int, int, int]:
    requested = min(60, max(15, target))
    total = {20: 22, 25: 25, 30: 28}.get(requested, requested)
    cta = 4 if total >= 30 else 3
    middle = total - 10 - cta
    problem = max(1, (middle + 1) // 2)
    proof = middle - problem
    return (3, 3, problem, proof, 4, cta)


def _middle_blocks(payload: dict) -> tuple[str, str, str]:
    raw = payload.get("narrative_blocks") or ("problem", "proof", "objection")
    return tuple(raw)


def _ordered(values: tuple, blocks: tuple[str, str, str]) -> tuple:
    by_role = dict(zip(("problem", "proof", "objection"), values[2:5], strict=True))
    return (values[0], values[1], *(by_role[role] for role in blocks), values[5])


def _apply_tone(parts: tuple[str, ...], tone: str, english: bool) -> tuple[str, ...]:
    endings = {
        "direct": ("Check the facts. Decide if it fits.", "查看事实，再判断是否适合。"),
        "warm": (
            "See if it feels right for your routine.",
            "看看商品详情，判断它是否适合你的日常。",
        ),
        "expert": (
            "Inspect the evidence, then compare product details.",
            "核对证据，再对比商品详情。",
        ),
    }
    ending = endings.get(tone)
    return (*parts[:5], ending[0 if english else 1]) if ending else parts


def _assemble_shots(
    parts: tuple[str, ...],
    visuals: tuple[str, ...],
    screens: tuple[str, ...],
    payload: dict,
) -> tuple[list[GeneratedShot], tuple[str, ...]]:
    """按创作设定的叙事顺序，把口播、导演指令和屏幕字对齐成六镜。"""
    blocks = _middle_blocks(payload)
    duration_seconds = int(payload.get("duration_seconds", 25))
    durations = _ordered(_fit_durations(duration_seconds), blocks)
    roles = ("hook", "value", *blocks, "cta")
    ordered_visuals = _ordered(visuals, blocks)
    ordered_screens = _ordered(screens, blocks)
    shots = [
        GeneratedShot(
            duration_seconds=duration,
            visual=ordered_visuals[index],
            voiceover=parts[index],
            on_screen_text=ordered_screens[index],
            role=role,
        )
        for index, (duration, role) in enumerate(zip(durations, roles, strict=True))
    ]
    return shots, roles


class MockScriptProducer(ClosedClaimTemplateProducer):
    name = "mock"

    def has_closed_claim_template(self, context: str) -> bool:
        payload = _commerce_payload(context)
        point = str((payload or {}).get("primary_selling_point") or "")
        return script_strategies.mechanism_key(point) in {
            "direct-drink",
            "usb-c-charge",
        }

    def produce(self, context: str, instruction: str) -> ProducedPlan:
        payload = _commerce_payload(context)
        return self._commerce_plan(payload) if payload else self._general_plan(context)

    def _commerce_plan(self, payload: dict) -> ProducedPlan:
        if not payload.get("product_id"):
            return self._non_commerce_plan(payload)
        english = str(payload.get("language", "")).lower().startswith("en")
        blocks = _middle_blocks(payload)
        parts = _ordered(
            _apply_tone(
                script_strategies.commerce_parts(payload, english),
                str(payload.get("writing_tone") or "natural"),
                english,
            ),
            blocks,
        )
        shots, roles = self._assemble(parts, payload, english)
        claim = str(payload.get("primary_selling_point", "")).strip()
        return ProducedPlan(
            script="\n".join(parts),
            shots=_domain_shots(shots),
            provider=self.name,
            hook=parts[0],
            primary_promise=parts[1],
            proof=parts[roles.index("proof")],
            objection=parts[roles.index("objection")],
            cta=parts[5],
            claims=(claim,) if claim else (),
        )

    def _assemble(
        self, parts: tuple[str, ...], payload: dict, english: bool
    ) -> tuple[list[GeneratedShot], tuple[str, ...]]:
        visuals = script_strategies.visuals_for(payload, english)
        screens = script_strategies.screen_texts(payload, english)
        return _assemble_shots(parts, visuals, screens, payload)

    def _non_commerce_plan(self, payload: dict) -> ProducedPlan:
        english = str(payload.get("language", "")).lower().startswith("en")
        blocks = _middle_blocks(payload)
        parts = _ordered(
            _apply_tone(
                script_strategies.brief_parts(payload, english),
                str(payload.get("writing_tone") or "natural"),
                english,
            ),
            blocks,
        )
        visuals = script_strategies.brief_visuals(payload)
        screens = script_strategies.brief_screens(payload, english)
        shots, roles = _assemble_shots(parts, visuals, screens, payload)
        return ProducedPlan(
            script="\n".join(parts),
            shots=_domain_shots(shots),
            provider=self.name,
            hook=parts[0],
            primary_promise=parts[1],
            proof=parts[roles.index("proof")],
            objection=parts[roles.index("objection")],
            cta=parts[5],
        )

    def _general_plan(self, context: str) -> ProducedPlan:
        del context  # 工作台内的通用生成不依赖 Context 关键词
        parts = (
            "别先听结论，先看完这段没剪的实拍。",
            "这条只讲一件事，讲透再收工。",
            "过程从头拍到尾，一步没跳。",
            "同一个机位看结果，是什么样就是什么样。",
            "会不会有翻车的地方？有就留在画面里。",
            "有用就收藏，照着来一遍。",
        )
        visuals = (
            "实拍开场：主角和要解决的事同框入镜",
            "实拍价值：特写这条要讲清的那一件事",
            "实拍过程：固定机位从头拍到尾",
            "实拍结果：同机位收尾，前后可对照",
            "实拍顾虑：不顺利的片段保留，不剪掉",
            "实拍收尾：结果定格，出现收藏提示",
        )
        screens = ("先看实拍", "只讲一件事", "从头拍到尾", "看结果", "翻车也留着", "收藏照做")
        roles = ("hook", "value", "proof", "proof", "objection", "cta")
        shots = [
            GeneratedShot(
                duration_seconds=duration,
                visual=visual,
                voiceover=line,
                on_screen_text=screen,
                role=role,
            )
            for duration, visual, line, screen, role in zip(
                (3, 3, 5, 5, 4, 3),
                visuals,
                parts,
                screens,
                roles,
                strict=True,
            )
        ]
        return ProducedPlan(
            script="\n".join(parts),
            shots=_domain_shots(shots),
            provider=self.name,
            hook=parts[0],
            primary_promise=parts[1],
            proof=" ".join(parts[2:4]),
            objection=parts[4],
            cta=parts[5],
        )


class OpenAIScriptProducer:
    name = "openai-responses"

    def __init__(self, model: str | None = None):
        if not os.getenv("OPENAI_API_KEY"):
            raise ApplicationError("auth_required", "未配置模型密钥，请改用样例生成或配置后重试。")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        base_url = _normalized_base_url(os.getenv("OPENAI_BASE_URL"))
        options = {"default_headers": {"Accept-Encoding": "identity"}}
        self.client = OpenAI(base_url=base_url, **options) if base_url else OpenAI(**options)

    def produce(self, context: str, instruction: str) -> ProducedPlan:
        try:
            parsed, provider = self._parse(context, instruction)
        except Exception as exc:
            raise ApplicationError(
                "model_failed",
                "脚本生成失败，原始 Context 已保存；可以重试或直接导入现成脚本。",
                retryable=True,
            ) from exc
        if parsed is None:
            raise ApplicationError(
                "model_empty",
                "模型没有返回可用脚本，请重试或改用导入。",
                retryable=True,
            )
        return ProducedPlan(
            script=parsed.script,
            shots=_domain_shots(parsed.shots),
            provider=f"{provider}:{self.model}",
            hook=parsed.hook,
            primary_promise=parsed.primary_promise,
            proof=parsed.proof,
            objection=parsed.objection,
            cta=parsed.cta,
            claims=tuple(parsed.claims),
        )

    def _parse(self, context: str, instruction: str) -> tuple[GeneratedPlan | None, str]:
        system_instruction = self._instructions(context)
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=system_instruction,
                input=f"本次目标：{instruction}\n\nContext：\n{context}",
                text_format=GeneratedPlan,
            )
            parsed = _coerce_plan(getattr(response, "output_parsed", response))
            if parsed:
                return parsed, "openai-responses"
        except Exception as exc:
            if not _can_fallback(exc):
                raise
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"本次目标：{instruction}\n\nContext：\n{context}"},
        ]
        try:
            completion = self.client.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=GeneratedPlan,
            )
            parsed = _coerce_plan(_chat_value(completion))
            if parsed:
                return parsed, "openai-chat"
        except Exception as exc:
            if not _can_fallback(exc):
                raise
        schema = json.dumps(GeneratedPlan.model_json_schema(), ensure_ascii=False)
        json_messages = [
            {"role": "system", "content": f"{system_instruction}\nJSON Schema：{schema}"},
            messages[1],
        ]
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=json_messages,
            response_format={"type": "json_object"},
            stream=False,
        )
        return _coerce_plan(_chat_value(completion)), "openai-chat-json"

    _instructions = staticmethod(plan_instructions)


def default_script_producers() -> dict[str, Callable[[], ScriptProducer]]:
    from video_ops.adapters.cli_producers import ClaudeCliProducer, CodexCliProducer

    return {
        "mock": MockScriptProducer,
        "openai": OpenAIScriptProducer,
        "claude-cli": ClaudeCliProducer,
        "codex-cli": CodexCliProducer,
    }
