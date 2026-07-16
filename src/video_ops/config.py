"""运行配置只读环境变量，不接触密钥明文。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _path_from_env(name: str, default: Path, app_root: Path) -> Path:
    raw = os.getenv(name)
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else app_root / path


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _metric_sync_seconds(mode: str) -> float:
    """demo 模式指标同步至少 30 分钟一次，避免快照灌爆演示库。"""
    configured = float(os.getenv("VIDEO_OPS_METRIC_SYNC_SECONDS", "300"))
    return max(configured, 1800.0) if mode == "demo" else configured


@dataclass(frozen=True, slots=True)
class Settings:
    app_root: Path
    mode: str
    database_path: Path
    upload_dir: Path
    sample_seed: Path
    api_host: str
    api_port: int
    web_host: str
    web_port: int
    worker_enabled: bool
    worker_poll_seconds: float
    metric_sync_seconds: float
    max_upload_bytes: int
    script_producer: str
    cli_timeout_seconds: float

    @classmethod
    def from_environment(cls) -> Settings:
        app_root = Path(__file__).resolve().parents[2]
        mode = os.getenv("VIDEO_OPS_MODE", "live").strip().lower()
        default_db = app_root / ("output/demo.db" if mode == "demo" else ".local/workspace.db")
        default_uploads = app_root / (
            "output/uploads" if mode == "demo" else ".local/uploads"
        )
        return cls(
            app_root=app_root,
            mode=mode,
            database_path=_path_from_env("VIDEO_OPS_DB_PATH", default_db, app_root),
            upload_dir=_path_from_env(
                "VIDEO_OPS_UPLOAD_DIR",
                default_uploads,
                app_root,
            ),
            sample_seed=app_root / "data/sample/workspace-seed.json",
            api_host=os.getenv("VIDEO_OPS_API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("VIDEO_OPS_API_PORT", "8787")),
            web_host=os.getenv("VIDEO_OPS_WEB_HOST", "127.0.0.1"),
            web_port=int(os.getenv("VIDEO_OPS_WEB_PORT", "5173")),
            worker_enabled=_bool_from_env("VIDEO_OPS_WORKER_ENABLED", True),
            worker_poll_seconds=float(os.getenv("VIDEO_OPS_WORKER_POLL_SECONDS", "30")),
            metric_sync_seconds=_metric_sync_seconds(mode),
            max_upload_bytes=int(os.getenv("VIDEO_OPS_MAX_UPLOAD_BYTES", str(2 * 1024**3))),
            script_producer=(os.getenv("VIDEO_OPS_SCRIPT_PRODUCER") or "openai").strip().lower(),
            cli_timeout_seconds=float(os.getenv("VIDEO_OPS_CLI_TIMEOUT") or "240"),
        )

    @property
    def web_origin(self) -> str:
        return f"http://{self.web_host}:{self.web_port}"
