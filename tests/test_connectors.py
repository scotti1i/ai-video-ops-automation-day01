"""连接与配置接口：响应形状、demo 恒用 mock、引擎回退与生成端点校验。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from video_ops.api.app import create_app

STATUS_ENUM = {"active", "ready", "detected", "unconfigured", "missing", "contract"}
ITEM_KEYS = {"id", "label", "status", "detail", "how"}
CLEAN_ENV = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "YOUTUBE_UPLOAD_DIR",
    "YOUTUBE_EXPECTED_CHANNEL",
    "YOUTUBE_COMMENT_TOKEN_PATH",
    "VIDEO_OPS_SCRIPT_PRODUCER",
    "VIDEO_OPS_CLI_TIMEOUT",
    "VIDEO_OPS_METRIC_SYNC_SECONDS",
)


def _client(tmp_path, monkeypatch, mode: str = "demo", **env: str) -> TestClient:
    monkeypatch.setenv("VIDEO_OPS_MODE", mode)
    monkeypatch.setenv("VIDEO_OPS_DB_PATH", str(tmp_path / "workspace.db"))
    monkeypatch.setenv("VIDEO_OPS_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("VIDEO_OPS_WORKER_ENABLED", "0")
    for name in CLEAN_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return TestClient(create_app())


def test_connectors_shape_matches_contract(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = client.get("/api/connectors").json()
    assert set(payload) == {"script", "publish", "data"}
    assert set(payload["script"]) == {"active", "options"}
    options = payload["script"]["options"]
    assert [item["id"] for item in options] == ["mock", "openai", "claude-cli", "codex-cli"]
    platforms = payload["publish"]["platforms"]
    assert [item["id"] for item in platforms] == ["mock-social", "youtube", "custom"]
    items = payload["data"]["items"]
    assert [item["id"] for item in items] == ["auto-sync", "manual-sync", "youtube-comments"]
    for item in (*options, *platforms, *items):
        assert set(item) == ITEM_KEYS
        assert item["status"] in STATUS_ENUM
        assert item["how"] is None or isinstance(item["how"], str)


def test_demo_mode_active_is_mock_and_details_are_plain(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = client.get("/api/connectors").json()
    assert payload["script"]["active"] == "mock"
    options = {item["id"]: item for item in payload["script"]["options"]}
    assert options["mock"]["status"] == "active"
    assert options["mock"]["how"] is None
    assert options["openai"]["status"] == "unconfigured"
    assert options["openai"]["detail"] == "OPENAI_API_KEY 未设置"
    assert "OPENAI_API_KEY" in options["openai"]["how"]
    platforms = {item["id"]: item for item in payload["publish"]["platforms"]}
    assert platforms["mock-social"]["status"] == "ready"
    assert platforms["youtube"]["status"] == "unconfigured"
    assert platforms["youtube"]["detail"] == "未配置上传目录"
    assert platforms["custom"]["status"] == "contract"
    items = {item["id"]: item for item in payload["data"]["items"]}
    # demo 模式指标同步至少 30 分钟一次，detail 必须反映真实设置。
    assert "每 30 分钟" in items["auto-sync"]["detail"]
    assert items["youtube-comments"]["status"] == "unconfigured"


def test_workspace_reports_active_script_producer(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    workspace = client.get("/api/workspace").json()
    assert workspace["active_script_producer"] == "mock"


def test_run_mode_falls_back_to_mock_when_engine_unavailable(tmp_path, monkeypatch):
    client = _client(
        tmp_path,
        monkeypatch,
        mode="live",
        VIDEO_OPS_SCRIPT_PRODUCER="claude-cli",
        PATH=str(tmp_path),
    )
    workspace = client.get("/api/workspace").json()
    assert workspace["active_script_producer"] == "mock"
    payload = client.get("/api/connectors").json()
    assert payload["script"]["active"] == "mock"
    options = {item["id"]: item for item in payload["script"]["options"]}
    assert options["claude-cli"]["status"] == "missing"


def test_run_mode_uses_configured_engine_when_available(tmp_path, monkeypatch):
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    client = _client(
        tmp_path,
        monkeypatch,
        mode="live",
        VIDEO_OPS_SCRIPT_PRODUCER="claude-cli",
        PATH=str(tmp_path),
    )
    workspace = client.get("/api/workspace").json()
    assert workspace["active_script_producer"] == "claude-cli"
    payload = client.get("/api/connectors").json()
    assert payload["script"]["active"] == "claude-cli"
    options = {item["id"]: item for item in payload["script"]["options"]}
    assert options["claude-cli"]["status"] == "active"
    assert options["codex-cli"]["status"] == "missing"


def test_generate_batch_rejects_unknown_producer(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/batches/generate", json={"producer": "nope"})
    assert response.status_code == 400
    assert "写脚本引擎" in response.json()["error"]["message"]


def test_generate_batch_reports_uninstalled_cli_as_client_error(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, PATH=str(tmp_path))
    response = client.post("/api/batches/generate", json={"producer": "claude-cli"})
    assert response.status_code == 400
    assert "claude" in response.json()["error"]["message"]
