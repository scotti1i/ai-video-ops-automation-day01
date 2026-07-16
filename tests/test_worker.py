from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from video_ops.api.worker import OperationsWorker
from video_ops.domain.models import PublicationOrigin, PublicationStatus


class _Service:
    def __init__(self) -> None:
        self.platform_adapters = {"mock-social": object(), "youtube": object()}
        self.synced: list[str] = []
        self.recovery_calls = 0
        self.workspace = SimpleNamespace(accounts=[], videos=[])

    def recover_interrupted_publications(self) -> None:
        self.recovery_calls += 1

    def snapshot(self):
        return self.workspace

    def sync_publication(self, publication_id: str) -> None:
        self.synced.append(publication_id)


def _publication(identifier: str, account_id: str, status, external_id: str | None):
    return SimpleNamespace(
        id=identifier,
        account_id=account_id,
        status=status,
        external_id=external_id,
    )


def test_worker_syncs_mock_and_youtube_without_triggering_publish() -> None:
    service = _Service()
    worker = OperationsWorker(service, poll_seconds=1, metric_sync_seconds=1)
    snapshot = SimpleNamespace(
        accounts=[
            SimpleNamespace(id="mock-account", platform="mock-social"),
            SimpleNamespace(id="youtube-account", platform="youtube"),
            SimpleNamespace(id="unavailable-account", platform="tiktok"),
        ],
        videos=[SimpleNamespace(video=SimpleNamespace(publications=[
            _publication("mock", "mock-account", PublicationStatus.SUCCEEDED, "mock-id"),
            _publication("youtube", "youtube-account", PublicationStatus.SUCCEEDED, "yt-id"),
            _publication("scheduled", "youtube-account", PublicationStatus.SCHEDULED, "yt-future"),
            _publication("draft", "youtube-account", PublicationStatus.DRAFT, None),
            _publication("missing", "unavailable-account", PublicationStatus.SUCCEEDED, "tt-id"),
        ]))],
    )

    worker._sync_publications(snapshot)

    assert service.synced == ["mock", "youtube", "scheduled"]


def test_worker_never_executes_due_sample_publication() -> None:
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    publication = SimpleNamespace(
        id="sample-scheduled",
        account_id="mock-account",
        status=PublicationStatus.SCHEDULED,
        scheduled_at=past,
        origin=PublicationOrigin.SAMPLE,
    )

    assert not OperationsWorker._is_due_mock(
        publication,
        {"mock-account": "mock-social"},
        datetime.now(UTC),
    )

    publication.origin = PublicationOrigin.SYSTEM
    assert OperationsWorker._is_due_mock(
        publication,
        {"mock-account": "mock-social"},
        datetime.now(UTC),
    )


def test_worker_periodically_recovers_expired_publish_leases() -> None:
    service = _Service()
    worker = OperationsWorker(service, poll_seconds=1, metric_sync_seconds=60)

    worker.run_once()

    assert service.recovery_calls == 1
