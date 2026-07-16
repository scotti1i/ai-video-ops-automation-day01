from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest

from video_ops.adapters.mock_platform import MockPlatformAdapter
from video_ops.adapters.sqlite_repo import SQLiteRepository
from video_ops.application import publication_reconciliation as publication_results
from video_ops.application.errors import ApplicationError, PlatformError
from video_ops.application.service import VideoOperationsService
from video_ops.domain.models import (
    ArtifactSource,
    ConnectionStatus,
    PublicationOrigin,
    PublicationStatus,
    StoryboardShot,
    VideoStage,
)


class CountingPlatform(MockPlatformAdapter):
    def __init__(self) -> None:
        self.publish_calls = 0
        self.requests: list[dict] = []

    def publish(self, request: dict) -> dict:
        self.publish_calls += 1
        self.requests.append(request)
        return super().publish(request)


class UnknownPlatform(CountingPlatform):
    def publish(self, request: dict) -> dict:
        self.publish_calls += 1
        raise PlatformError(
            "publish",
            "unknown_outcome",
            "平台可能已接收视频",
            raw_ref="evidence/unknown.json",
        )


class UnknownOncePlatform(CountingPlatform):
    def publish(self, request: dict) -> dict:
        if self.publish_calls == 0:
            self.publish_calls += 1
            raise PlatformError(
                "publish",
                "unknown_outcome",
                "平台可能已接收视频",
                raw_ref="evidence/unknown-once.json",
            )
        return super().publish(request)


class CrashingPlatform(CountingPlatform):
    def publish(self, request: dict) -> dict:
        self.publish_calls += 1
        raise RuntimeError("unexpected child process failure")


class ScheduledYouTubePlatform(CountingPlatform):
    platform = "youtube"

    def publish(self, request: dict) -> dict:
        self.publish_calls += 1
        self.requests.append(request)
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
            "state": "succeeded",
            "platform_content_id": external_id,
            "url": f"https://youtu.be/{external_id}",
            "published_at": "2026-07-15T02:00:00+00:00",
        }


class InspectionFailurePlatform(MockPlatformAdapter):
    def inspect_account(self, connector_ref: str | None) -> dict:
        raise PlatformError(
            "inspect_account",
            "auth_required",
            "授权已失效",
        )


class CustomScriptProducer:
    def produce(self, _context: str, _instruction: str):
        return SimpleNamespace(
            script="自定义生产器脚本",
            shots=[
                StoryboardShot(order=1, duration_seconds=3, visual="开场", voiceover="先看结果"),
                StoryboardShot(order=2, duration_seconds=8, visual="过程", voiceover="再看过程"),
            ],
            provider="custom-provider",
        )


def _new_video(service: VideoOperationsService, suffix: str):
    return service.create_video(
        title=f"脚本入口 {suffix}",
        goal=f"验证 {suffix}",
        account_ids=["account-mock-shop"],
        product_id="product-blender",
        brief="从真实业务 Context 开始",
        sources=[
            {
                "kind": "text",
                "label": "需求",
                "content": "20 秒内讲清一个使用场景",
            }
        ],
    )


def test_one_click_generation_produces_conversational_versions(
    service: VideoOperationsService,
) -> None:
    generated = _new_video(service, "一键生成")
    generated = service.generate_artifacts(
        generated.id,
        instruction="先给结果，再讲过程",
        producer="mock",
    )
    assert generated.scripts[-1].source == ArtifactSource.MOCK
    assert generated.storyboards[-1].source == ArtifactSource.MOCK
    follow_up_context = service._generation_context(generated)
    assert "当前脚本 v1" in follow_up_context
    assert generated.scripts[-1].content in follow_up_context
    assert "当前分镜 v1" in follow_up_context
    generated = service.generate_artifacts(
        generated.id,
        instruction="缩短第一句，保留其他结构",
        producer="mock",
    )
    assert generated.scripts[-1].version == 2
    assert generated.storyboards[-1].version == 2
    assert "缩短第一句" in generated.scripts[-1].note


