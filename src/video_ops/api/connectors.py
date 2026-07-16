"""「连接与配置」页的状态汇总：写脚本引擎、发布平台、数据同步。"""

from __future__ import annotations

import logging
import os

from video_ops.adapters.cli_producers import cli_available
from video_ops.config import Settings

LOGGER = logging.getLogger(__name__)

_OPENAI_HOW = (
    "export OPENAI_API_KEY=sk-...\n"
    "export OPENAI_BASE_URL=https://... # 可选，兼容中继\n"
    "export OPENAI_MODEL=gpt-... # 可选\n"
    "uv run video-ops run"
)
_YOUTUBE_HOW = (
    "export YOUTUBE_UPLOAD_DIR=...\nexport YOUTUBE_EXPECTED_CHANNEL=...\nuv run video-ops run"
)
_YOUTUBE_COMMENTS_HOW = (
    "uv run video-ops youtube-comment-auth --uploader-dir ...\n"
    "export YOUTUBE_COMMENT_TOKEN_PATH=.local/youtube-comment-token.json"
)
_CUSTOM_HOW = "见 README「其他平台与飞书」——按平台接口合同写一个适配器类"


def _producer_available(producer: str) -> bool:
    checks = {
        "mock": lambda: True,
        "openai": lambda: bool(os.getenv("OPENAI_API_KEY")),
        "claude-cli": lambda: cli_available("claude"),
        "codex-cli": lambda: cli_available("codex"),
    }
    check = checks.get(producer)
    return check() if check else False


def resolve_active_script_producer(settings: Settings) -> str:
    """demo 恒用 mock；run 模式按环境变量选，选中的引擎不可用时回退 mock。"""
    if settings.mode == "demo":
        return "mock"
    requested = settings.script_producer
    if _producer_available(requested):
        return requested
    LOGGER.warning(
        "写脚本引擎 %s 当前不可用（命令未安装或密钥未配置），已回退到内置示例模板。",
        requested,
    )
    return "mock"


def _status(producer: str, active: str, available: bool) -> str:
    if producer == active:
        return "active"
    if producer == "mock":
        return "ready"
    if producer == "openai":
        return "ready" if available else "unconfigured"
    return "detected" if available else "missing"


def _script_options(active: str) -> list[dict]:
    has_key = bool(os.getenv("OPENAI_API_KEY"))
    has_claude = cli_available("claude")
    has_codex = cli_available("codex")
    return [
        {
            "id": "mock",
            "label": "内置示例模板",
            "status": _status("mock", active, True),
            "detail": "零密钥可用，演示模式默认",
            "how": None,
        },
        {
            "id": "openai",
            "label": "OpenAI 兼容 API",
            "status": _status("openai", active, has_key),
            "detail": "密钥已配置，可以直接用" if has_key else "OPENAI_API_KEY 未设置",
            "how": None if has_key else _OPENAI_HOW,
        },
        {
            "id": "claude-cli",
            "label": "Claude Code 命令行",
            "status": _status("claude-cli", active, has_claude),
            "detail": (
                "检测到本机已安装 claude 命令"
                if has_claude
                else "本机没有安装 claude 命令，先装好并登录 Claude Code"
            ),
            "how": "export VIDEO_OPS_SCRIPT_PRODUCER=claude-cli\nuv run video-ops run",
        },
        {
            "id": "codex-cli",
            "label": "Codex 命令行",
            "status": _status("codex-cli", active, has_codex),
            "detail": (
                "检测到本机已安装 codex 命令"
                if has_codex
                else "本机没有安装 codex 命令，先装好并登录 Codex"
            ),
            "how": "export VIDEO_OPS_SCRIPT_PRODUCER=codex-cli\nuv run video-ops run",
        },
    ]


def _publish_platforms(loaded_platforms: set[str]) -> list[dict]:
    youtube_ready = "youtube" in loaded_platforms
    return [
        {
            "id": "mock-social",
            "label": "示例平台",
            "status": "ready",
            "detail": "内置，用来完整跑通流程",
            "how": None,
        },
        {
            "id": "youtube",
            "label": "YouTube",
            "status": "ready" if youtube_ready else "unconfigured",
            "detail": "上传目录已配置，可以发布" if youtube_ready else "未配置上传目录",
            "how": None if youtube_ready else _YOUTUBE_HOW,
        },
        {
            "id": "custom",
            "label": "自定义平台",
            "status": "contract",
            "detail": "实现 5 个方法就能接入：查账号、发布、查任务、拉数据、拉评论",
            "how": _CUSTOM_HOW,
        },
    ]


def _data_items(settings: Settings) -> list[dict]:
    minutes = max(1, round(settings.metric_sync_seconds / 60))
    has_comment_token = bool((os.getenv("YOUTUBE_COMMENT_TOKEN_PATH") or "").strip())
    return [
        {
            "id": "auto-sync",
            "label": "自动拉数据",
            "status": "ready",
            "detail": f"发布成功后，每 {minutes} 分钟自动拉一次播放、订单、评论",
            "how": None,
        },
        {
            "id": "manual-sync",
            "label": "手动拉数据",
            "status": "ready",
            "detail": "发布记录里点「同步数据」，立刻拉一次",
            "how": None,
        },
        {
            "id": "youtube-comments",
            "label": "YouTube 评论",
            "status": "ready" if has_comment_token else "unconfigured",
            "detail": "评论授权已配置" if has_comment_token else "要单独授权一次",
            "how": None if has_comment_token else _YOUTUBE_COMMENTS_HOW,
        },
    ]


def connectors_payload(settings: Settings, active: str, loaded_platforms: set[str]) -> dict:
    return {
        "script": {"active": active, "options": _script_options(active)},
        "publish": {"platforms": _publish_platforms(loaded_platforms)},
        "data": {"items": _data_items(settings)},
    }
