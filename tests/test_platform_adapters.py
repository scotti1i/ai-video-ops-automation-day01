import importlib.util
import json
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from video_ops.adapters.mock_platform import MockPlatformAdapter
from video_ops.adapters.script_producers import (
    GeneratedPlan,
    GeneratedShot,
    MockScriptProducer,
    OpenAIScriptProducer,
    _coerce_plan,
    _normalized_base_url,
)
from video_ops.adapters.sqlite_repo import SQLiteRepository
from video_ops.adapters.youtube import YouTubePlatformAdapter
from video_ops.application.errors import ApplicationError, PlatformError
from video_ops.application.service import VideoOperationsService
from video_ops.cli import (
    _parser,
    _require_loopback_host,
    _youtube_checks,
    _youtube_comment_auth,
)
from video_ops.domain.models import PublicationStatus
from video_ops.domain.ports import PlatformAdapter


def _load_youtube_bridge():
    path = Path(__file__).parents[1] / "scripts" / "youtube_bridge.py"
    spec = importlib.util.spec_from_file_location("day01_youtube_bridge", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, status: int):
        self.status = status


class _FakeHttpError:
    def __init__(self, status: int, reason: str):
        self.resp = _FakeResponse(status)
        self.content = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode()


class _ModelStatusError(RuntimeError):
    def __init__(self, status_code: int):
        super().__init__(f"model status {status_code}")
        self.status_code = status_code


class _InvalidReceiptPlatform(MockPlatformAdapter):
    def __init__(self, receipt: dict) -> None:
        self.receipt = receipt
        self.publish_calls = 0

    def publish(self, request: dict) -> dict:
        del request
        self.publish_calls += 1
        return self.receipt


class _RegressingScheduledPlatform(MockPlatformAdapter):
    platform = "youtube"

    def publish(self, request: dict) -> dict:
        return {
            "state": "scheduled",
            "platform_content_id": "scheduled-youtube-id",
            "url": "https://youtu.be/scheduled-youtube-id",
            "published_at": None,
            "warnings": [],
            "raw_ref": "evidence/scheduled.json",
        }

    def get_publication(self, external_id: str) -> dict:
        return {
            "state": "draft",
            "platform_content_id": external_id,
            "url": f"https://youtu.be/{external_id}",
        }


@pytest.fixture
def youtube_adapter(tmp_path: Path) -> tuple[YouTubePlatformAdapter, Path]:
    uploader = tmp_path / "uploader"
    python = uploader / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    (uploader / "publish_single.py").touch()
    for name in ("token.json", "client_secrets.json"):
        secret = uploader / name
        secret.write_text("{}", encoding="utf-8")
        secret.chmod(0o644)
    app_root = tmp_path / "app"
    bridge = app_root / "scripts" / "youtube_bridge.py"
    bridge.parent.mkdir(parents=True)
    bridge.touch()
    media = tmp_path / "video.mp4"
    media.write_bytes(b"safe-test-video")
    adapter = YouTubePlatformAdapter(
        uploader_dir=uploader,
        expected_channel="channel-exact",
        evidence_dir=app_root / ".local" / "youtube-evidence",
        bridge_script=bridge,
    )
    return adapter, media


def _request(media: Path) -> dict:
    return {
        "idempotency_key": "stable-key",
        "account_ref": "channel-exact",
        "media_path": str(media),
        "title": "安全的 YouTube 上传",
        "description": "这是可验证的视频简介。",
        "scheduled_at": None,
    }


def _skip_inspection(adapter: YouTubePlatformAdapter, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adapter,
        "inspect_account",
        lambda _ref: {"platform_account_id": "channel-exact"},
    )


