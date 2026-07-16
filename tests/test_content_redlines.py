"""内容红线：零密钥生成与种子样例都必须是真人可拍可说的口播。

红线来源 design.md（v5 候选内容合同 + v6 验收）：
- 口播不含字段标签、导演指令与内部术语；
- 十个测试角度十种开头，任意两条候选的前两句互不相同；
- 屏幕字是点题短语，不是口播的前缀截断；
- 候选标题像真实视频标题，不是策略自述。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from video_ops.application.service import VideoOperationsService

SEED_PATH = Path(__file__).parents[1] / "data" / "sample" / "workspace-seed.json"

EN_BRIEF = "为每天早上赶时间的上班族推广便携榨汁杯，重点讲随行杯直接饮用，目标 25 秒，美区英文"
ZH_BRIEF = "给通勤用户推广便携榨汁杯，重点讲随行杯直接饮用，目标 25 秒"

# 台词禁用词表：字段标签、内部术语、导演指令
FORBIDDEN_IN_VOICEOVER = (
    "问题动作",
    "先看结果：",
    "倒回动作",
    "Result:",
    "Problem:",
    "Rewind:",
    "Start:",
    "Test it:",
    "继续裂变",
    "原始资料",
    "本次内容",
    "测试角度",
    "Context",
    "Brief",
    "placeholder",
    "核心卖点",
    "最常见顾虑",
    "保持同一机位",
    "放进画面",
)

FORBIDDEN_IN_TITLE = ("｜", "本次内容", "先说用户", "证据版", "测试角度")


def _normalized(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).lower()


def _is_prefix_of_voiceover(screen: str, voiceover: str) -> bool:
    return _normalized(voiceover).startswith(_normalized(screen))


@pytest.fixture(params=(EN_BRIEF, ZH_BRIEF), ids=("en", "zh"))
def candidates(request, service: VideoOperationsService):
    _, generated = service.generate_batch(
        product_id="product-blender",
        brief=request.param,
        reference_url=None,
        count=10,
        producer="mock",
    )
    return generated


def test_voiceover_is_spoken_language_without_labels(candidates) -> None:
    for candidate in candidates:
        for shot in candidate.shots:
            assert "：" not in shot.voiceover, (candidate.angle, shot.voiceover)
            assert ":" not in shot.voiceover, (candidate.angle, shot.voiceover)
            for term in FORBIDDEN_IN_VOICEOVER:
                assert term not in shot.voiceover, (candidate.angle, term)


def test_ten_angles_open_with_ten_different_first_two_lines(candidates) -> None:
    openings = [(item.shots[0].voiceover, item.shots[1].voiceover) for item in candidates]

    assert len(set(openings)) == 10
    assert len({hook for hook, _ in openings}) == 10
    assert len({value for _, value in openings}) == 10


def test_screen_text_is_caption_not_voiceover_truncation(candidates) -> None:
    for candidate in candidates:
        for shot in candidate.shots:
            assert shot.on_screen_text.strip(), (candidate.angle, shot.order)
            assert not _is_prefix_of_voiceover(shot.on_screen_text, shot.voiceover), (
                candidate.angle,
                shot.on_screen_text,
                shot.voiceover,
            )


def test_candidate_titles_read_like_real_videos(candidates) -> None:
    titles = [item.title for item in candidates]

    assert len(set(titles)) == 10
    for title in titles:
        for term in FORBIDDEN_IN_TITLE:
            assert term not in title, title


# ------------------------------------------------------------
# 种子契约 v2：手写脚本与分镜达到投放水平
# ------------------------------------------------------------

VALID_ROLES = {"hook", "problem", "value", "proof", "objection", "cta"}


def _seed() -> dict:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def test_seed_declares_contract_v2_and_batch_notes() -> None:
    seed = _seed()

    assert seed["version"] == 3
    assert all(str(batch.get("note", "")).strip() for batch in seed["batches"])


def test_seed_scripts_and_storyboards_are_publish_grade() -> None:
    seed = _seed()
    scripted = [item for item in seed["videos"] if "script" in item or "storyboard" in item]

    # organizer 被 test_data_flywheel 钉作"字段缺席走生成路径"的探针，刻意不带手写稿
    assert len(scripted) >= 8
    for item in scripted:
        shots = item["storyboard"]["shots"]
        assert 3 <= len(shots) <= 6, item["key"]
        total = sum(shot["duration_seconds"] for shot in shots)
        assert 17 <= total <= 30, (item["key"], total)
        assert item["script"]["content"] == "\n".join(shot["voiceover"] for shot in shots)
        for shot in shots:
            assert shot["role"] in VALID_ROLES, (item["key"], shot["order"])
            assert shot["visual"].strip() and shot["voiceover"].strip()
            assert "：" not in shot["voiceover"] and ":" not in shot["voiceover"]
            for term in FORBIDDEN_IN_VOICEOVER:
                assert term not in shot["voiceover"], (item["key"], term)
            screen = shot["on_screen_text"]
            assert screen.strip() and len(screen) <= 12, (item["key"], screen)
            assert not _is_prefix_of_voiceover(screen, shot["voiceover"]), (item["key"], screen)
        roles = [shot["role"] for shot in shots]
        assert roles[0] == "hook" and roles[-1] == "cta", item["key"]


def test_seed_needs_script_videos_stay_honestly_empty() -> None:
    seed = _seed()
    waiting = [item for item in seed["videos"] if item["state"] == "needs_script"]

    assert waiting
    for item in waiting:
        assert "script" not in item and "storyboard" not in item, item["key"]


def test_seed_titles_and_goals_use_operator_voice() -> None:
    seed = _seed()
    titles = [item["title"] for item in seed["videos"]]

    assert len(set(titles)) == len(titles)
    for item in seed["videos"]:
        for term in FORBIDDEN_IN_TITLE:
            assert term not in item["title"], item["title"]
        assert item["goal"].strip()
