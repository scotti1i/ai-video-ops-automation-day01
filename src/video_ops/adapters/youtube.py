"""对既有 YouTube uploader 的进程适配器。"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic

from video_ops.application.errors import PlatformError
from video_ops.domain.models import CommentSnapshot, MetricSnapshot

DONE_PATTERN = re.compile(r"DONE https://youtu\.be/([\w-]+)")
CACHE_SECONDS = 5.0
COMMENT_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _connector_path(raw: str, app_root: Path) -> Path:
    path = Path(raw).expanduser()
    return path.resolve() if path.is_absolute() else (app_root / path).resolve()


def _publish_failure(output: str) -> tuple[str, str]:
    checks = [
        (
            "视频上传完成" in output,
            "unknown_outcome",
            "YouTube 已可能创建视频，但未得到完成回执，核对前不会重试。",
        ),
        ("频道不匹配" in output, "account_mismatch", "YouTube 授权频道与目标账号不一致。"),
        (
            "授权" in output or "token" in output.lower(),
            "auth_required",
            "YouTube 授权不足或已失效。",
        ),
        (
            any(marker in output for marker in ("缺视频", "缺封面", "缺简介")),
            "invalid_input",
            "YouTube 发布输入不完整。",
        ),
        (True, "unknown_outcome", "YouTube 发布没有得到可确认的结果，核对前不会重试。"),
    ]
    return next((code, message) for matched, code, message in checks if matched)


@dataclass(frozen=True)
class _CacheEntry:
    payload: dict
    expires_at: float


class YouTubePlatformAdapter:
    platform = "youtube"

    def __init__(
        self,
        uploader_dir: Path,
        expected_channel: str,
        evidence_dir: Path,
        bridge_script: Path,
        comment_token_path: Path | None = None,
    ):
        self.uploader_dir = uploader_dir
        self.expected_channel = expected_channel.strip()
        self.evidence_dir = evidence_dir
        self.bridge_script = bridge_script
        self.comment_token_path = comment_token_path
        self._collection_cache: dict[str, _CacheEntry] = {}

    @classmethod
    def from_environment(cls, app_root: Path):
        directory = os.getenv("YOUTUBE_UPLOAD_DIR", "")
        expected = os.getenv("YOUTUBE_EXPECTED_CHANNEL", "")
        comment_token = os.getenv("YOUTUBE_COMMENT_TOKEN_PATH", "").strip()
        if not directory:
            return None
        return cls(
            uploader_dir=_connector_path(directory, app_root),
            expected_channel=expected,
            evidence_dir=app_root / ".local" / "youtube-evidence",
            bridge_script=app_root / "scripts" / "youtube_bridge.py",
            comment_token_path=(
                _connector_path(comment_token, app_root) if comment_token else None
            ),
        )

    def capabilities(self) -> dict[str, bool]:
        return {
            "publish": True,
            "schedule": True,
            "thumbnail": False,
            "basic_metrics": True,
            "comments": self._has_comment_scope(),
            "analytics": False,
        }

    def inspect_account(self, connector_ref: str | None) -> dict:
        payload, raw_ref = self._bridge("inspect")
        channels = payload.get("channels", [])
        channel = self._match_channel(channels, connector_ref or self.expected_channel)
        return {
            "platform_account_id": channel["id"],
            "display_name": channel["title"],
            "handle": channel.get("handle", ""),
            "raw_ref": raw_ref,
        }

    def publish(self, request: dict) -> dict:
        self._validate_publish(request)
        account = self.inspect_account(request.get("account_ref"))
        self._secure_connector_files("publish")
        self._prepare_evidence_dir()
        description = self.evidence_dir / f"{request['idempotency_key']}.description.txt"
        description.write_text(request["description"], encoding="utf-8")
        description.chmod(0o600)
        command = self._publish_command(request, description, account["platform_account_id"])
        try:
            result = subprocess.run(
                command,
                cwd=self.uploader_dir,
                capture_output=True,
                text=True,
                timeout=7200,
                check=False,
                umask=0o077,
            )
        except subprocess.TimeoutExpired as exc:
            return self._handle_publish_timeout(request, exc)
        except OSError as exc:
            raise PlatformError(
                "publish",
                "connector_unavailable",
                "YouTube uploader 无法启动，请运行 doctor 检查其自带 venv。",
            ) from exc
        raw_ref = self._save_raw("publish", result.stdout, result.stderr)
        match = DONE_PATTERN.search(result.stdout)
        if not match:
            self._raise_publish_error(result, raw_ref)
        warnings = self._publish_warnings(result.stdout, result.stderr)
        if result.returncode:
            warnings.append(f"uploader 退出码为 {result.returncode}，但已收到平台视频编号。")
        return self._publish_receipt(request, match.group(1), warnings, raw_ref)

    def _publish_receipt(
        self,
        request: dict,
        video_id: str,
        warnings: list[str],
        raw_ref: str,
    ) -> dict:
        if not request.get("scheduled_at"):
            warnings.append("YouTube 安全默认：视频以 private 上传，未对外公开。")
        warnings = list(dict.fromkeys(warnings))
        if request.get("scheduled_at"):
            state = "scheduled"
        else:
            state = "succeeded_with_warnings" if warnings else "succeeded"
        return {
            "state": state,
            "platform_content_id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "published_at": None if request.get("scheduled_at") else _now(),
            "warnings": warnings,
            "raw_ref": raw_ref,
        }

    def _handle_publish_timeout(
        self,
        request: dict,
        exc: subprocess.TimeoutExpired,
    ) -> dict:
        stdout = self._timeout_output(exc.stdout)
        stderr = self._timeout_output(exc.stderr)
        raw_ref = self._save_raw("publish-timeout", stdout, stderr)
        match = DONE_PATTERN.search(stdout)
        if match:
            warnings = self._publish_warnings(stdout, stderr)
            warnings.append("uploader 超时退出，但已收到平台视频编号。")
            return self._publish_receipt(request, match.group(1), warnings, raw_ref)
        raise PlatformError(
            "publish",
            "unknown_outcome",
            "YouTube 上传超时，平台结果未知；核对前不会自动重试。",
            raw_ref=raw_ref,
        )

    def get_publication(self, external_id: str) -> dict:
        payload = self._collect(external_id)
        video = payload["video"]
        scheduled = (
            video.get("privacy_status") == "private"
            and bool(video.get("publish_at"))
        )
        return {
            "state": "scheduled" if scheduled else "succeeded",
            "platform_content_id": external_id,
            "url": f"https://youtu.be/{external_id}",
            "published_at": None if scheduled else video.get("published_at"),
            "platform_state": video.get("privacy_status"),
            "publish_at": video.get("publish_at"),
        }

    def collect_metrics(
        self,
        publication_id: str,
        external_id: str,
        previous: MetricSnapshot | None = None,
    ) -> MetricSnapshot:
        del previous
        payload = self._collect(external_id)
        statistics = payload["video"].get("statistics", {})
        captured = _now()
        return MetricSnapshot(
            id=f"metric-{sha256((publication_id + captured).encode()).hexdigest()[:16]}",
            publication_id=publication_id,
            captured_at=captured,
            views=self._optional_int(statistics.get("viewCount")),
            likes=self._optional_int(statistics.get("likeCount")),
            comments=self._optional_int(statistics.get("commentCount")),
            raw={"youtube": statistics},
        )

    def collect_comments(
        self,
        publication_id: str,
        external_id: str,
    ) -> tuple[list[CommentSnapshot], str | None]:
        payload = self._collect(external_id)
        captured = _now()
        comments = [
            CommentSnapshot(
                id=f"comment-{sha256((publication_id + item['id']).encode()).hexdigest()[:16]}",
                publication_id=publication_id,
                external_id=item["id"],
                author=item["author"],
                content=item["content"],
                likes=int(item.get("likes", 0)),
                commented_at=item.get("published_at") or captured,
                captured_at=captured,
                raw={
                    "total_reply_count": item.get("total_reply_count", 0),
                    "replies_included": item.get("replies_included", 0),
                },
            )
            for item in payload.get("comments", [])
        ]
        return comments, payload.get("comments_unavailable_reason")

    def _collect(self, external_id: str) -> dict:
        cached = self._collection_cache.get(external_id)
        if cached and cached.expires_at > monotonic():
            return cached.payload
        payload, _ = self._bridge("collect", "--video-id", external_id)
        self._collection_cache[external_id] = _CacheEntry(
            payload=payload,
            expires_at=monotonic() + CACHE_SECONDS,
        )
        return payload

    def _bridge(self, *args: str) -> tuple[dict, str]:
        python = self.uploader_dir / ".venv" / "bin" / "python"
        if not python.exists() or not self.bridge_script.exists():
            raise PlatformError(
                args[0],
                "connector_unavailable",
                "YouTube 连接器必须使用 uploader 自带的 .venv Python；请运行 doctor。",
            )
        command = [
            str(python),
            str(self.bridge_script),
            "--uploader-dir",
            str(self.uploader_dir),
        ]
        if self.comment_token_path:
            command.extend(["--comment-token", str(self.comment_token_path)])
        command.extend(args)
        result = self._run_bridge(args[0], command)
        return self._parse_bridge_result(args[0], result)

    def _has_comment_scope(self) -> bool:
        token = self.comment_token_path or self.uploader_dir / "token.json"
        try:
            payload = json.loads(token.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return COMMENT_SCOPE in set(payload.get("scopes") or [])

    def _run_bridge(
        self,
        operation: str,
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        self._secure_connector_files(operation)
        try:
            return subprocess.run(
                command,
                cwd=self.uploader_dir,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
                umask=0o077,
            )
        except subprocess.TimeoutExpired as exc:
            raw_ref = self._save_raw(
                f"{operation}-timeout",
                self._timeout_output(exc.stdout),
                self._timeout_output(exc.stderr),
            )
            raise PlatformError(
                operation,
                "timeout",
                "YouTube 只读调用超时，可以安全重试。",
                retryable=True,
                raw_ref=raw_ref,
            ) from exc
        except OSError as exc:
            raise PlatformError(
                operation,
                "connector_unavailable",
                "YouTube uploader 自带 venv 无法启动。",
            ) from exc

    def _parse_bridge_result(
        self,
        operation: str,
        result: subprocess.CompletedProcess[str],
    ) -> tuple[dict, str]:
        raw_ref = self._save_raw(operation, result.stdout, result.stderr)
        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise PlatformError(
                operation,
                "invalid_response",
                "YouTube 工具没有返回可解析结果。",
                raw_ref=raw_ref,
            ) from exc
        if result.returncode or not payload.get("ok"):
            raise PlatformError(
                operation,
                payload.get("code", "youtube_error"),
                payload.get("message", "YouTube 调用失败"),
                retryable=bool(payload.get("retryable", False)),
                raw_ref=raw_ref,
            )
        return payload, raw_ref

    def _match_channel(self, channels: list[dict], expected: str) -> dict:
        if not expected:
            raise PlatformError(
                "inspect_account",
                "account_required",
                "必须配置准确的 YouTube 频道 ID、名称或 handle。",
            )
        matches = [
            item
            for item in channels
            if expected in {item.get("id"), item.get("title"), item.get("handle")}
        ]
        if len(matches) != 1:
            raise PlatformError(
                "inspect_account",
                "account_mismatch",
                "当前授权频道与指定账号不一致。",
            )
        return matches[0]

    def _publish_command(self, request: dict, description: Path, channel_id: str) -> list[str]:
        python = self.uploader_dir / ".venv" / "bin" / "python"
        command = [
            str(python),
            str(self.uploader_dir / "publish_single.py"),
            "--video",
            request["media_path"],
            "--title",
            request["title"],
            "--description-file",
            str(description),
            "--expected-channel",
            channel_id,
            "--privacy",
            "private",
        ]
        if request.get("scheduled_at"):
            command.extend(["--publish-at", request["scheduled_at"]])
        return command

    def _validate_publish(self, request: dict) -> None:
        python = self.uploader_dir / ".venv" / "bin" / "python"
        uploader = self.uploader_dir / "publish_single.py"
        if not python.exists() or not uploader.exists():
            raise PlatformError(
                "publish",
                "connector_unavailable",
                "YouTube 发布必须使用 uploader 自带的 .venv Python。",
            )
        media = Path(request["media_path"])
        if not media.exists():
            raise PlatformError("publish", "invalid_input", "成片文件不存在，请重新上传。")
        if not 1 <= len(request["title"]) <= 100:
            raise PlatformError("publish", "invalid_input", "YouTube 标题必须为 1 到 100 个字符。")
        if not request["description"].strip():
            raise PlatformError("publish", "invalid_input", "YouTube 简介不能为空。")

    def _raise_publish_error(self, result: subprocess.CompletedProcess, raw_ref: str) -> None:
        code, message = _publish_failure(f"{result.stdout}\n{result.stderr}")
        raise PlatformError(
            "publish",
            code,
            message,
            retryable=False,
            raw_ref=raw_ref,
        )

    def _save_raw(self, operation: str, stdout: str, stderr: str) -> str:
        self._prepare_evidence_dir()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        path = self.evidence_dir / f"{stamp}-{operation}.json"
        payload = json.dumps(
            {"stdout": stdout, "stderr": stderr},
            ensure_ascii=False,
        )
        path.write_text(payload, encoding="utf-8")
        path.chmod(0o600)
        return str(path.relative_to(self.evidence_dir.parent.parent))

    def _prepare_evidence_dir(self) -> None:
        self.evidence_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.evidence_dir.chmod(0o700)

    def _secure_connector_files(self, operation: str) -> None:
        paths = [
            self.uploader_dir / "token.json",
            self.uploader_dir / "client_secrets.json",
        ]
        if self.comment_token_path:
            paths.append(self.comment_token_path)
        try:
            for path in paths:
                if path.is_file():
                    path.chmod(0o600)
        except OSError as exc:
            raise PlatformError(
                operation,
                "insecure_connector",
                "YouTube 凭据文件无法收紧为仅当前用户可读。",
            ) from exc

    @staticmethod
    def _publish_warnings(stdout: str, stderr: str) -> list[str]:
        lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        lines.extend(
            line.strip()
            for line in stdout.splitlines()
            if "失败" in line or "warning" in line.lower()
        )
        return list(dict.fromkeys(lines))

    @staticmethod
    def _timeout_output(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    @staticmethod
    def _optional_int(value: str | int | None) -> int | None:
        return None if value is None else int(value)