def test_youtube_uses_private_default_and_keeps_partial_success(
    youtube_adapter: tuple[YouTubePlatformAdapter, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, media = youtube_adapter
    _skip_inspection(adapter, monkeypatch)
    seen_command: list[str] = []
    seen_options: dict = {}

    def completed(command: list[str], **kwargs):
        seen_command.extend(command)
        seen_options.update(kwargs)
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="视频上传完成: https://youtu.be/abc-123\nDONE https://youtu.be/abc-123\n",
            stderr="封面设置失败: quota",
        )

    monkeypatch.setattr(subprocess, "run", completed)
    receipt = adapter.publish(_request(media))

    assert receipt["state"] == PublicationStatus.SUCCEEDED_WITH_WARNINGS
    assert receipt["platform_content_id"] == "abc-123"
    assert "--privacy" in seen_command
    assert seen_command[seen_command.index("--privacy") + 1] == "private"
    assert any("private" in item for item in receipt["warnings"])
    assert any("退出码" in item for item in receipt["warnings"])
    assert seen_options["umask"] == 0o077
    assert stat.S_IMODE(adapter.evidence_dir.stat().st_mode) == 0o700
    private_files = [
        adapter.uploader_dir / "token.json",
        adapter.uploader_dir / "client_secrets.json",
        *adapter.evidence_dir.iterdir(),
    ]
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in private_files)


