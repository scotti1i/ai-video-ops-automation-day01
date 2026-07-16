"""本地开发入口：环境诊断、零密钥 demo、持久工作区和质量门禁。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import uvicorn

from video_ops.api.app import create_app
from video_ops.config import Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video-ops", description="AI 视频运营流水线")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="检查本地运行条件")
    doctor.add_argument("--json", action="store_true", help="输出 JSON")
    for name, help_text in (("demo", "启动零密钥样例"), ("run", "启动持久工作区")):
        command = commands.add_parser(name, help=help_text)
        default_api = int(os.getenv("VIDEO_OPS_API_PORT", "8787"))
        default_web = int(os.getenv("VIDEO_OPS_WEB_PORT", "5173"))
        command.add_argument("--host", default=os.getenv("VIDEO_OPS_API_HOST", "127.0.0.1"))
        command.add_argument("--api-port", type=int, default=default_api)
        command.add_argument("--web-port", type=int, default=default_web)
        command.add_argument("--api-only", action="store_true")
        command.add_argument("--no-worker", action="store_true")
    commands.add_parser("check", help="运行后端与前端质量门禁")
    comment_auth = commands.add_parser("youtube-comment-auth", help="创建独立评论读取授权")
    comment_auth.add_argument("--uploader-dir", default=os.getenv("YOUTUBE_UPLOAD_DIR", ""))
    comment_auth.add_argument("--output", default=".local/youtube-comment-token.json")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "doctor":
        return _doctor(as_json=args.json)
    if args.command == "check":
        return _check()
    if args.command == "youtube-comment-auth":
        return _youtube_comment_auth(args)
    return _serve(args, mode="demo" if args.command == "demo" else "live")


def _youtube_comment_auth(args: argparse.Namespace) -> int:
    if not args.uploader_dir:
        raise SystemExit("请传 --uploader-dir 或设置 YOUTUBE_UPLOAD_DIR。")
    settings = Settings.from_environment()
    uploader = Path(args.uploader_dir).expanduser()
    python = uploader / ".venv/bin/python"
    script = settings.app_root / "scripts/youtube_comment_auth.py"
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = settings.app_root / output
    if not python.is_file():
        raise SystemExit("uploader 自带的 .venv Python 不存在。")
    client_secrets = uploader / "client_secrets.json"
    if client_secrets.is_file():
        client_secrets.chmod(0o600)
    result = subprocess.run(
        [str(python), str(script), "--uploader-dir", str(uploader), "--output", str(output)],
        cwd=settings.app_root,
        check=False,
        umask=0o077,
    )
    return result.returncode


def _doctor(*, as_json: bool) -> int:
    settings = Settings.from_environment()
    checks = _base_checks(settings)
    checks.extend(_youtube_checks(settings))
    ok = all(item["ok"] for item in checks if item["required"])
    if as_json:
        print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    else:
        _print_checks(checks, ok)
    return 0 if ok else 1


def _base_checks(settings: Settings) -> list[dict]:
    dependency_names = ("fastapi", "pydantic", "uvicorn", "multipart")
    dependencies = all(importlib.util.find_spec(name) for name in dependency_names)
    return [
        _check_result("Python", sys.version_info >= (3, 12), ">= 3.12", True),
        _check_result("后端依赖", dependencies, "uv sync", True),
        _check_result("样例数据", settings.sample_seed.is_file(), str(settings.sample_seed), True),
        _check_result(
            "package.json",
            (settings.app_root / "package.json").is_file(),
            "前端工程",
            True,
        ),
        _check_result(
            "node",
            shutil.which("node") is not None,
            shutil.which("node") or "未找到",
            True,
        ),
        _check_result(
            "npm",
            shutil.which("npm") is not None,
            shutil.which("npm") or "未找到",
            True,
        ),
        _check_result(
            "前端依赖",
            (settings.app_root / "node_modules").is_dir(),
            (
                "已就绪"
                if (settings.app_root / "node_modules").is_dir()
                else "请在应用目录运行 npm install"
            ),
            True,
        ),
        _check_result(
            "运行目录",
            os.access(settings.app_root, os.W_OK),
            str(settings.app_root),
            True,
        ),
    ]


def _youtube_checks(settings: Settings) -> list[dict]:
    raw = os.getenv("YOUTUBE_UPLOAD_DIR", "").strip()
    if not raw:
        return [
            _check_result("YouTube 连接器", True, "未配置（可选）", False),
            _youtube_comment_check(),
        ]
    directory = Path(raw).expanduser()
    expected = os.getenv("YOUTUBE_EXPECTED_CHANNEL", "").strip()
    checks = [
        _check_result(
            "YouTube uploader",
            (directory / "publish_single.py").is_file(),
            str(directory),
            True,
        ),
        _check_result(
            "YouTube Python",
            (directory / ".venv/bin/python").is_file(),
            str(directory / ".venv/bin/python"),
            True,
        ),
        _youtube_credentials_check(directory),
        _check_result(
            "YouTube 频道锁定",
            bool(expected),
            "已配置" if expected else "缺少频道 ID/handle",
            True,
        ),
        _check_result(
            "YouTube 读桥接",
            (settings.app_root / "scripts/youtube_bridge.py").is_file(),
            "scripts/youtube_bridge.py",
            True,
        ),
    ]
    checks.append(_youtube_comment_check())
    return checks


def _youtube_credentials_check(directory: Path) -> dict:
    paths = [directory / "token.json", directory / "client_secrets.json"]
    if not all(path.is_file() for path in paths):
        return _check_result("YouTube 凭据", False, "缺少本地授权文件", True)
    secure = all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in paths)
    return _check_result(
        "YouTube 凭据",
        secure,
        "权限 0600" if secure else "权限必须收紧为 0600",
        True,
    )


def _youtube_comment_check() -> dict:
    raw = os.getenv("YOUTUBE_COMMENT_TOKEN_PATH", "").strip()
    if not raw:
        return _check_result("YouTube 评论读取", True, "未配置（可选）", False)
    path = Path(raw).expanduser()
    if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        return _check_result(
            "YouTube 评论读取",
            False,
            "token 不存在或权限不是 0600",
            False,
        )
    try:
        scopes = set(json.loads(path.read_text(encoding="utf-8")).get("scopes") or [])
    except (OSError, json.JSONDecodeError):
        return _check_result("YouTube 评论读取", False, "token 不可读取", False)
    scope = "https://www.googleapis.com/auth/youtube.force-ssl"
    return _check_result(
        "YouTube 评论读取",
        scope in scopes,
        "授权完整" if scope in scopes else "缺少 youtube.force-ssl",
        False,
    )


def _check_result(name: str, ok: bool, detail: str, required: bool) -> dict:
    return {"name": name, "ok": ok, "detail": detail, "required": required}


def _print_checks(checks: list[dict], ok: bool) -> None:
    for item in checks:
        marker = "PASS" if item["ok"] else "FAIL"
        optional = " · 可选" if not item["required"] else ""
        print(f"[{marker}] {item['name']}{optional} — {item['detail']}")
    print("环境可运行。" if ok else "环境尚未就绪，请处理 FAIL 项。")


def _serve(args: argparse.Namespace, *, mode: str) -> int:
    _require_loopback_host(args.host)
    _set_runtime_environment(args, mode)
    settings = Settings.from_environment()
    frontend = None
    if not args.api_only:
        frontend = _start_frontend(settings)
    label = "零密钥样例" if mode == "demo" else "本地工作区"
    print(f"{label}：http://localhost:{settings.web_port}")
    print(f"API：http://localhost:{settings.api_port}/api/health")
    try:
        uvicorn.run(
            create_app(settings),
            host=settings.api_host,
            port=settings.api_port,
            log_level="info",
        )
    finally:
        _stop_process(frontend)
    return 0


def _require_loopback_host(host: str) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Day 1 含本地写入和真实发布能力，只允许监听 loopback 地址。")


def _set_runtime_environment(args: argparse.Namespace, mode: str) -> None:
    os.environ["VIDEO_OPS_MODE"] = mode
    os.environ["VIDEO_OPS_API_HOST"] = args.host
    os.environ["VIDEO_OPS_WEB_HOST"] = args.host
    os.environ["VIDEO_OPS_API_PORT"] = str(args.api_port)
    os.environ["VIDEO_OPS_WEB_PORT"] = str(args.web_port)
    if args.no_worker:
        os.environ["VIDEO_OPS_WORKER_ENABLED"] = "false"


def _start_frontend(settings: Settings) -> subprocess.Popen:
    if not (settings.app_root / "node_modules").is_dir():
        raise SystemExit("前端依赖未就绪：请在当前应用目录运行 npm install。")
    command = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        settings.web_host,
        "--port",
        str(settings.web_port),
    ]
    return subprocess.Popen(command, cwd=settings.app_root)


def _stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _check() -> int:
    settings = Settings.from_environment()
    commands = [
        [sys.executable, "-m", "ruff", "check", "src", "tests"],
        [sys.executable, "-m", "pytest"],
        ["npm", "run", "check"],
    ]
    for command in commands:
        print(f"$ {' '.join(command)}")
        result = subprocess.run(command, cwd=settings.app_root, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
