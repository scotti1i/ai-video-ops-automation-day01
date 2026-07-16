"""轻量后台轮询：只自动发布样例平台，真实平台仅做只读数据回流。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic

from video_ops.application.service import VideoOperationsService
from video_ops.domain.models import (
    Publication,
    PublicationOrigin,
    PublicationStatus,
    WorkspaceSnapshot,
)

LOGGER = logging.getLogger(__name__)
PUBLISHED_STATES = {
    PublicationStatus.SUCCEEDED,
    PublicationStatus.SUCCEEDED_WITH_WARNINGS,
}


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class OperationsWorker:
    def __init__(
        self,
        service: VideoOperationsService,
        *,
        poll_seconds: float,
        metric_sync_seconds: float,
    ):
        self.service = service
        self.poll_seconds = max(1.0, poll_seconds)
        self.metric_sync_seconds = max(self.poll_seconds, metric_sync_seconds)
        self._stop = asyncio.Event()
        self._last_metric_sync = monotonic()

    async def serve(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self.run_once)
            except Exception:  # pragma: no cover - 保证工作线程不因单条数据退出
                LOGGER.exception("后台轮询失败")
            await self._wait_for_next_poll()

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> None:
        self.service.recover_interrupted_publications()
        snapshot = self.service.snapshot()
        self._publish_due_mock_tasks(snapshot)
        if monotonic() - self._last_metric_sync < self.metric_sync_seconds:
            return
        self._sync_publications(self.service.snapshot())
        self._last_metric_sync = monotonic()

    async def _wait_for_next_poll(self) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)

    def _publish_due_mock_tasks(self, snapshot: WorkspaceSnapshot) -> None:
        platforms = {item.id: item.platform for item in snapshot.accounts}
        now = datetime.now(UTC)
        for publication in self._publications(snapshot):
            if not self._is_due_mock(publication, platforms, now):
                continue
            draft = publication.model_copy(
                update={"status": PublicationStatus.DRAFT, "updated_at": now.isoformat()}
            )
            self.service.repository.update_publication(draft)
            self.service.execute_publication(publication.id)

    def _sync_publications(self, snapshot: WorkspaceSnapshot) -> None:
        platforms = {item.id: item.platform for item in snapshot.accounts}
        for publication in self._publications(snapshot):
            scheduled_remote = (
                publication.status == PublicationStatus.SCHEDULED
                and bool(publication.external_id)
            )
            if publication.status not in PUBLISHED_STATES and not scheduled_remote:
                continue
            platform = platforms.get(publication.account_id)
            if platform not in self.service.platform_adapters:
                continue
            try:
                self.service.sync_publication(publication.id)
            except Exception:  # pragma: no cover - 单账号失败不能阻塞其他账号
                LOGGER.exception("发布数据同步失败: %s", publication.id)

    @staticmethod
    def _is_due_mock(
        publication: Publication,
        platforms: dict[str, str],
        now: datetime,
    ) -> bool:
        if publication.status != PublicationStatus.SCHEDULED or not publication.scheduled_at:
            return False
        if publication.origin == PublicationOrigin.SAMPLE:
            return False
        if platforms.get(publication.account_id) != "mock-social":
            return False
        try:
            return _parse_time(publication.scheduled_at) <= now
        except ValueError:
            LOGGER.warning("无法解析排期时间: %s", publication.id)
            return False

    @staticmethod
    def _publications(snapshot: WorkspaceSnapshot):
        return (
            publication
            for view in snapshot.videos
            for publication in view.video.publications
        )