def test_youtube_timeout_without_id_is_unknown_and_never_retryable(
    youtube_adapter: tuple[YouTubePlatformAdapter, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, media = youtube_adapter
    _skip_inspection(adapter, monkeypatch)

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("publish", 7200, output="上传中... 95%")

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(PlatformError) as raised:
        adapter.publish(_request(media))
    assert raised.value.code == "unknown_outcome"
    assert raised.value.retryable is False
    assert raised.value.raw_ref


def test_youtube_future_upload_is_returned_as_scheduled(
    youtube_adapter: tuple[YouTubePlatformAdapter, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, media = youtube_adapter
    _skip_inspection(adapter, monkeypatch)
    seen_command: list[str] = []

    def completed(command: list[str], **_kwargs):
        seen_command.extend(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="DONE https://youtu.be/scheduled-id\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", completed)
    request = _request(media)
    request["scheduled_at"] = "2026-07-15T04:00:00+00:00"
    receipt = adapter.publish(request)

    assert receipt["state"] == "scheduled"
    assert receipt["published_at"] is None
    assert "--publish-at" in seen_command
    assert seen_command[seen_command.index("--publish-at") + 1] == request["scheduled_at"]


def test_youtube_timeout_after_done_is_recorded_as_success_with_warnings(
    youtube_adapter: tuple[YouTubePlatformAdapter, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, media = youtube_adapter
    _skip_inspection(adapter, monkeypatch)

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            "publish",
            7200,
            output=b"DONE https://youtu.be/done-before-timeout\n",
        )

    monkeypatch.setattr(subprocess, "run", timeout)
    receipt = adapter.publish(_request(media))
    assert receipt["state"] == "succeeded_with_warnings"
    assert receipt["platform_content_id"] == "done-before-timeout"
    assert any("超时" in item for item in receipt["warnings"])


def test_youtube_upload_marker_without_done_requires_reconciliation(
    youtube_adapter: tuple[YouTubePlatformAdapter, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, media = youtube_adapter
    _skip_inspection(adapter, monkeypatch)
    result = subprocess.CompletedProcess(
        [],
        1,
        stdout="视频上传完成: https://youtu.be/maybe-created\n",
        stderr="进程意外中断",
    )
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: result)
    with pytest.raises(PlatformError) as raised:
        adapter.publish(_request(media))
    assert raised.value.code == "unknown_outcome"
    assert raised.value.retryable is False

    for misleading_error in ("token expired", "频道不匹配", "缺封面"):
        ambiguous = subprocess.CompletedProcess(
            [],
            1,
            stdout="视频上传完成: https://youtu.be/maybe-created\n",
            stderr=misleading_error,
        )
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *_args, result=ambiguous, **_kwargs: result,
        )
        with pytest.raises(PlatformError) as ambiguous_result:
            adapter.publish(_request(media))
        assert ambiguous_result.value.code == "unknown_outcome"
        assert ambiguous_result.value.retryable is False

    unconfirmed = subprocess.CompletedProcess(
        [],
        1,
        stdout="",
        stderr="connection reset after upload request",
    )
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: unconfirmed)
    with pytest.raises(PlatformError) as missing_receipt:
        adapter.publish(_request(media))
    assert missing_receipt.value.code == "unknown_outcome"
    assert missing_receipt.value.retryable is False


def test_youtube_channel_match_is_exact_and_unambiguous(
    youtube_adapter: tuple[YouTubePlatformAdapter, Path],
) -> None:
    adapter, _ = youtube_adapter
    channels = [
        {"id": "UC-1", "title": "Scott", "handle": "@Scott"},
        {"id": "UC-2", "title": "Scott Lab", "handle": "@ScottLab"},
    ]
    assert adapter._match_channel(channels, "UC-1")["id"] == "UC-1"
    with pytest.raises(PlatformError, match="不一致"):
        adapter._match_channel(channels, "Scott ")
    duplicated = [channels[0], {"id": "UC-3", "title": "Scott", "handle": "@Other"}]
    with pytest.raises(PlatformError, match="不一致"):
        adapter._match_channel(duplicated, "Scott")


def test_youtube_metrics_and_comments_share_short_lived_collection(
    youtube_adapter: tuple[YouTubePlatformAdapter, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, _ = youtube_adapter
    calls = 0
    payload = {
        "video": {
            "statistics": {"viewCount": "1234", "likeCount": "56", "commentCount": "1"},
            "privacy_status": "private",
            "publish_at": "2026-07-15T04:00:00Z",
            "published_at": "2026-07-14T04:00:00Z",
        },
        "comments": [
            {
                "id": "comment-1",
                "author": "Viewer",
                "content": "请再测一个场景",
                "likes": 3,
                "published_at": "2026-07-14T01:00:00Z",
            }
        ],
        "comments_unavailable_reason": None,
    }

    def collect(*_args):
        nonlocal calls
        calls += 1
        return payload, "evidence/collect.json"

    monkeypatch.setattr(adapter, "_bridge", collect)
    remote = adapter.get_publication("youtube-1")
    metric = adapter.collect_metrics("publication-1", "youtube-1")
    comments, reason = adapter.collect_comments("publication-1", "youtube-1")

    assert calls == 1
    assert remote["state"] == "scheduled"
    assert remote["published_at"] is None
    assert metric.views == 1234
    assert comments[0].external_id == "comment-1"
    assert reason is None


def test_mock_platform_fulfils_publish_metrics_and_comments_contract() -> None:
    adapter = MockPlatformAdapter()
    receipt = adapter.publish({"idempotency_key": "same-request"})
    metric = adapter.collect_metrics("publication-1", receipt["platform_content_id"])
    comments, reason = adapter.collect_comments(
        "publication-1",
        receipt["platform_content_id"],
    )

    assert adapter.capabilities()["publish"] is True
    assert receipt["state"] == "succeeded"
    assert metric.views is not None
    assert len(comments) == 2
    assert reason is None


def test_mock_script_keeps_demo_disclosure_outside_script_content() -> None:
    plan = MockScriptProducer().produce("通勤场景", "先展示清洗结果")

    assert plan.script.startswith("别先听结论")
    assert "反复返工" not in plan.script
    assert "样例生成" not in plan.script
    assert "模拟输出" not in plan.script


def test_demo_seed_scripts_contain_only_user_facing_content(
    repository: SQLiteRepository,
) -> None:
    snapshot = repository.snapshot()
    imported = next(
        view.video for view in snapshot.videos
        if view.video.id == "video-import-script"
    )
    generated = next(view.video for view in snapshot.videos if view.video.id == "video-hero")

    assert imported.scripts[0].content.startswith("喝之前还要再倒进另一个杯子吗")
    assert "下一条只换成" not in imported.scripts[0].content
    assert imported.scripts[0].note == "导入已有脚本"
    assert generated.scripts[0].note == "演示工作区自带版本"


def test_mock_and_youtube_implement_the_same_platform_contract(
    youtube_adapter: tuple[YouTubePlatformAdapter, Path],
) -> None:
    adapters: tuple[PlatformAdapter, ...] = (
        MockPlatformAdapter(),
        youtube_adapter[0],
    )
    required_capabilities = {"publish", "schedule", "basic_metrics", "comments"}

    for adapter in adapters:
        assert isinstance(adapter, PlatformAdapter)
        assert required_capabilities <= adapter.capabilities().keys()


@pytest.mark.parametrize(
    "receipt",
    [
        {"state": "draft", "platform_content_id": "maybe-created"},
        {"state": "succeeded"},
        {"state": "succeeded", "platform_content_id": "", "warnings": []},
    ],
)
def test_invalid_publish_receipt_becomes_unknown_and_blocks_retry(
    repository: SQLiteRepository,
    receipt: dict,
) -> None:
    adapter = _InvalidReceiptPlatform(receipt)
    service = VideoOperationsService(repository, platform_adapters={"mock-social": adapter})
    publication = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop"],
        scheduled_at=None,
        auto_execute_mock=False,
    )[0]

    result = service.execute_publication(publication.id)

    assert result.status == PublicationStatus.UNKNOWN
    assert "回执不完整" in (result.error or "")
    with pytest.raises(ApplicationError) as blocked:
        service.execute_publication(publication.id)
    assert blocked.value.code == "needs_reconciliation"
    assert adapter.publish_calls == 1


def test_sync_rejects_remote_status_regression_without_mutating_local_record(
    repository: SQLiteRepository,
) -> None:
    adapter = _RegressingScheduledPlatform()
    service = VideoOperationsService(repository, platform_adapters={"youtube": adapter})
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    publication = service.arrange_publications(
        "video-organizer",
        account_ids=["account-youtube-main"],
        scheduled_at=future,
        auto_execute_mock=False,
    )[0]
    scheduled = service.execute_publication(publication.id, confirmed=True)

    with pytest.raises(ApplicationError) as invalid:
        service.sync_publication(scheduled.id)

    assert invalid.value.code == "invalid_platform_response"
    stored = service._find_publication(repository.snapshot(), scheduled.id)
    assert stored.status == PublicationStatus.SCHEDULED


@pytest.mark.parametrize(
    ("reason", "message"),
    [
        ("commentsDisabled", "YouTube 评论已关闭"),
        ("forbidden", "YouTube 评论当前授权不可读取"),
        ("insufficientPermissions", "YouTube 评论当前授权不可读取"),
    ],
)
def test_youtube_comment_permission_failure_keeps_metric_sync(
    reason: str,
    message: str,
) -> None:
    bridge = _load_youtube_bridge()
    assert bridge.comment_unavailable_reason(_FakeHttpError(403, reason)) == message
    assert bridge.comment_unavailable_reason(_FakeHttpError(403, "quotaExceeded")) is None
    assert bridge.comment_unavailable_reason(_FakeHttpError(500, reason)) is None


def test_youtube_comment_capability_requires_force_ssl_token(
    youtube_adapter: tuple[YouTubePlatformAdapter, Path],
) -> None:
    adapter, _ = youtube_adapter
    token = adapter.uploader_dir / "token.json"
    token.write_text(json.dumps({"scopes": ["youtube.upload"]}), encoding="utf-8")
    bridge = _load_youtube_bridge()

    assert adapter.capabilities()["comments"] is False
    assert bridge.comment_token_reason(token) == (
        "YouTube 评论读取缺少 youtube.force-ssl 授权"
    )

    token.write_text(json.dumps({"scopes": [bridge.COMMENT_SCOPE]}), encoding="utf-8")
    assert adapter.capabilities()["comments"] is True
    assert bridge.comment_token_reason(token) is None


def test_youtube_environment_paths_resolve_from_app_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YOUTUBE_UPLOAD_DIR", "connector")
    monkeypatch.setenv("YOUTUBE_EXPECTED_CHANNEL", "channel-exact")
    monkeypatch.setenv("YOUTUBE_COMMENT_TOKEN_PATH", ".local/comments.json")

    adapter = YouTubePlatformAdapter.from_environment(tmp_path)

    assert adapter is not None
    assert adapter.uploader_dir == tmp_path / "connector"
    assert adapter.comment_token_path == tmp_path / ".local/comments.json"


def test_comment_auth_command_keeps_token_separate_from_uploader() -> None:
    args = _parser().parse_args(
        [
            "youtube-comment-auth",
            "--uploader-dir",
            "/connector",
            "--output",
            ".local/comments.json",
        ]
    )

    assert args.command == "youtube-comment-auth"
    assert args.uploader_dir == "/connector"
    assert args.output == ".local/comments.json"


def test_server_rejects_non_loopback_bind() -> None:
    _require_loopback_host("127.0.0.1")
    _require_loopback_host("localhost")
    with pytest.raises(SystemExit, match="loopback"):
        _require_loopback_host("0.0.0.0")


def test_comment_auth_hardens_client_secret_and_child_umask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploader = tmp_path / "uploader"
    python = uploader / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    client_secrets = uploader / "client_secrets.json"
    client_secrets.write_text("{}", encoding="utf-8")
    client_secrets.chmod(0o644)
    options: dict = {}

    def completed(command: list[str], **kwargs):
        options.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", completed)
    result = _youtube_comment_auth(
        SimpleNamespace(
            uploader_dir=str(uploader),
            output=str(tmp_path / "comments.json"),
        )
    )

    assert result == 0
    assert stat.S_IMODE(client_secrets.stat().st_mode) == 0o600
    assert options["umask"] == 0o077


def test_doctor_rejects_broad_youtube_credential_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploader = tmp_path / "uploader"
    (uploader / ".venv/bin").mkdir(parents=True)
    for relative in (".venv/bin/python", "publish_single.py", "token.json", "client_secrets.json"):
        path = uploader / relative
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o644)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/youtube_bridge.py").touch()
    monkeypatch.setenv("YOUTUBE_UPLOAD_DIR", str(uploader))
    monkeypatch.setenv("YOUTUBE_EXPECTED_CHANNEL", "channel-exact")

    insecure = _youtube_checks(SimpleNamespace(app_root=tmp_path))
    assert next(item for item in insecure if item["name"] == "YouTube 凭据")["ok"] is False

    (uploader / "token.json").chmod(0o600)
    (uploader / "client_secrets.json").chmod(0o600)
    comment_token = tmp_path / "comments.json"
    comment_token.write_text(
        json.dumps({"scopes": ["https://www.googleapis.com/auth/youtube.force-ssl"]}),
        encoding="utf-8",
    )
    comment_token.chmod(0o644)
    monkeypatch.setenv("YOUTUBE_COMMENT_TOKEN_PATH", str(comment_token))
    secure = _youtube_checks(SimpleNamespace(app_root=tmp_path))
    assert next(item for item in secure if item["name"] == "YouTube 凭据")["ok"] is True
    assert next(item for item in secure if item["name"] == "YouTube 评论读取")["ok"] is False

    comment_token.chmod(0o600)
    complete = _youtube_checks(SimpleNamespace(app_root=tmp_path))
    assert next(item for item in complete if item["name"] == "YouTube 评论读取")["ok"] is True


def test_openai_producer_falls_back_to_structured_chat_for_compatible_relays() -> None:
    plan = GeneratedPlan(
        script="先展示整理前后，再说明免打孔。",
        shots=[
            GeneratedShot(duration_seconds=3, visual="前后对比", voiceover="先看结果"),
            GeneratedShot(duration_seconds=8, visual="安装过程", voiceover="免打孔安装"),
        ],
    )
    chat = SimpleNamespace(completions=SimpleNamespace(parse=lambda **_kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=plan))],
    )))
    producer = object.__new__(OpenAIScriptProducer)
    producer.model = "compatible-model"
    producer.client = SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **_kwargs: "incompatible-response-shape"),
        chat=chat,
    )

    result = producer.produce("真实 Context", "做 20 秒视频")

    assert result.script == plan.script
    assert len(result.shots) == 2
    assert result.provider == "openai-chat:compatible-model"