def test_generation_context_includes_reference_url(
    service: VideoOperationsService,
) -> None:
    video = service.create_video(
        title="参考视频输入",
        goal="复用参考视频结构",
        account_ids=["account-mock-shop"],
        product_id=None,
        brief="只学习结构",
        sources=[
            {
                "kind": "video",
                "label": "参考视频",
                "content": "先展示失败结果",
                "href": "https://example.com/reference-video",
            }
        ],
    )

    context = service._generation_context(video)
    assert "参考视频：先展示失败结果" in context
    assert "https://example.com/reference-video" in context


def test_video_title_uses_youtube_safe_limit(
    service: VideoOperationsService,
) -> None:
    with pytest.raises(ApplicationError, match="不能超过 100"):
        service.create_video(
            title="长" * 101,
            goal="避免创建无法发布且无法修复的记录",
            account_ids=[],
            product_id=None,
            brief="",
            sources=[],
        )


def test_branch_title_keeps_variation_within_youtube_limit(
    service: VideoOperationsService,
) -> None:
    parent = service.create_video(
        title="父" * 100,
        goal="测试长标题裂变",
        account_ids=[],
        product_id=None,
        brief="",
        sources=[],
    )

    child = service.branch_video(parent.id, variation="换成家庭厨房场景", comment_ids=[])

    assert len(child.title) <= 100
    assert child.title.endswith(" · 换成家庭厨房场景")


def test_script_producer_can_be_replaced_without_changing_video_relations(
    service: VideoOperationsService,
) -> None:
    video = _new_video(service, "可替换生产器")
    before = service.snapshot()
    replaced = VideoOperationsService(
        service.repository,
        platform_adapters=service.platform_adapters,
        script_producer_factories={"custom": CustomScriptProducer},
    )

    generated = replaced.generate_artifacts(
        video.id,
        instruction="使用外部生产器",
        producer="custom",
    )

    assert generated.id == video.id
    assert generated.account_ids == video.account_ids
    assert generated.parent_video_id == video.parent_video_id
    assert generated.publications == video.publications
    assert len(replaced.snapshot().accounts) == len(before.accounts)
    assert "custom-provider" in generated.scripts[-1].note


def test_imported_script_uses_the_same_artifact_contract(
    service: VideoOperationsService,
) -> None:
    imported = _new_video(service, "外部导入")
    imported = service.import_artifacts(
        imported.id,
        script="镜头一：给结果\n镜头二：展示过程",
    )
    assert imported.scripts[-1].source == ArtifactSource.IMPORT
    assert imported.storyboards[-1].source == ArtifactSource.IMPORT


def test_missing_parent_is_rejected_before_video_is_created(
    service: VideoOperationsService,
) -> None:
    before = len(service.snapshot().videos)

    with pytest.raises(ApplicationError) as error:
        service.create_video(
            title="无效父视频",
            goal="验证父子关系",
            account_ids=[],
            product_id=None,
            brief="父节点必须真实存在",
            sources=[],
            parent_video_id="video-does-not-exist",
        )

    assert error.value.code == "invalid_parent"
    assert len(service.snapshot().videos) == before


def test_batch_creates_traceable_children_without_mutating_parent(
    service: VideoOperationsService,
) -> None:
    parent = _new_video(service, "批量裂变")
    parent = service.generate_artifacts(parent.id, instruction="先给结果", producer="mock")
    parent_before = parent.model_dump()

    batch = service.create_batch(
        parent.id,
        name="第一批裂变",
        variations=["换人物", "  ", "换场景"],
    )
    snapshot = service.snapshot()
    videos = [item.video for item in snapshot.videos]
    children = [item for item in videos if item.id in batch.video_ids]
    parent_after = next(item for item in videos if item.id == parent.id)

    assert len(children) == 2
    assert {item.variation_note for item in children} == {"换人物", "换场景"}
    assert all(item.parent_video_id == parent.id for item in children)
    assert all(item.batch_id == batch.id for item in children)
    assert all(item.account_ids == parent.account_ids for item in children)
    assert all(item.product_id == parent.product_id for item in children)
    assert all(item.contexts[-1].sources[0].kind == "lineage" for item in children)
    assert parent_after.model_dump() == parent_before


