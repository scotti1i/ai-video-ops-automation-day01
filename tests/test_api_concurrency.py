"""API 不应让长时间外部调用占住事件循环。"""

from __future__ import annotations

import asyncio
import stat
from io import BytesIO
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from video_ops.api import app as api_app
from video_ops.api.app import (
    _confirm_absent,
    _execute,
    _generate,
    _register_error_handlers,
    _register_routes,
    _registered_media_path,
    _store_upload,
    _sync,
    _upload_directory,
    _upload_media,
)
from video_ops.api.schemas import (
    ConfirmPublicationAbsentRequest,
    ExecutePublicationRequest,
    GenerateArtifactsRequest,
)
from video_ops.application.errors import ApplicationError
from video_ops.config import Settings


class SlowService:
    script_producer_factories = {"mock": object, "openai": object}

    def __init__(self) -> None:
        self.confirmed: bool | None = None

    def execute_publication(self, publication_id: str, *, confirmed: bool):
        self.confirmed = confirmed
        sleep(0.25)
        return {"id": publication_id, "status": "succeeded"}

    def generate_artifacts(self, video_id: str, *, instruction: str, producer: str):
        sleep(0.25)
        return {"id": video_id, "instruction": instruction, "producer": producer}

    def sync_publication(self, publication_id: str):
        sleep(0.25)
        return {"id": publication_id, "status": "succeeded"}


def _request(service: SlowService):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(service=service)))


async def _assert_event_loop_stays_responsive(coroutine) -> dict:
    started = monotonic()
    task = asyncio.create_task(coroutine)
    await asyncio.sleep(0.03)
    assert monotonic() - started < 0.15
    return await task


def test_execute_and_generate_run_outside_event_loop() -> None:
    service = SlowService()

    async def scenario() -> None:
        executed = await _assert_event_loop_stays_responsive(
            _execute(
                "publication-1",
                ExecutePublicationRequest(confirmed=True),
                _request(service),
            )
        )
        generated = await _assert_event_loop_stays_responsive(
            _generate(
                "video-1",
                GenerateArtifactsRequest(instruction="改写开头", producer="openai"),
                _request(service),
            )
        )
        synced = await _assert_event_loop_stays_responsive(
            _sync("publication-1", _request(service))
        )
        assert executed["status"] == "succeeded"
        assert generated["producer"] == "openai"
        assert synced["status"] == "succeeded"

    asyncio.run(scenario())
    assert service.confirmed is True