def test_openai_producer_falls_back_to_validated_json_for_limited_relays() -> None:
    plan_json = json.dumps(
        {
            "script": "先展示问题，再给出过程。",
            "shots": [
                {"duration_seconds": 3, "visual": "问题", "voiceover": "先看问题"},
                {"duration_seconds": 6, "visual": "过程", "voiceover": "再看过程"},
            ],
        },
        ensure_ascii=False,
    )
    event = json.dumps(
        {"choices": [{"delta": {"content": plan_json}}]},
        ensure_ascii=False,
    )
    received: dict = {}

    def create(**kwargs):
        received.update(kwargs)
        return f"data: {event}\n\ndata: [DONE]"

    completions = SimpleNamespace(
        parse=lambda **_kwargs: (_ for _ in ()).throw(ValueError("schema unsupported")),
        create=create,
    )
    producer = object.__new__(OpenAIScriptProducer)
    producer.model = "limited-model"
    producer.client = SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **_kwargs: "unsupported"),
        chat=SimpleNamespace(completions=completions),
    )

    result = producer.produce("真实 Context", "做 20 秒视频")

    assert result.script == "先展示问题，再给出过程。"
    assert result.provider == "openai-chat-json:limited-model"
    assert received["stream"] is False
    assert "JSON Schema" in received["messages"][0]["content"]