def test_lineage_context_excludes_local_paths_accounts_urls_and_authors(
    service: VideoOperationsService,
) -> None:
    parent = next(item.video for item in service.snapshot().videos if item.video.id == "video-hero")
    comment = parent.publications[0].comments[0]

    child = service.branch_video(
        parent.id,
        variation="只换场景",
        comment_ids=[comment.id],
    )
    model_context = service._generation_context(child)

    private_values = [
        *(item.storage_path for item in parent.media),
        *(item.account_id for item in parent.publications),
        *(item.url for item in parent.publications if item.url),
        comment.author,
    ]
    assert all(value not in model_context for value in private_values)
    assert parent.media[0].checksum in model_context
    assert comment.content in model_context


def test_direct_edit_versions_script_and_storyboard(
    service: VideoOperationsService,
) -> None:
    edited = _new_video(service, "直接编辑")
    edited = service.update_artifacts(
        edited.id,
        "手动编辑后的脚本",
        [
            {
                "order": 1,
                "duration_seconds": 6,
                "visual": "结果特写",
                "voiceover": "先看结果",
            }
        ],
        "运营修改",
    )
    edited = service.update_storyboard(
        edited.id,
        [
            {
                "order": 1,
                "duration_seconds": 8,
                "visual": "同机位对比",
                "voiceover": "只换画面，保留口播",
            }
        ],
        "分镜修订",
    )
    assert edited.scripts[-1].source == ArtifactSource.USER
    assert [item.version for item in edited.storyboards] == [1, 2]


def test_script_only_edit_creates_matching_storyboard_version(
    service: VideoOperationsService,
) -> None:
    video = _new_video(service, "脚本与分镜同步")
    video = service.generate_artifacts(video.id, instruction="先给结果", producer="mock")

    edited = service.update_artifacts(video.id, "新开头\n新证明\n新行动语", None, "改口播")

    assert edited.scripts[-1].version == 2
    assert edited.storyboards[-1].version == 2
    assert "新开头" in edited.storyboards[-1].shots[0].voiceover


def test_markdown_import_does_not_turn_frontmatter_or_heading_into_voiceover(
    service: VideoOperationsService,
) -> None:
    video = _new_video(service, "Markdown 清洗")
    script = "---\ntitle: 私有标题\nauthor: Scott\n---\n# 正式脚本\n第一句口播\n第二句口播"

    imported = service.import_artifacts(video.id, script=script)
    voiceover = "\n".join(item.voiceover for item in imported.storyboards[-1].shots)

    assert "title:" not in voiceover
    assert "author:" not in voiceover
    assert "正式脚本" not in voiceover
    assert "第一句口播" in voiceover


def test_concurrent_video_creation_allocates_unique_codes(
    service: VideoOperationsService,
) -> None:
    with ThreadPoolExecutor(max_workers=4) as pool:
        videos = list(pool.map(lambda index: _new_video(service, str(index)), range(4)))
    assert len({item.code for item in videos}) == 4


def test_publication_is_idempotent(
    repository: SQLiteRepository,
) -> None:
    adapter = CountingPlatform()
    service = VideoOperationsService(
        repository,
        platform_adapters={"mock-social": adapter},
    )
    first = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop", "account-mock-shop"],
        scheduled_at=None,
        auto_execute_mock=False,
    )
    assert len(first) == 1
    first = first[0]
    same = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop"],
        scheduled_at=None,
        auto_execute_mock=False,
    )[0]
    assert same.id == first.id

    succeeded = service.execute_publication(first.id)
    repeated = service.execute_publication(first.id)
    assert succeeded.status == PublicationStatus.SUCCEEDED
    assert repeated.external_id == succeeded.external_id
    assert adapter.publish_calls == 1


