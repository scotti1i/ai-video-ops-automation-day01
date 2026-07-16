"""本机命令行写脚本引擎：复用已登录的 claude / codex 命令，不再单独配密钥。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from video_ops.adapters.script_producers import (
    GeneratedPlan,
    ProducedPlan,
    _coerce_plan,
    _domain_shots,
    plan_instructions,
)
from video_ops.application.errors import ApplicationError

_APP_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_TIMEOUT_SECONDS = 240.0


def cli_available(executable: str) -> bool:
    return shutil.which(executable) is not None


def cli_timeout_seconds() -> float:
    try:
        value = float(os.getenv("VIDEO_OPS_CLI_TIMEOUT", ""))
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_TIMEOUT_SECONDS


def _prompt(context: str, instruction: str) -> str:
    schema = json.dumps(GeneratedPlan.model_json_schema(), ensure_ascii=False)
    return (
        f"{plan_instructions(context)}\n\n"
        f"本次目标：{instruction}\n\nContext：\n{context}\n\n"
        "只输出一个符合下述 JSON Schema 的 JSON 对象，不要解释、不要 markdown 代码块。\n"
        f"JSON Schema：{schema}"
    )


def _balanced_objects(text: str) -> list[str]:
    """扫描文本中所有平衡的顶层 {...} 片段，忽略字符串内部的括号。"""
    fragments: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"' and depth > 0:
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                fragments.append(text[start : index + 1])
    return fragments


def _plan_dict(value: object) -> dict | None:
    """从解析结果中定位含 shots 的脚本对象，兼容命令行的 JSON 信封嵌套。"""
    if not isinstance(value, dict):
        return None
    if "shots" in value:
        return value
    result = value.get("result")
    if isinstance(result, str):
        return _search_plan(result)
    return _plan_dict(result)


def _search_plan(text: str) -> dict | None:
    """从裸 JSON、信封、代码块围栏或夹杂噪音的输出里提取脚本对象。"""
    for fragment in reversed(_balanced_objects(text)):
        try:
            parsed = json.loads(fragment)
        except json.JSONDecodeError:
            continue
        found = _plan_dict(parsed)
        if found is not None:
            return found
    return None


class _CliScriptProducer:
    name = ""
    executable = ""
    display = ""

    def __init__(self) -> None:
        if not cli_available(self.executable):
            raise ApplicationError(
                "unsupported",
                f"本机没有安装 {self.executable} 命令，装好并登录后再试，或换一个写脚本引擎。",
            )

    def _argv(self, prompt: str) -> list[str]:
        raise NotImplementedError

    def produce(self, context: str, instruction: str) -> ProducedPlan:
        stdout = self._run(_prompt(context, instruction))
        plan = self._parse(stdout)
        return ProducedPlan(
            script=plan.script,
            shots=_domain_shots(plan.shots),
            provider=self.name,
            hook=plan.hook,
            primary_promise=plan.primary_promise,
            proof=plan.proof,
            objection=plan.objection,
            cta=plan.cta,
            claims=tuple(plan.claims),
        )

    def _run(self, prompt: str) -> str:
        timeout = cli_timeout_seconds()
        try:
            completed = subprocess.run(
                self._argv(prompt),
                cwd=_APP_ROOT,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                close_fds=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ApplicationError(
                "model_failed",
                f"{self.display}在 {timeout:g} 秒内没写完脚本，请重试或换一个引擎。",
                retryable=True,
            ) from exc
        if completed.returncode != 0:
            raise ApplicationError(
                "model_failed",
                f"{self.display}执行失败，请重试或换一个引擎。",
                retryable=True,
            )
        return completed.stdout

    def _parse(self, stdout: str) -> GeneratedPlan:
        payload = _search_plan(stdout)
        try:
            plan = _coerce_plan(payload)
        except Exception as exc:
            raise self._empty_error() from exc
        if plan is None:
            raise self._empty_error()
        return plan

    def _empty_error(self) -> ApplicationError:
        return ApplicationError(
            "model_empty",
            f"{self.display}没有返回可用的脚本，请重试或换一个引擎。",
            retryable=True,
        )


class ClaudeCliProducer(_CliScriptProducer):
    name = "claude-cli"
    executable = "claude"
    display = "Claude 命令行"

    def _argv(self, prompt: str) -> list[str]:
        return [self.executable, "-p", prompt, "--output-format", "json"]


class CodexCliProducer(_CliScriptProducer):
    name = "codex-cli"
    executable = "codex"
    display = "Codex 命令行"

    def _argv(self, prompt: str) -> list[str]:
        return [self.executable, "exec", prompt]
