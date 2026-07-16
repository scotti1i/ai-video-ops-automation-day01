"""业务核心依赖的可替换合同。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .models import (
    Account,
    AccountGroup,
    Batch,
    CommentSnapshot,
    ConnectionStatus,
    ContextSnapshot,
    MediaArtifact,
    MetricSnapshot,
    Product,
    Publication,
    ScriptArtifact,
    ScriptCandidate,
    StoryboardArtifact,
    StoryboardShot,
    Video,
    WorkspaceSnapshot,
)


class CandidateVersionConflict(RuntimeError):
    """候选在读取后被修改或冻结，调用方必须刷新再决定。"""


class ScriptResult(Protocol):
    script: str
    shots: list[StoryboardShot]
    provider: str
    hook: str
    primary_promise: str
    proof: str
    objection: str
    cta: str
    claims: list[str]


class ScriptProducer(Protocol):
    def produce(self, context: str, instruction: str) -> ScriptResult: ...


class ClosedClaimTemplateProducer:
    """仅供仓库内封闭模板显式继承的声明审计标记。"""

    def has_closed_claim_template(self, context: str) -> bool:
        return False


class ProductionProvider(Protocol):
    """External making/editing modules can only return tasks or finished media."""

    name: str

    def capabilities(self) -> dict[str, bool]: ...

    def submit(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def get_task(self, external_task_id: str) -> dict[str, Any]: ...

    def collect_media(self, external_task_id: str) -> MediaArtifact | None: ...


@runtime_checkable
class PlatformAdapter(Protocol):
    platform: str

    def capabilities(self) -> dict[str, bool]: ...

    def inspect_account(self, connector_ref: str | None) -> dict[str, Any]: ...

    def publish(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def get_publication(self, external_id: str) -> dict[str, Any]: ...

    def collect_metrics(
        self,
        publication_id: str,
        external_id: str,
        previous: MetricSnapshot | None = None,
    ) -> MetricSnapshot: ...

    def collect_comments(
        self,
        publication_id: str,
        external_id: str,
    ) -> tuple[list[CommentSnapshot], str | None]: ...


class WorkspaceSync(Protocol):
    """Tables such as Feishu map records without owning domain state."""

    name: str

    def preview_import(self, records: list[dict[str, Any]]) -> dict[str, Any]: ...

    def import_records(self, records: list[dict[str, Any]]) -> dict[str, Any]: ...

    def export_snapshot(self, snapshot: WorkspaceSnapshot) -> list[dict[str, Any]]: ...


class WorkspaceRepository(Protocol):
    """Persistence boundary consumed by the application service."""

    def initialize(self) -> None: ...

    def snapshot(self) -> WorkspaceSnapshot: ...

    def transaction(self): ...

    def add_group(self, group: AccountGroup) -> None: ...

    def add_account(self, account: Account) -> None: ...

    def update_account_connection(
        self,
        account_id: str,
        status: ConnectionStatus,
        connector_ref: str | None,
    ) -> None: ...

    def add_product(self, product: Product) -> None: ...

    def add_batch(self, batch: Batch) -> None: ...

    def add_candidate(self, candidate: ScriptCandidate) -> None: ...

    def update_candidate(self, candidate: ScriptCandidate) -> bool: ...

    def select_candidate(
        self,
        candidate_id: str,
        expected_updated_at: str,
        video: Video,
        context: ContextSnapshot,
        script: ScriptArtifact,
        storyboard: StoryboardArtifact,
    ) -> str: ...

    def add_video_with_context(self, video: Video, context: ContextSnapshot) -> None: ...

    def update_video_title(self, video_id: str, title: str, updated_at: str) -> None: ...

    def add_script(self, script: ScriptArtifact) -> None: ...

    def add_storyboard(self, storyboard: StoryboardArtifact) -> None: ...

    def add_artifact_pair(
        self,
        script: ScriptArtifact,
        storyboard: StoryboardArtifact,
    ) -> None: ...

    def add_media(self, media: MediaArtifact) -> None: ...

    def add_publication(self, publication: Publication) -> None: ...

    def add_publication_with_account_link(self, publication: Publication) -> None: ...

    def update_publication(self, publication: Publication) -> None: ...

    def claim_publication(self, publication: Publication, claimed: Publication) -> bool: ...

    def finish_publication(
        self,
        publication: Publication,
        expected_claim_token: str | None,
    ) -> bool: ...

    def add_metric(self, metric: MetricSnapshot) -> None: ...

    def upsert_comment(self, comment: CommentSnapshot) -> None: ...

    def replace_video_accounts(self, video_id: str, account_ids: list[str]) -> None: ...