def test_concurrent_execute_claims_publication_once(
    repository: SQLiteRepository,
) -> None:
    adapter = CountingPlatform()
    service = VideoOperationsService(repository, platform_adapters={"mock-social": adapter})
    publication = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop"],
        scheduled_at=None,
        auto_execute_mock=False,
    )[0]
    original_snapshot = repository.snapshot
    barrier = Barrier(2)
    counter_lock = Lock()
    snapshot_calls = 0

    def synchronized_snapshot():
        nonlocal snapshot_calls
        snapshot = original_snapshot()
        with counter_lock:
            snapshot_calls += 1
            should_wait = snapshot_calls <= 2
        if should_wait:
            barrier.wait(timeout=5)
        return snapshot

    repository.snapshot = synchronized_snapshot  # type: ignore[method-assign]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.execute_publication(publication.id), range(2)))

    assert adapter.publish_calls == 1
    assert {item.status for item in results} <= {
        PublicationStatus.PUBLISHING,
        PublicationStatus.SUCCEEDED,
    }
    stored = service._find_publication(original_snapshot(), publication.id)
    assert stored.status == PublicationStatus.SUCCEEDED


def test_due_schedule_runs_and_invalid_schedule_is_rejected(
    repository: SQLiteRepository,
) -> None:
    adapter = CountingPlatform()
    service = VideoOperationsService(
        repository,
        platform_adapters={"mock-social": adapter},
    )
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    future_task = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop"],
        scheduled_at=future,
        auto_execute_mock=False,
    )[0]
    assert service.execute_publication(future_task.id).status == PublicationStatus.SCHEDULED
    assert adapter.publish_calls == 0

    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    with repository.transaction() as connection:
        connection.execute(
            "UPDATE publications SET scheduled_at = ? WHERE id = ?",
            (past, future_task.id),
        )
    assert service.execute_publication(future_task.id).status == PublicationStatus.SUCCEEDED
    assert adapter.publish_calls == 1
    assert adapter.requests[-1]["scheduled_at"] is None

    with pytest.raises(ApplicationError) as invalid:
        service.arrange_publications(
            "video-organizer",
            account_ids=["account-mock-shop"],
            scheduled_at="2026-07-14 09:00:00",
            auto_execute_mock=False,
        )
    assert invalid.value.code == "invalid_input"


def test_unknown_publish_result_blocks_automatic_retry(
    repository: SQLiteRepository,
) -> None:
    adapter = UnknownPlatform()
    service = VideoOperationsService(
        repository,
        platform_adapters={"mock-social": adapter},
    )
    publication = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop"],
        scheduled_at=None,
        auto_execute_mock=False,
    )[0]

    result = service.execute_publication(publication.id)
    assert result.status == PublicationStatus.UNKNOWN
    assert result.raw_ref == "evidence/unknown.json"
    with pytest.raises(ApplicationError, match="不能自动重试"):
        service.execute_publication(publication.id)
    assert adapter.publish_calls == 1

    reconciled = service.reconcile_publication(
        publication.id,
        external_id="confirmed-platform-id",
        url="https://example.invalid/confirmed-platform-id",
        published_at="2026-07-14T08:00:00+00:00",
    )
    assert reconciled.status == PublicationStatus.SUCCEEDED
    assert reconciled.external_id == "confirmed-platform-id"
    assert reconciled.error is None
    assert adapter.publish_calls == 1


def test_unknown_can_retry_only_after_user_confirms_platform_absent(
    repository: SQLiteRepository,
) -> None:
    adapter = UnknownOncePlatform()
    service = VideoOperationsService(repository, platform_adapters={"mock-social": adapter})
    publication = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop"],
        scheduled_at=None,
        auto_execute_mock=False,
    )[0]

    unknown = service.execute_publication(publication.id)
    reset = service.confirm_publication_absent(
        publication.id,
        note="频道后台和定时列表均无记录",
    )

    assert unknown.status == PublicationStatus.UNKNOWN
    assert reset.status == PublicationStatus.FAILED
    assert reset.raw_ref is None
    assert "频道后台和定时列表均无记录" in reset.warnings[-1]
    retried = service.execute_publication(publication.id)
    assert retried.status == PublicationStatus.SUCCEEDED
    assert adapter.publish_calls == 2
    assert any("人工核对" in warning for warning in retried.warnings)
    with pytest.raises(ApplicationError) as invalid:
        service.confirm_publication_absent(publication.id, note="再次点击")
    assert invalid.value.code == "invalid_state"