def test_large_media_copy_runs_outside_event_loop(tmp_path: Path, monkeypatch) -> None:
    def slow_copy(_source, target: Path, _limit: int):
        sleep(0.25)
        target.write_bytes(b"video")
        return 5, "checksum"

    monkeypatch.setattr(api_app, "_copy_upload", slow_copy)
    upload = SimpleNamespace(
        filename="video.mp4",
        content_type="video/mp4",
        file=BytesIO(b"video"),
        close=lambda: asyncio.sleep(0),
    )
    settings = SimpleNamespace(upload_dir=tmp_path, max_upload_bytes=10)

    async def scenario() -> None:
        stored = await _assert_event_loop_stays_responsive(
            _store_upload(upload, "video-1", settings)
        )
        assert stored["size_bytes"] == 5
        stored_path = Path(stored["storage_path"])
        assert stat.S_IMODE(stored_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(stored_path.parent.stat().st_mode) == 0o700

    asyncio.run(scenario())


def test_cancelled_upload_waits_for_copy_then_removes_orphan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = Event()
    finished = Event()

    def slow_copy(_source, target: Path, _limit: int):
        started.set()
        sleep(0.15)
        target.write_bytes(b"partial-video")
        finished.set()
        return 13, "checksum"

    monkeypatch.setattr(api_app, "_copy_upload", slow_copy)
    upload = SimpleNamespace(
        filename="video.mp4",
        content_type="video/mp4",
        file=BytesIO(b"video"),
        close=lambda: asyncio.sleep(0),
    )
    settings = SimpleNamespace(upload_dir=tmp_path / "uploads", max_upload_bytes=20)

    async def scenario() -> None:
        task = asyncio.create_task(_store_upload(upload, "video-1", settings))
        while not started.is_set():
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()

    asyncio.run(scenario())
    assert not (settings.upload_dir / "video-1").exists()
    assert not [item for item in settings.upload_dir.rglob("*") if item.is_file()]


def test_live_and_demo_uploads_use_separate_default_storage(monkeypatch) -> None:
    monkeypatch.delenv("VIDEO_OPS_DB_PATH", raising=False)
    monkeypatch.delenv("VIDEO_OPS_UPLOAD_DIR", raising=False)
    monkeypatch.setenv("VIDEO_OPS_MODE", "live")
    live = Settings.from_environment()
    monkeypatch.setenv("VIDEO_OPS_MODE", "demo")
    demo = Settings.from_environment()

    assert live.database_path == live.app_root / ".local/workspace.db"
    assert live.upload_dir == live.app_root / ".local/uploads"
    assert demo.database_path == demo.app_root / "output/demo.db"
    assert demo.upload_dir == demo.app_root / "output/uploads"


def test_upload_storage_rejects_traversal_and_external_registration(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    inside = root / "video.mp4"
    inside.write_bytes(b"video")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"private")

    with pytest.raises(ApplicationError, match="编号不合法"):
        _upload_directory(root, "..")
    assert _registered_media_path(str(inside), root) == str(inside.resolve())
    with pytest.raises(ApplicationError, match="成片存储目录"):
        _registered_media_path(str(outside), root)


def _media_client(storage_path: str, root: Path) -> TestClient:
    media = SimpleNamespace(
        id="media-1",
        storage_path=storage_path,
        file_name="final.mp4",
        mime_type="video/mp4",
    )
    snapshot = SimpleNamespace(
        videos=[SimpleNamespace(video=SimpleNamespace(media=[media]))]
    )
    service = SimpleNamespace(snapshot=lambda: snapshot)
    app = FastAPI()
    app.state.service = service
    app.state.settings = SimpleNamespace(upload_dir=root)
    _register_routes(app)
    _register_error_handlers(app)
    return TestClient(app)


def test_media_content_streams_registered_upload_inline(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    content = b"0123456789"
    media_path = root / "final.mp4"
    media_path.write_bytes(content)
    client = _media_client(str(media_path), root)

    response = client.get("/api/media/media-1/content")
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["accept-ranges"] == "bytes"

    ranged = client.get("/api/media/media-1/content", headers={"Range": "bytes=2-4"})
    assert ranged.status_code == 206
    assert ranged.content == b"234"


def test_media_content_hides_placeholder_missing_and_external_files(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"private")
    invalid_paths = [
        "sample://media/demo.mp4",
        str(root / "missing.mp4"),
        str(outside),
    ]

    for storage_path in invalid_paths:
        response = _media_client(storage_path, root).get("/api/media/media-1/content")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    unknown = _media_client(str(outside), root).get("/api/media/unknown/content")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["message"] == "没有找到这份成片。"


def test_missing_video_is_rejected_before_upload_writes(tmp_path: Path) -> None:
    upload = SimpleNamespace(
        filename="video.mp4",
        content_type="video/mp4",
        file=BytesIO(b"video"),
        close=lambda: asyncio.sleep(0),
    )
    settings = SimpleNamespace(upload_dir=tmp_path / "uploads", max_upload_bytes=10)
    service = SimpleNamespace(snapshot=lambda: SimpleNamespace(videos=[]))
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings, service=service))
    )

    with pytest.raises(ApplicationError, match="没有找到"):
        asyncio.run(_upload_media("..", request, upload))
    assert not settings.upload_dir.exists()


def test_confirm_absent_route_requires_explicit_acknowledgement() -> None:
    calls = []
    service = SimpleNamespace(
        confirm_publication_absent=lambda publication_id, note: calls.append(
            (publication_id, note)
        )
        or {"id": publication_id, "status": "failed"}
    )
    app = FastAPI()
    app.state.service = service
    _register_routes(app)
    assert any(route.path.endswith("/confirm-absent") for route in app.routes)
    with pytest.raises(ValueError):
        ConfirmPublicationAbsentRequest(confirmed_absent=False, note="已核对")
    accepted = asyncio.run(
        _confirm_absent(
            "publication-1",
            ConfirmPublicationAbsentRequest(
                confirmed_absent=True,
                note="频道后台和定时列表均无记录",
            ),
            _request(service),
        )
    )

    assert accepted["status"] == "failed"
    assert calls == [("publication-1", "频道后台和定时列表均无记录")]
