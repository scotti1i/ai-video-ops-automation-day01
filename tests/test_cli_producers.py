"""本机命令行写脚本引擎：用假可执行文件验证解析与容错，不真实调用 claude/codex。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from video_ops.adapters.cli_producers import ClaudeCliProducer, CodexCliProducer
from video_ops.application.errors import ApplicationError

PLAN = {
    "hook": "开场",
    "primary_promise": "承诺",
    "proof": "证明",
    "objection": "顾虑",
    "cta": "行动",
    "claims": ["同杯直饮"],
    "script": "第一句\n第二句",
    "shots": [
        {
            "duration_seconds": 3,
            "visual": "画面一",
            "voiceover": "第一句",
            "on_screen_text": "",
            "role": "hook",
        },
        {
            "duration_seconds": 4,
            "visual": "画面二",
            "voiceover": "第二句",
            "on_screen_text": "",
            "role": "cta",
        },
    ],
}


def _install(tmp_path: Path, monkeypatch, name: str, body: str) -> None:
    executable = tmp_path / name
    executable.write_text(f"#!/bin/sh\n{body}\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")


def test_claude_json_envelope_is_unwrapped(tmp_path, monkeypatch):
    envelope = {
        "type": "result",
        "is_error": False,
        "result": json.dumps(PLAN, ensure_ascii=False),
    }
    out = tmp_path / "claude-out.json"
    out.write_text(json.dumps(envelope, ensure_ascii=False))
    prompt_log = tmp_path / "prompt.txt"
    _install(tmp_path, monkeypatch, "claude", f'printf "%s" "$2" > "{prompt_log}"\ncat "{out}"')
    plan = ClaudeCliProducer().produce("Context 内容", "写一版脚本")
    assert plan.provider == "claude-cli"
    assert plan.script == "第一句\n第二句"
    assert [shot.voiceover for shot in plan.shots] == ["第一句", "第二句"]
    assert plan.claims == ("同杯直饮",)
    prompt = prompt_log.read_text()
    assert "本次目标：写一版脚本" in prompt
    assert "只输出一个符合下述 JSON Schema 的 JSON 对象" in prompt


def test_claude_envelope_with_fenced_result_is_parsed(tmp_path, monkeypatch):
    fenced = f"```json\n{json.dumps(PLAN, ensure_ascii=False)}\n```"
    envelope = {"type": "result", "result": fenced}
    out = tmp_path / "claude-out.json"
    out.write_text(json.dumps(envelope, ensure_ascii=False))
    _install(tmp_path, monkeypatch, "claude", f'cat "{out}"')
    plan = ClaudeCliProducer().produce("Context", "写一版")
    assert plan.script == "第一句\n第二句"


def test_codex_noisy_output_takes_last_plan_object(tmp_path, monkeypatch):
    decoy = json.dumps({"status": "ok", "shots": "不是数组"})
    trailing = json.dumps({"tokens_used": 4096})
    out = tmp_path / "codex-out.txt"
    out.write_text(
        "workdir: /tmp\n"
        f"{decoy}\n"
        "思考中……\n"
        f"{json.dumps(PLAN, ensure_ascii=False)}\n"
        f"{trailing}\n"
        "tokens used: 4096\n"
    )
    _install(tmp_path, monkeypatch, "codex", f'cat "{out}"')
    plan = CodexCliProducer().produce("Context", "写一版")
    assert plan.provider == "codex-cli"
    assert plan.script == "第一句\n第二句"
    assert len(plan.shots) == 2


def test_timeout_raises_human_error(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "claude", "exec sleep 5")
    monkeypatch.setenv("VIDEO_OPS_CLI_TIMEOUT", "0.5")
    with pytest.raises(ApplicationError) as excinfo:
        ClaudeCliProducer().produce("Context", "写一版")
    assert excinfo.value.code == "model_failed"
    assert "秒内没写完脚本" in excinfo.value.message


def test_nonzero_exit_raises_human_error(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "codex", "exit 3")
    with pytest.raises(ApplicationError) as excinfo:
        CodexCliProducer().produce("Context", "写一版")
    assert excinfo.value.code == "model_failed"
    assert "执行失败" in excinfo.value.message


def test_unusable_json_raises_human_error(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "claude", 'echo "今天天气不错，没有脚本。"')
    with pytest.raises(ApplicationError) as excinfo:
        ClaudeCliProducer().produce("Context", "写一版")
    assert excinfo.value.code == "model_empty"
    assert "没有返回可用的脚本" in excinfo.value.message


def test_invalid_plan_shape_raises_human_error(tmp_path, monkeypatch):
    broken = {"script": "只有一句", "shots": [{"duration_seconds": 3, "visual": "画面"}]}
    out = tmp_path / "claude-out.json"
    out.write_text(json.dumps({"result": json.dumps(broken, ensure_ascii=False)}))
    _install(tmp_path, monkeypatch, "claude", f'cat "{out}"')
    with pytest.raises(ApplicationError) as excinfo:
        ClaudeCliProducer().produce("Context", "写一版")
    assert excinfo.value.code == "model_empty"


@pytest.mark.parametrize("producer_cls", [ClaudeCliProducer, CodexCliProducer])
def test_missing_command_rejected_at_construction(tmp_path, monkeypatch, producer_cls):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ApplicationError) as excinfo:
        producer_cls()
    assert excinfo.value.code == "unsupported"
    assert "没有安装" in excinfo.value.message