def test_unexpected_publish_exception_becomes_unknown_and_blocks_retry(
    repository: SQLiteRepository,
) -> None:
    adapter = CrashingPlatform()
    service = VideoOperationsService(
        repository,
        platform_adapters={"mock-social": adapter},
    )
    publication = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop"],
        scheduled_at=None,
        auto_execute_mock=False,
    )[0]

    result = service.execute_publication(publication.id)

    assert result.status == PublicationStatus.UNKNOWN
    assert "核对前不会重试" in (result.error or "")
    with pytest.raises(ApplicationError, match="不能自动重试"):
        service.execute_publication(publication.id)
    assert adapter.publish_calls == 1


def test_publish_lease_blocks_live_recovery_and_stale_final_write(
    repository: SQLiteRepository,
) -> None:
    adapter = CountingPlatform()
    service = VideoOperationsService(
        repository,
        platform_adapters={"mock-social": adapter},
    )
    publication = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop"],
        scheduled_at=None,
        auto_execute_mock=False,
    )[0]
    publishing, claim_token = publication_results.begin_publish(publication)
    assert repository.claim_publication(publication, publishing)

    second_service = VideoOperationsService(
        repository,
        platform_adapters={"mock-social": adapter},
    )
    assert second_service.recover_interrupted_publications() == []
    active = service._find_publication(repository.snapshot(), publication.id)
    assert active.status == PublicationStatus.PUBLISHING
    assert active.claim_token == claim_token

    expired = active.model_copy(
        update={"lease_expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
    )
    repository.update_publication(expired)
    recovered = second_service.recover_interrupted_publications()

    stale_success = publication_results.record_publish_receipt(
        publishing,
        {
            "state": "succeeded",
            "platform_content_id": "stale-platform-id",
            "url": "https://example.invalid/stale-platform-id",
        },
        updated_at=datetime.now(UTC).isoformat(),
    )
    stored = service._store_publication(stale_success, claim_token)

    assert [item.id for item in recovered] == [publication.id]
    assert recovered[0].status == PublicationStatus.UNKNOWN
    assert "进程曾中断" in (recovered[0].error or "")
    assert stored.status == PublicationStatus.UNKNOWN
    assert stored.external_id is None
    assert adapter.publish_calls == 0


def test_one_account_failure_does_not_roll_back_another_success(
    service: VideoOperationsService,
) -> None:
    publications = service.arrange_publications(
        "video-organizer",
        account_ids=["account-mock-shop", "account-mock-broken"],
        scheduled_at=None,
    )
    status_by_account = {item.account_id: item.status for item in publications}
    assert status_by_account == {
        "account-mock-shop": PublicationStatus.SUCCEEDED,
        "account-mock-broken": PublicationStatus.FAILED,
    }
    video = next(
        item.video for item in service.snapshot().videos if item.video.id == "video-organizer"
    )
    assert len(video.publications) == 2
    assert video.media


def test_youtube_schedule_submits_once_then_advances_only_by_sync(
    repository: SQLiteRepository,
) -> None:
    adapter = ScheduledYouTubePlatform()
    service = VideoOperationsService(repository, platform_adapters={"youtube": adapter})
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    publication = service.arrange_publications(
        "video-organizer",
        account_ids=["account-youtube-main"],
        scheduled_at=future,
        auto_execute_mock=False,
    )[0]

    with pytest.raises(ApplicationError) as confirmation:
        service.execute_publication(publication.id)
    assert confirmation.value.code == "confirmation_required"

    scheduled = service.execute_publication(publication.id, confirmed=True)
    assert scheduled.status == PublicationStatus.SCHEDULED
    assert scheduled.external_id == "scheduled-youtube-id"
    assert adapter.requests[0]["scheduled_at"] == future

    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    with repository.transaction() as connection:
        connection.execute(
            "UPDATE publications SET scheduled_at = ? WHERE id = ?",
            (past, scheduled.id),
        )
    same = service.execute_publication(scheduled.id, confirmed=True)
    assert same.status == PublicationStatus.SCHEDULED
    assert adapter.publish_calls == 1

    synced = service.sync_publication(scheduled.id)
    assert synced.status == PublicationStatus.SUCCEEDED
    assert synced.published_at == "2026-07-15T02:00:00+00:00"
    assert adapter.publish_calls == 1


def test_history_import_sync_and_account_inspection(
    repository: SQLiteRepository,
) -> None:
    adapter = MockPlatformAdapter()
    service = VideoOperationsService(
        repository,
        platform_adapters={"youtube": adapter, "mock-social": adapter},
    )
    imported = service.import_publication(
        "video-import-script",
        "account-youtube-main",
        "existing-youtube-id",
        "https://youtu.be/existing-youtube-id",
        "2026-07-01T08:00:00+00:00",
    )
    same = service.import_publication(
        "video-import-script",
        "account-youtube-main",
        "existing-youtube-id",
        "https://youtu.be/existing-youtube-id",
        "2026-07-01T08:00:00+00:00",
    )
    assert imported.id == same.id
    assert imported.origin == PublicationOrigin.IMPORTED
    repository.update_publication(
        imported.model_copy(update={"warnings": ["YouTube 评论授权文件不存在", "保留的发布警告"]})
    )

    service.sync_publication(imported.id)
    throttled = service.sync_publication(imported.id)
    assert len(throttled.metrics) == 1  # 30 分钟内重复同步不再记快照
    backdated = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    with repository.transaction() as connection:
        connection.execute(
            "UPDATE metrics SET captured_at = ? WHERE publication_id = ?",
            (backdated, imported.id),
        )
    synced = service.sync_publication(imported.id)
    assert len(synced.metrics) == 2
    assert len(synced.comments) == 2
    assert synced.warnings == ["保留的发布警告"]
    video = next(
        item.video for item in service.snapshot().videos if item.video.id == "video-import-script"
    )
    assert "account-youtube-main" in video.account_ids

    inspected = service.inspect_account("account-youtube-main")
    assert inspected["platform_account_id"] == "mock-account"
    account = next(
        item for item in service.snapshot().accounts if item.id == "account-youtube-main"
    )
    assert account.connection_status == ConnectionStatus.CONNECTED


def test_failed_account_inspection_preserves_existing_connection_state(
    repository: SQLiteRepository,
) -> None:
    service = VideoOperationsService(
        repository,
        platform_adapters={"mock-social": InspectionFailurePlatform()},
    )
    before = next(item for item in service.snapshot().accounts if item.id == "account-mock-shop")
    with pytest.raises(PlatformError):
        service.inspect_account(before.id)
    after = next(item for item in service.snapshot().accounts if item.id == "account-mock-shop")
    assert after.connection_status == before.connection_status


def test_branch_inherits_context_and_references_without_copying_artifacts(
    service: VideoOperationsService,
) -> None:
    before = next(item.video for item in service.snapshot().videos if item.video.id == "video-hero")
    comment = before.publications[0].comments[0]

    child = service.branch_video(
        before.id,
        variation="只换人物和场景",
        comment_ids=[comment.id],
    )

    assert child.parent_video_id == before.id
    assert not child.scripts
    assert not child.storyboards
    assert not child.media
    kinds = {item.kind for item in child.contexts[-1].sources}
    assert {
        "parent_context",
        "parent_context_source",
        "parent_script",
        "parent_storyboard",
        "parent_media",
        "parent_metric",
        "comment",
    } <= kinds
    view = next(item for item in service.snapshot().videos if item.video.id == child.id)
    assert view.stage.stage == VideoStage.NEEDS_SCRIPT

    after = next(item.video for item in service.snapshot().videos if item.video.id == "video-hero")
    assert after.scripts == before.scripts
    assert after.storyboards == before.storyboards
    assert after.media == before.media
