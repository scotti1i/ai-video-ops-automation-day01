"""把审稿口播装配成六镜：口播出自 commerce_copy，导演指令与屏幕字在这里对齐。

分工：
- voiceover：真人对观众说的话（commerce_copy 手写维护）；
- visual：给拍摄者看的导演指令，允许出现机位与合规提示；
- on_screen_text：≤12 字的点题短语，不是口播截断。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from video_ops.domain.commerce_copy import (
    BRIEF_BODY_EN,
    BRIEF_BODY_ZH,
    BRIEF_OPENINGS_EN,
    BRIEF_OPENINGS_ZH,
    CURATED_ANGLES,
    CURATED_EN,
    CURATED_ZH,
    GENERIC_BODY_EN,
    GENERIC_BODY_ZH,
    GENERIC_OPENINGS_EN,
    GENERIC_OPENINGS_ZH,
    has_mechanism,
    mechanism_key,
    scene_word,
)

__all__ = [
    "brief_parts",
    "brief_screens",
    "brief_visuals",
    "commerce_parts",
    "has_mechanism",
    "mechanism_key",
    "screen_texts",
    "visuals_for",
]


@dataclass(frozen=True)
class Mechanism:
    """一个封闭卖点的可拍素材：五个导演指令 + 六个屏幕点题。"""

    value_visual: str
    old_visual: str
    new_visual: str
    result_visual: str
    objection_visual: str
    screens_zh: tuple[str, str, str, str, str, str]
    screens_en: tuple[str, str, str, str, str, str]


MECHANISMS = {
    "direct-drink": Mechanism(
        value_visual="在杯身贴可移除标记，杯体、搅打位置和饮用杯口同框",
        old_visual="桌面并排放原杯与另一个空杯，只演示一次换杯路径",
        new_visual="标记杯全程入镜，加入食材并在同一个杯体中完成搅打",
        result_visual="保持标记可见，当场用刚才搅打的同一个杯子饮用",
        objection_visual="镜头停在桌面，只标注同杯直饮，不拍防漏或携带",
        screens_zh=("同一个杯子", "多倒一次", "打完直接喝", "原杯开喝", "防漏另测", "查看杯体"),
        screens_en=(
            "SAME CUP",
            "THE EXTRA POUR",
            "BLEND AND SIP",
            "STRAIGHT FROM IT",
            "LEAKS NOT TESTED",
            "CHECK THE CUP",
        ),
    ),
    "detachable-wash": Mechanism(
        value_visual="商品页卖点特写，标出杯体可拆洗一栏",
        old_visual="对比封闭杯体，只能灌肥皂水摇晃的费劲洗法",
        new_visual="双手拆开杯体，逐件放进水池冲洗",
        result_visual="冲净沥干的部件排开，再装回成完整杯子",
        objection_visual="特写电机部分用拧干湿布擦拭，全程远离水流",
        screens_zh=("杯体可拆", "封死难洗", "拆开冲洗", "装回完整", "能全进水吗", "看完再定"),
        screens_en=(
            "COMES APART",
            "THE SEALED MESS",
            "OPEN AND RINSE",
            "BACK TOGETHER",
            "EVERY PART? UNCLEAR",
            "CHECK THE LISTING",
        ),
    ),
    "usb-c-charge": Mechanism(
        value_visual="镜头特写杯身的 USB-C 接口与线头，接口标识清晰可见",
        old_visual="桌面并排摆两种线头与杯身接口，口型差异清晰可见",
        new_visual="手把 USB-C 线直接接入杯身接口，接口与线头保持同框",
        result_visual="USB-C 线接入后保持同框，不展示续航或充电速度数字",
        objection_visual="镜头只拍接口和线头，屏幕标注只验证接口类型",
        screens_zh=("USB-C 充电", "专用线退场", "插上就充", "同一个口", "续航另说", "看清接口"),
        screens_en=(
            "USB-C PORT",
            "ODD CABLES OUT",
            "PLUG IT IN",
            "SAME PORT",
            "SPEED NOT TESTED",
            "CHECK THE PORT",
        ),
    ),
}

# 每个角度的开场拍法，保证十条候选的首镜画面互不相同。
HOOK_VISUAL_STYLE = {
    "痛点直击": "俯拍问题动作",
    "结果先看": "先给完成画面",
    "一镜实测": "固定机位不切",
    "双路对比": "左右分屏对照",
    "购买标准": "特写判断细节",
    "使用场景": "跟拍真实动线",
    "购买问答": "问题上屏再实拍",
    "连续证据": "主体全程入镜",
    "核对清单": "台面逐项排开",
    "异议先答": "先亮边界再实拍",
}

ANGLE_SCREEN_ZH = {
    "痛点直击": "每天多一步",
    "结果先看": "先看结果",
    "一镜实测": "一镜到底",
    "双路对比": "两种做法",
    "购买标准": "只看一条",
    "使用场景": "真实场景",
    "购买问答": "买前必问",
    "连续证据": "全程不切",
    "核对清单": "三个核对点",
    "异议先答": "先说边界",
}

ANGLE_SCREEN_EN = {
    "痛点直击": "THE EXTRA STEP",
    "结果先看": "RESULT FIRST",
    "一镜实测": "UNCUT",
    "双路对比": "SIDE BY SIDE",
    "购买标准": "ONE RULE",
    "使用场景": "REAL SETTING",
    "购买问答": "ASKED, ANSWERED",
    "连续证据": "NO CUTS",
    "核对清单": "THREE CHECKS",
    "异议先答": "LIMITS FIRST",
}

# problem / proof 两镜取哪两段导演指令，按角度错开避免画面雷同。
CURATED_VISUAL_PAIRS = {
    "direct-drink": (
        ("old_visual", "new_visual"),
        ("new_visual", "result_visual"),
        ("new_visual", "result_visual"),
        ("old_visual", "result_visual"),
        ("old_visual", "result_visual"),
        ("new_visual", "result_visual"),
        ("value_visual", "result_visual"),
        ("new_visual", "result_visual"),
        ("value_visual", "result_visual"),
        ("value_visual", "result_visual"),
    ),
    "detachable-wash": (
        ("old_visual", "new_visual"),
        ("value_visual", "result_visual"),
        ("old_visual", "new_visual"),
        ("old_visual", "new_visual"),
        ("value_visual", "new_visual"),
        ("old_visual", "new_visual"),
        ("value_visual", "new_visual"),
        ("new_visual", "result_visual"),
        ("value_visual", "objection_visual"),
        ("value_visual", "objection_visual"),
    ),
    "usb-c-charge": (
        ("old_visual", "new_visual"),
        ("new_visual", "result_visual"),
        ("old_visual", "new_visual"),
        ("old_visual", "result_visual"),
        ("value_visual", "new_visual"),
        ("old_visual", "new_visual"),
        ("value_visual", "new_visual"),
        ("new_visual", "result_visual"),
        ("value_visual", "new_visual"),
        ("new_visual", "objection_visual"),
    ),
}

_GENERIC_VISUALS = (
    "特写商品和它的主打卖点部位",
    "固定机位完整拍一次卖点动作",
    "同机位拍动作结束后的状态",
)


def _angle(payload: dict[str, Any]) -> str:
    value = str(payload.get("angle") or "一镜实测")
    return value if value in CURATED_ANGLES else "一镜实测"


def _angle_index(payload: dict[str, Any]) -> int:
    return CURATED_ANGLES.index(_angle(payload))


def _point(payload: dict[str, Any]) -> str:
    return str(payload.get("primary_selling_point") or "")


def _mechanism(payload: dict[str, Any]) -> Mechanism | None:
    return MECHANISMS.get(mechanism_key(_point(payload)) or "")


def commerce_parts(payload: dict[str, Any], english: bool) -> tuple[str, ...]:
    """带商品的六句口播：已审稿机制直接取表，未知卖点走通用人话模板。"""
    key = mechanism_key(_point(payload))
    index = _angle_index(payload)
    if key:
        return (CURATED_EN if english else CURATED_ZH)[key][index]
    point = _point(payload) or ("its headline feature" if english else "它的主打设计")
    title = str(payload.get("product_title") or ("this product" if english else "这件商品"))
    openings = (GENERIC_OPENINGS_EN if english else GENERIC_OPENINGS_ZH)[index]
    body = GENERIC_BODY_EN if english else GENERIC_BODY_ZH
    lines = (*openings, *body)
    return tuple(line.format(point=point, title=title) for line in lines)


def visuals_for(payload: dict[str, Any], english: bool) -> tuple[str, ...]:
    """六镜导演指令；机制外商品仍给可拍动作，不再输出占位文本。"""
    del english  # 导演指令统一中文，给拍摄者看
    angle = _angle(payload)
    style = HOOK_VISUAL_STYLE[angle]
    mechanism = _mechanism(payload)
    if mechanism is None:
        value_visual, action_visual, result_visual = _GENERIC_VISUALS
        return (
            f"实拍开场·{style}：商品与使用现场同框入镜",
            f"实拍价值：{value_visual}",
            f"实拍动作·{style}：{action_visual}",
            f"实拍结果·{style}：{result_visual}",
            "实拍顾虑：镜头停在商品上，不拍未验证的部分",
            "实拍收尾：商品定格，出现查看详情提示",
        )
    key = mechanism_key(_point(payload))
    first_slot, second_slot = CURATED_VISUAL_PAIRS[key][_angle_index(payload)]
    hook_visual = {
        "结果先看": mechanism.result_visual,
        "异议先答": mechanism.objection_visual,
    }.get(angle, getattr(mechanism, first_slot))
    return (
        f"实拍开场·{style}：{hook_visual}",
        f"实拍价值：{mechanism.value_visual}",
        f"实拍动作·{style}：{getattr(mechanism, first_slot)}",
        f"实拍结果·{style}：{getattr(mechanism, second_slot)}",
        f"实拍顾虑：{mechanism.objection_visual}",
        f"实拍收尾：{mechanism.result_visual}，出现查看详情按钮",
    )


def screen_texts(payload: dict[str, Any], english: bool) -> tuple[str, ...]:
    """六镜屏幕字：角度点题 + 机制点题，全部 ≤12 字。"""
    angle = _angle(payload)
    first = (ANGLE_SCREEN_EN if english else ANGLE_SCREEN_ZH)[angle]
    mechanism = _mechanism(payload)
    if mechanism is None:
        if english:
            return (
                first,
                "ONE CLAIM ONLY",
                "HANDS ON",
                "SEE THE RESULT",
                "THE REST? UNTESTED",
                "CHECK THE PAGE",
            )
        return (first, "只讲一个卖点", "上手实拍", "拍完给你看", "其他另说", "详情页见")
    screens = mechanism.screens_en if english else mechanism.screens_zh
    key = mechanism_key(_point(payload))
    first_slot, second_slot = CURATED_VISUAL_PAIRS[key][_angle_index(payload)]
    slot_text = {
        "value_visual": screens[0],
        "old_visual": screens[1],
        "new_visual": screens[2],
        "result_visual": screens[3],
        "objection_visual": screens[4],
    }
    return (
        first,
        screens[0],
        slot_text[first_slot],
        slot_text[second_slot],
        screens[4],
        screens[5],
    )


def brief_parts(payload: dict[str, Any], english: bool) -> tuple[str, ...]:
    """无商品路径：围绕 brief 场景的生活化口播，不讲拍摄方法论。"""
    index = _angle_index(payload)
    scene = scene_word(str(payload.get("scenario") or ""))
    openings = (BRIEF_OPENINGS_EN if english else BRIEF_OPENINGS_ZH)[index]
    body = BRIEF_BODY_EN if english else BRIEF_BODY_ZH
    return tuple(line.format(scene=scene) for line in (*openings, *body))


def brief_visuals(payload: dict[str, Any]) -> tuple[str, ...]:
    style = HOOK_VISUAL_STYLE[_angle(payload)]
    scene = scene_word(str(payload.get("scenario") or ""))
    return (
        f"实拍开场·{style}：{scene}现场原样入镜，不提前收拾",
        "实拍价值：手指向本条要解决的那一处，给一个明确特写",
        "实拍过程：固定机位，从动手前的原状开始拍",
        "实拍结果：同一机位拍完成后的样子，前后可对照",
        "实拍顾虑：镜头扫过没改动的区域，边界拍清楚",
        "实拍收尾：完成画面定格，出现收藏提示",
    )


def brief_screens(payload: dict[str, Any], english: bool) -> tuple[str, ...]:
    angle = _angle(payload)
    if english:
        return (
            ANGLE_SCREEN_EN[angle],
            "ONE FIX",
            "BEFORE",
            "AFTER",
            "YOUR PLACE TOO?",
            "SAVE AND TRY",
        )
    return (ANGLE_SCREEN_ZH[angle], "只解决一处", "改前", "改后", "你家也适用吗", "收藏照做")
