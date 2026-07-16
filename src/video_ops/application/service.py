"""把创建、生产、发布、回流和裂变串成同一条视频记录。"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from video_ops.application.errors import ApplicationError
from video_ops.domain.models import (
    Account,
    AccountGroup,
    ArtifactSource,
    Batch,
    ConnectionStatus,
    ContextSnapshot,
    ContextSource,
    MediaArtifact,
    Product,
    Publication,
    PublicationOrigin,
    PublicationStatus,
    ScriptArtifact,
    ScriptCandidate,
    StoryboardArtifact,
    StoryboardShot,
    Video,
    VideoView,
    WorkspaceSnapshot,
)
from video_ops.domain.ports import PlatformAdapter, ScriptProducer, WorkspaceRepository

from . import publication_reconciliation as publication_results
from .batch_generation import (
    assess_free_artifact,
    create_variation_batch,
    fallback_storyboard_shots,
    generate_script_batch,
    save_video_title,
)
from .identifiers import new_id
from .lineage import build_lineage_sources


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


# 同一发布两次指标快照的最小间隔：手动连点或后台轮询都不把种子历史淹没。
METRIC_SNAPSHOT_INTERVAL = timedelta(minutes=30)


class VideoOperationsService:
    def __init__(
        self,
        repository: WorkspaceRepository,
        *,
        platform_adapters: dict[str, PlatformAdapter] | None = None,
        script_producer_factories: dict[str, Callable[[], ScriptProducer]] | None = None,
    ):
        self.repository = repository
        self.platform_adapters = platform_adapters if platform_adapters is not None else {}
        self.script_producer_factories = (
            script_producer_factories if script_producer_factories is not None else {}
        )

    def snapshot(self) -> WorkspaceSnapshot:
        return self.repository.snapshot()

    def recover_interrupted_publications(self) -> list[Publication]:
        recovered = []
        for view in self.snapshot().videos:
            for publication in view.video.publications:
                repaired = publication_results.mark_interrupted(
                    publication,
                    updated_at=utc_now(),
                )
                if repaired == publication:
                    continue
                if self.repository.finish_publication(repaired, publication.claim_token):
                    recovered.append(repaired)
        return recovered

    def inspect_account(self, account_id: str) -> dict:
        snapshot = self.snapshot()
        account = self._find_account(snapshot, account_id)
        adapter = self._adapter(account.platform)
        result = adapter.inspect_account(account.connector_ref)
        self.repository.update_account_connection(
            account.id,
            ConnectionStatus.CONNECTED,
            account.connector_ref,
        )
        return result

    def create_video(
        self,
        *,
        title: str,
        goal: str,
        account_ids: list[str],
        product_id: str | None,
        brief: str,
        sources: list[dict],
        parent_video_id: str | None = None,
        variation_note: str | None = None,
        batch_id: str | None = None,
        external_video_id: str | None = None,
    ) -> Video:
        snapshot = self.snapshot()
        account_ids = list(dict.fromkeys(item for item in account_ids if item))
        self._validate_references(snapshot, account_ids, product_id, parent_video_id)
        if batch_id and batch_id not in {item.id for item in snapshot.batches}:
            raise ApplicationError("invalid_batch", "指定的批次不存在。")
        now = utc_now()
        video = Video(
            id=new_id("video"),
            code="pending",
            external_video_id=external_video_id,
            title=title.strip(),
            goal=goal.strip(),
            account_ids=account_ids,
            product_id=product_id,
            parent_video_id=parent_video_id,
            variation_note=variation_note,
            batch_id=batch_id,
            created_at=now,
            updated_at=now,
        )
        if not video.title or not video.goal:
            raise ApplicationError("invalid_input", "视频名称和本次目标都不能为空。")
        if len(video.title) > 100:
            raise ApplicationError("invalid_input", "视频名称不能超过 100 个字符。")
        context = ContextSnapshot(
            id=new_id("context"),
            video_id=video.id,
            version=1,
            brief=brief.strip() or goal.strip(),
            sources=[ContextSource(id=new_id("source"), **source) for source in sources],
            created_at=now,
        )
        video = self.repository.add_video_with_context(video, context)
        return self._find_video(self.snapshot(), video.id).video

    def update_video_title(self, video_id: str, title: str) -> Video:
        return save_video_title(self, video_id, title)

    def generate_artifacts(
        self,
        video_id: str,
        *,
        instruction: str,
        producer: str = "mock",
    ) -> Video:
        view = self._find_video(self.snapshot(), video_id)
        context = self._generation_context(view.video)
        factory = self.script_producer_factories.get(producer)
        if not factory:
            raise ApplicationError("unsupported", "当前脚本生产器不可用，请选择样例生成或 OpenAI。")
        result = factory().produce(context, instruction)
        source = ArtifactSource.MOCK if producer == "mock" else ArtifactSource.MODEL
        change = instruction.strip()[:160] or "按当前 Context 生成"
        note = f"{change} · 由 {result.provider} 生成"
        self._save_artifact_pair(
            view.video,
            result.script,
            result.shots,
            source,
            note,
            list(getattr(result, "claims", ()) or ()),
        )
        return self._find_video(self.snapshot(), video_id).video

    def import_artifacts(
        self,
        video_id: str,
        *,
        script: str,
        shots: list[dict] | None = None,
        note: str = "外部脚本导入",
    ) -> Video:
        view = self._find_video(self.snapshot(), video_id)
        if not script.strip():
            raise ApplicationError("invalid_input", "导入脚本不能为空。")
        storyboard = (
            [StoryboardShot(**item) for item in shots]
            if shots
            else fallback_storyboard_shots(script)
        )
        self._save_artifact_pair(
            view.video,
            script.strip(),
            storyboard,
            ArtifactSource.IMPORT,
            note,
        )
        return self._find_video(self.snapshot(), video_id).video

    def update_script(self, video_id: str, content: str, note: str) -> Video:
        return self.update_artifacts(video_id, content, None, note)

    def update_artifacts(
        self,
        video_id: str,
        content: str,
        shots: list[dict] | None,
        note: str,
    ) -> Video:
        view = self._find_video(self.snapshot(), video_id)
        if not content.strip():
            raise ApplicationError("invalid_input", "脚本内容不能为空。")
        board_shots = (
            [StoryboardShot(**item) for item in shots]
            if shots
            else fallback_storyboard_shots(content)
        )
        self._save_artifact_pair(
            view.video,
            content.strip(),
            board_shots,
            ArtifactSource.USER,
            note or "直接编辑",
        )
        return self._find_video(self.snapshot(), video_id).video

    def update_storyboard(self, video_id: str, shots: list[dict], note: str) -> Video:
        view = self._find_video(self.snapshot(), video_id)
        if not shots:
            raise ApplicationError("invalid_input", "分镜不能为空。")
        storyboard = StoryboardArtifact(
            id=new_id("storyboard"),
            video_id=video_id,
            version=len(view.video.storyboards) + 1,
            source=ArtifactSource.USER,
            shots=[StoryboardShot(**item) for item in shots],
            note=note or "直接编辑",
            created_at=utc_now(),
        )
        self.repository.add_storyboard(storyboard)
        return self._find_video(self.snapshot(), video_id).video

    def register_media(
        self,
        video_id: str,
        *,
        file_name: str,
        mime_type: str,
        size_bytes: int,
        checksum: str,
        storage_path: str,
        source: ArtifactSource = ArtifactSource.USER,
    ) -> Video:
        self._find_video(self.snapshot(), video_id)
        if not file_name or size_bytes <= 0:
            raise ApplicationError("invalid_input", "成片文件为空，请重新选择。")
        media = MediaArtifact(
            id=new_id("media"),
            video_id=video_id,
            file_name=file_name,
            mime_type=mime_type or "application/octet-stream",
            size_bytes=size_bytes,
            checksum=checksum,
            storage_path=storage_path,
            source=source,
            status="ready",
            created_at=utc_now(),
        )
        self.repository.add_media(media)
        return self._find_video(self.snapshot(), video_id).video

    def import_publication(
        self,
        video_id: str,
        account_id: str,
        external_id: str,
        url: str,
        published_at: str | None,
    ) -> Publication:
        snapshot = self.snapshot()
        self._find_video(snapshot, video_id)
        self._find_account(snapshot, account_id)
        platform_id = external_id.strip()
        if not platform_id or not url.strip():
            raise ApplicationError(
                "invalid_input",
                "导入历史视频时必须提供平台视频编号和链接。",
            )
        existing = self._publication_by_external_id(snapshot, account_id, platform_id)
        if existing:
            if existing.video_id != video_id:
                raise ApplicationError(
                    "external_id_conflict",
                    "该平台视频已经关联到另一条视频记录。",
                )
            return existing
        now = utc_now()
        key_seed = f"import:{account_id}:{platform_id}"
        publication = Publication(
            id=new_id("publication"),
            video_id=video_id,
            account_id=account_id,
            status=PublicationStatus.SUCCEEDED,
            origin=PublicationOrigin.IMPORTED,
            published_at=published_at,
            external_id=platform_id,
            url=url.strip(),
            idempotency_key=sha256(key_seed.encode()).hexdigest(),
            created_at=now,
            updated_at=now,
        )
        self.repository.add_publication_with_account_link(publication)
        return publication

    def reconcile_publication(
        self,
        publication_id: str,
        *,
        external_id: str,
        url: str,
        published_at: str | None,
    ) -> Publication:
        snapshot = self.snapshot()
        publication = self._find_publication(snapshot, publication_id)
        existing = self._publication_by_external_id(
            snapshot,
            publication.account_id,
            external_id.strip(),
        )
        reconciled = publication_results.reconcile_unknown_publication(
            publication,
            external_id=external_id,
            url=url,
            published_at=published_at,
            external_id_in_use=bool(existing and existing.id != publication.id),
            updated_at=utc_now(),
        )
        self.repository.update_publication(reconciled)
        return self._find_publication(self.snapshot(), publication_id)

    def confirm_publication_absent(self, publication_id: str, *, note: str) -> Publication:
        publication = self._find_publication(self.snapshot(), publication_id)
        reset = publication_results.confirm_unknown_not_created(
            publication,
            note=note,
            updated_at=utc_now(),
        )
        self.repository.update_publication(reset)
        return self._find_publication(self.snapshot(), publication_id)

    def arrange_publications(
        self,
        video_id: str,
        *,
        account_ids: list[str],
        scheduled_at: str | None,
        auto_execute_mock: bool = True,
    ) -> list[Publication]:
        snapshot = self.snapshot()
        view = self._find_video(snapshot, video_id)
        account_ids = list(dict.fromkeys(item for item in account_ids if item))
        if not account_ids:
            raise ApplicationError("invalid_input", "请至少选择一个发布账号。")
        self._validate_new_schedule(scheduled_at)
        if not view.video.media:
            raise ApplicationError("missing_media", "请先上传或登记成片，再安排发布。")
        self._validate_references(snapshot, account_ids, view.video.product_id, None)
        linked_accounts = list(dict.fromkeys([*view.video.account_ids, *account_ids]))
        if linked_accounts != view.video.account_ids:
            self.repository.replace_video_accounts(video_id, linked_accounts)
        media = view.video.media[-1]
        publications = []
        for account_id in account_ids:
            existing = self._publication_for(view.video, account_id, media.checksum, scheduled_at)
            if existing:
                publications.append(existing)
                continue
            publication = self._new_publication(view.video, account_id, media, scheduled_at)
            self.repository.add_publication(publication)
            publications.append(publication)
            account = self._find_account(snapshot, account_id)
            if auto_execute_mock and account.platform == "mock-social" and not scheduled_at:
                publications[-1] = self.execute_publication(publication.id)
        return publications

    def execute_publication(self, publication_id: str, *, confirmed: bool = False) -> Publication:
        snapshot = self.snapshot()
        publication = self._find_publication(snapshot, publication_id)
        account = self._find_account(snapshot, publication.account_id)
        view = self._find_video(snapshot, publication.video_id)
        if not self._publication_is_runnable(publication, account.platform):
            return publication
        if account.platform == "youtube" and not confirmed:
            raise ApplicationError(
                "confirmation_required",
                "YouTube 发布会真实对外生效，请确认后再执行。",
            )
        adapter = self._adapter(account.platform)
        publishing, claim_token = publication_results.begin_publish(publication)
        if not self.repository.claim_publication(publication, publishing):
            return self._find_publication(self.snapshot(), publication_id)
        request = self._publish_request(view.video, account, publishing)
        result = publication_results.publish_once(adapter, request, publishing)
        return self._store_publication(result, claim_token)

    def sync_publication(self, publication_id: str) -> Publication:
        snapshot = self.snapshot()
        publication = self._find_publication(snapshot, publication_id)
        account = self._find_account(snapshot, publication.account_id)
        if not publication.external_id:
            raise ApplicationError(
                "not_published",
                "这条任务还没有平台视频编号，暂时不能同步数据。",
            )
        adapter = self._adapter(account.platform)
        remote = adapter.get_publication(publication.external_id)
        publication = self._reconcile_publication(publication, remote)
        if not self._metric_recorded_recently(publication):
            previous = publication.metrics[-1] if publication.metrics else None
            metric = adapter.collect_metrics(publication.id, publication.external_id, previous)
            self.repository.add_metric(metric)
        comments, unavailable_reason = adapter.collect_comments(
            publication.id,
            publication.external_id,
        )
        for comment in comments:
            self.repository.upsert_comment(comment)
        previous_warnings = publication.warnings
        publication = publication_results.refresh_comment_warning(
            publication,
            platform=account.platform,
            unavailable_reason=unavailable_reason,
            updated_at=utc_now(),
        )
        if publication.warnings != previous_warnings:
            self.repository.update_publication(publication)
        return self._find_publication(self.snapshot(), publication_id)

    def branch_video(
        self,
        video_id: str,
        *,
        variation: str,
        comment_ids: list[str],
    ) -> Video:
        view = self._find_video(self.snapshot(), video_id)
        parent = view.video
        known_comment_ids = {
            comment.id for publication in parent.publications for comment in publication.comments
        }
        missing = set(comment_ids) - known_comment_ids
        if missing:
            raise ApplicationError(
                "invalid_comment",
                "选择的评论已不存在，请刷新数据后重试。",
            )
        if not variation.strip():
            raise ApplicationError("invalid_input", "请说明这次裂变要改变什么。")
        sources = build_lineage_sources(
            parent,
            comment_ids,
            performance_brief=view.performance_brief,
        )
        suffix = f" · {variation[:24]}"
        child = self.create_video(
            title=f"{parent.title[: 100 - len(suffix)]}{suffix}",
            goal=variation,
            account_ids=parent.account_ids,
            product_id=parent.product_id,
            brief=f"基于 {parent.code} 裂变：{variation}",
            sources=sources,
            parent_video_id=parent.id,
            variation_note=variation,
        )
        return child

    def create_batch(
        self,
        video_id: str,
        *,
        name: str,
        variations: list[str],
    ) -> Batch:
        return create_variation_batch(
            self,
            video_id,
            name=name,
            variations=variations,
        )

    def generate_batch(
        self,
        *,
        product_id: str | None,
        brief: str,
        reference_url: str | None,
        count: int,
        producer: str,
        script_settings: dict | None = None,
    ) -> tuple[Batch, list[ScriptCandidate]]:
        return generate_script_batch(
            self,
            product_id=product_id,
            brief=brief,
            reference_url=reference_url,
            count=count,
            producer=producer,
            script_settings=script_settings,
        )

    def create_account(self, account: Account) -> Account:
        self.repository.add_account(account)
        return account

    def create_group(self, group: AccountGroup) -> AccountGroup:
        self.repository.add_group(group)
        return group

    def create_product(self, product: Product) -> Product:
        self.repository.add_product(product)
        return product

    def _save_artifact_pair(
        self,
        video: Video,
        script_content: str,
        shots: list[StoryboardShot],
        source: ArtifactSource,
        note: str,
        claims_used: list[str] | None = None,
    ) -> None:
        now = utc_now()
        quality, claims, unsupported = assess_free_artifact(
            self, video, script_content, shots, claims_used
        )
        script = ScriptArtifact(
            id=new_id("script"),
            video_id=video.id,
            version=len(video.scripts) + 1,
            source=source,
            content=script_content,
            note=note,
            quality=quality,
            claims_used=claims,
            claims_needing_evidence=unsupported,
            created_at=now,
        )
        board = StoryboardArtifact(
            id=new_id("storyboard"),
            video_id=video.id,
            version=len(video.storyboards) + 1,
            source=source,
            shots=shots,
            note=note,
            created_at=now,
        )
        self.repository.add_artifact_pair(script, board)

    def _generation_context(self, video: Video) -> str:
        snapshot = self.snapshot()
        account_text = "\n".join(
            self._find_account(snapshot, item).context for item in video.account_ids
        )
        product = next((item for item in snapshot.products if item.id == video.product_id), None)
        product_text = ""
        if product:
            references = [
                f"商品链接（仅来源引用，未解析）：{product.url}" if product.url else "",
                f"商品主图（仅来源引用，未解析）：{product.image_url}" if product.image_url else "",
            ]
            product_text = "\n".join(
                item
                for item in (
                    f"商品：{product.title}",
                    f"商品描述：{product.description}",
                    f"卖点：{'；'.join(product.selling_points)}",
                    *references,
                )
                if item
            )
        context = video.contexts[-1] if video.contexts else None
        source_text = "\n".join(
            self._generation_source(item) for item in (context.sources if context else [])
        )
        sections = [
            account_text,
            product_text,
            context.brief if context else "",
            source_text,
            self._current_artifact_context(video),
        ]
        return "\n\n".join(item for item in sections if item)

    @staticmethod
    def _generation_source(source: ContextSource) -> str:
        values = [source.content] if source.content else []
        if source.href and source.href not in values:
            values.append(source.href)
        return f"{source.label}：{'\n'.join(values)}"

    @staticmethod
    def _current_artifact_context(video: Video) -> str:
        sections: list[str] = []
        if video.scripts:
            script = video.scripts[-1]
            sections.append(f"当前脚本 v{script.version}：\n{script.content}")
        if video.storyboards:
            board = video.storyboards[-1]
            shots = json.dumps(
                [item.model_dump() for item in board.shots],
                ensure_ascii=False,
            )
            sections.append(f"当前分镜 v{board.version}：\n{shots}")
        return "\n\n".join(sections)

    @staticmethod
    def _validate_references(
        snapshot: WorkspaceSnapshot,
        account_ids: list[str],
        product_id: str | None,
        parent_video_id: str | None,
    ) -> None:
        known_accounts = {item.id for item in snapshot.accounts}
        if any(item not in known_accounts for item in account_ids):
            raise ApplicationError("invalid_account", "选择的账号不存在或已经被移除。")
        if product_id and product_id not in {item.id for item in snapshot.products}:
            raise ApplicationError("invalid_product", "选择的商品不存在或已经被移除。")
        if parent_video_id and parent_video_id not in {item.video.id for item in snapshot.videos}:
            raise ApplicationError("invalid_parent", "父视频不存在，不能创建无法追溯的裂变视频。")

    @staticmethod
    def _find_video(snapshot: WorkspaceSnapshot, video_id: str) -> VideoView:
        view = next((item for item in snapshot.videos if item.video.id == video_id), None)
        if view is None:
            raise ApplicationError("not_found", "没有找到这条视频。")
        return view

    @staticmethod
    def _find_account(snapshot: WorkspaceSnapshot, account_id: str) -> Account:
        account = next((item for item in snapshot.accounts if item.id == account_id), None)
        if account is None:
            raise ApplicationError("not_found", "没有找到这个账号。")
        return account

    @staticmethod
    def _find_publication(snapshot: WorkspaceSnapshot, publication_id: str) -> Publication:
        for view in snapshot.videos:
            publication = next(
                (item for item in view.video.publications if item.id == publication_id),
                None,
            )
            if publication:
                return publication
        raise ApplicationError("not_found", "没有找到这条发布记录。")

    @staticmethod
    def _publication_by_external_id(
        snapshot: WorkspaceSnapshot,
        account_id: str,
        external_id: str,
    ) -> Publication | None:
        for view in snapshot.videos:
            for publication in view.video.publications:
                if publication.account_id == account_id and publication.external_id == external_id:
                    return publication
        return None

    def _adapter(self, platform: str):
        adapter = self.platform_adapters.get(platform)
        if adapter is None:
            raise ApplicationError(
                "connector_unavailable",
                "该平台只保留了接口，当前没有可运行连接器。",
            )
        return adapter

    def _publication_is_runnable(
        self,
        publication: Publication,
        platform: str,
    ) -> bool:
        if publication.status == PublicationStatus.UNKNOWN:
            raise ApplicationError(
                "needs_reconciliation",
                "平台结果未知，必须先核对，不能自动重试。",
            )
        if publication.status == PublicationStatus.SCHEDULED:
            if publication.external_id:
                return False
            if platform == "youtube":
                return True
            return self._schedule_is_due(publication.scheduled_at)
        return publication.status in {
            PublicationStatus.DRAFT,
            PublicationStatus.FAILED,
        }

    def _reconcile_publication(
        self,
        publication: Publication,
        remote: dict,
    ) -> Publication:
        state = publication_results.validate_remote_transition(publication, remote)
        updates = {
            "status": state,
            "url": remote.get("url") or publication.url,
            "published_at": remote.get("published_at") or publication.published_at,
            "updated_at": utc_now(),
        }
        reconciled = publication.model_copy(update=updates)
        if reconciled != publication:
            self.repository.update_publication(reconciled)
        return reconciled

    def _store_publication(
        self,
        publication: Publication,
        claim_token: str,
    ) -> Publication:
        if self.repository.finish_publication(publication, claim_token):
            return publication
        return self._find_publication(self.snapshot(), publication.id)

    @staticmethod
    def _new_publication(
        video: Video,
        account_id: str,
        media: MediaArtifact,
        scheduled_at: str | None,
    ) -> Publication:
        now = utc_now()
        seed = f"{video.id}:{account_id}:{media.checksum}:{scheduled_at or 'now'}"
        return Publication(
            id=new_id("publication"),
            video_id=video.id,
            account_id=account_id,
            status=PublicationStatus.SCHEDULED if scheduled_at else PublicationStatus.DRAFT,
            scheduled_at=scheduled_at,
            idempotency_key=sha256(seed.encode()).hexdigest(),
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _publication_for(
        video: Video,
        account_id: str,
        checksum: str,
        scheduled_at: str | None,
    ) -> Publication | None:
        seed = f"{video.id}:{account_id}:{checksum}:{scheduled_at or 'now'}"
        key = sha256(seed.encode()).hexdigest()
        return next((item for item in video.publications if item.idempotency_key == key), None)

    @staticmethod
    def _publish_request(video: Video, account: Account, publication: Publication) -> dict:
        media = video.media[-1]
        script = video.scripts[-1].content if video.scripts else video.goal
        scheduled_at = publication.scheduled_at
        if VideoOperationsService._schedule_is_due(scheduled_at):
            scheduled_at = None
        return {
            "idempotency_key": publication.idempotency_key,
            "account_ref": account.connector_ref,
            "account_id": account.id,
            "media_path": media.storage_path,
            "title": video.title,
            "description": script,
            "scheduled_at": scheduled_at,
            "simulate_failure": account.connection_status == ConnectionStatus.DISCONNECTED,
        }

    @staticmethod
    def _metric_recorded_recently(publication: Publication) -> bool:
        """30 分钟内已有快照就跳过记录，快照节流的唯一判断点。"""
        if not publication.metrics:
            return False
        latest = max(publication.metrics, key=lambda item: item.captured_at)
        try:
            captured = datetime.fromisoformat(latest.captured_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=UTC)
        return datetime.now(UTC) - captured < METRIC_SNAPSHOT_INTERVAL

    @staticmethod
    def _schedule_is_due(scheduled_at: str | None) -> bool:
        if not scheduled_at:
            return True
        try:
            scheduled = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ApplicationError(
                "invalid_schedule",
                "排期时间不是有效的 ISO 时间。",
            ) from exc
        if scheduled.tzinfo is None:
            raise ApplicationError("invalid_schedule", "排期时间必须包含时区。")
        return scheduled <= datetime.now(UTC)

    @staticmethod
    def _validate_new_schedule(scheduled_at: str | None) -> None:
        if not scheduled_at:
            return
        try:
            scheduled = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ApplicationError("invalid_input", "排期时间格式无效。") from exc
        if scheduled.tzinfo is None:
            raise ApplicationError("invalid_input", "排期时间必须包含时区。")
        if scheduled <= datetime.now(UTC):
            raise ApplicationError("invalid_input", "排期时间必须晚于当前时间。")