@pytest.mark.parametrize("status_code", [401, 429])
def test_openai_producer_does_not_multiply_auth_or_rate_limit_calls(
    status_code: int,
) -> None:
    calls = 0

    def chat_call(**_kwargs):
        nonlocal calls
        calls += 1

    producer = object.__new__(OpenAIScriptProducer)
    producer.model = "protected-model"
    producer.client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=lambda **_kwargs: (_ for _ in ()).throw(_ModelStatusError(status_code))
        ),
        chat=SimpleNamespace(completions=SimpleNamespace(parse=chat_call, create=chat_call)),
    )

    with pytest.raises(ApplicationError) as error:
        producer.produce("已保存 Context", "生成脚本")

    assert error.value.code == "model_failed"
    assert calls == 0


def test_openai_compatible_relay_base_url_and_sse_are_normalized() -> None:
    assert _normalized_base_url("https://relay.example") == "https://relay.example/v1"
    assert _normalized_base_url("https://relay.example/api/v1/") == (
        "https://relay.example/api/v1"
    )
    plan_json = json.dumps(
        {
            "script": "真实脚本",
            "shots": [
                {"duration_seconds": 3, "visual": "镜头一", "voiceover": "台词一"},
                {"duration_seconds": 4, "visual": "镜头二", "voiceover": "台词二"},
            ],
        },
        ensure_ascii=False,
    )
    size = len(plan_json) // 3
    parts = [plan_json[:size], plan_json[size : size * 2], plan_json[size * 2 :]]
    chunks = [
        json.dumps({"choices": [{"delta": {"content": part}}]}, ensure_ascii=False)
        for part in parts
    ]
    payload = "\n\n".join(f"data: {chunk}" for chunk in chunks) + "\n\ndata: [DONE]"

    plan = _coerce_plan(payload)

    assert plan is not None
    assert plan.script == "真实脚本"
    assert len(plan.shots) == 2
