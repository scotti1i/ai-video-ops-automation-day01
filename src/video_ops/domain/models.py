"""视频运营领域对象。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConnectionStatus(StrEnum):
    CONNECTED = "connected"
    NEEDS_AUTH = "needs_auth"
    MOCK = "mock"
    DISCONNECTED = "disconnected"


class ArtifactSource(StrEnum):
    MOCK = "mock"
    MODEL = "model"
    IMPORT = "import"
    USER = "user"
    EXTERNAL = "external"


class PublicationStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    SUCCEEDED = "succeeded"
    SUCCEEDED_WITH_WARNINGS = "succeeded_with_warnings"
    FAILED = "failed"
    UNKNOWN = "unknown"


class PublicationOrigin(StrEnum):
    SYSTEM = "system"
    IMPORTED = "imported"
    SAMPLE = "sample"


class VideoStage(StrEnum):
    NEEDS_SCRIPT = "needs_script"
    NEEDS_MEDIA = "needs_media"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHING = "publishing"
    SCHEDULED = "scheduled"
    PUBLISH_FAILED = "publish_failed"
    NEEDS_RECONCILIATION = "needs_reconciliation"
    PUBLISHED = "published"


class ContextSource(DomainModel):
    id: str
    kind: str
    label: str
    content: str = ""
    href: str | None = None
    file_name: str | None = None


class ContextSnapshot(DomainModel):
    id: str
    video_id: str
    version: int
    brief: str
    sources: list[ContextSource]
    created_at: str


class ScriptQualityCheck(DomainModel):
    key: str
    label: str
    passed: bool
    score: int = Field(ge=0)
    max_score: int = Field(gt=0)
    detail: str


class ScriptQuality(DomainModel):
    status: str = Field(pattern="^(ready_to_test|needs_revision)$")
    score: int = Field(ge=0, le=100)
    checks: list[ScriptQualityCheck]
    risks: list[str] = Field(default_factory=list)


class StoryboardShot(DomainModel):
    order: int
    duration_seconds: int = Field(ge=1, le=120)
    visual: str
    voiceover: str
    on_screen_text: str = ""
    role: str = ""


class ScriptArtifact(DomainModel):
    id: str
    video_id: str
    version: int
    source: ArtifactSource
    content: str
    note: str = ""
    quality: ScriptQuality | None = None
    claims_used: list[str] = Field(default_factory=list)
    claims_needing_evidence: list[str] = Field(default_factory=list)
    created_at: str


class StoryboardArtifact(DomainModel):
    id: str
    video_id: str
    version: int
    source: ArtifactSource
    shots: list[StoryboardShot]
    note: str = ""
    created_at: str


class MediaArtifact(DomainModel):
    id: str
    video_id: str
    file_name: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    checksum: str
    storage_path: str
    source: ArtifactSource
    status: str
    created_at: str


class MetricSnapshot(DomainModel):
    id: str
    publication_id: str
    captured_at: str
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    orders: int | None = Field(default=None, ge=0)
    revenue: float | None = Field(default=None, ge=0)
    raw: dict[str, Any] = Field(default_factory=dict)


class CommentSnapshot(DomainModel):
    id: str
    publication_id: str
    external_id: str
    author: str
    content: str
    likes: int = Field(default=0, ge=0)
    commented_at: str
    captured_at: str
    raw: dict[str, Any] = Field(default_factory=dict)


class AccountGroup(DomainModel):
    id: str
    name: str
    sort_order: int = 0


class Account(DomainModel):
    id: str
    group_id: str
    name: str
    handle: str
    platform: str
    connection_status: ConnectionStatus
    context: str = ""
    connector_ref: str | None = None


class Product(DomainModel):
    id: str
    title: str
    description: str
    selling_points: list[str]
    url: str | None = None
    image_url: str | None = None


NarrativeBlock = Literal["problem", "proof", "objection"]
NARRATIVE_BLOCKS = ("problem", "proof", "objection")


class ScriptSettings(DomainModel):
    """批次级创作设定快照。

    API 只开放 20/25/30 秒；领域层保留 15–60 秒是为了承接旧 Context
    里已经存在的自定义时长，不在迁移时暗改历史意图。
    """

    language: Literal["zh-CN", "en-US"]
    writing_tone: Literal["natural", "direct", "warm", "expert"] = "natural"
    duration_seconds: int = Field(default=25, ge=15, le=60)
    narrative_blocks: list[NarrativeBlock] = Field(
        default_factory=lambda: list(NARRATIVE_BLOCKS)
    )

    @field_validator("narrative_blocks")
    @classmethod
    def validate_narrative_blocks(cls, value: list[NarrativeBlock]) -> list[NarrativeBlock]:
        if len(value) != len(NARRATIVE_BLOCKS) or set(value) != set(NARRATIVE_BLOCKS):
            raise ValueError("叙事中段必须各包含一次 problem、proof 和 objection")
        return value


class Publication(DomainModel):
    id: str
    video_id: str
    account_id: str
    status: PublicationStatus
    origin: PublicationOrigin = PublicationOrigin.SYSTEM
    scheduled_at: str | None = None
    published_at: str | None = None
    external_id: str | None = None
    url: str | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    raw_ref: str | None = None
    claim_token: str | None = Field(default=None, exclude=True)
    lease_expires_at: str | None = Field(default=None, exclude=True)
    idempotency_key: str
    created_at: str
    updated_at: str
    metrics: list[MetricSnapshot] = Field(default_factory=list)
    comments: list[CommentSnapshot] = Field(default_factory=list)


class Video(DomainModel):
    id: str
    code: str
    title: str
    goal: str
    account_ids: list[str]
    product_id: str | None = None
    parent_video_id: str | None = None
    variation_note: str | None = None
    batch_id: str | None = None
    created_at: str
    updated_at: str
    external_video_id: str | None = None
    contexts: list[ContextSnapshot] = Field(default_factory=list)
    scripts: list[ScriptArtifact] = Field(default_factory=list)
    storyboards: list[StoryboardArtifact] = Field(default_factory=list)
    media: list[MediaArtifact] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)


class Batch(DomainModel):
    id: str
    name: str
    video_ids: list[str] = Field(default_factory=list)
    product_id: str | None = None
    brief: str = ""
    reference_url: str | None = None
    script_settings: ScriptSettings | None = None
    note: str = ""
    candidates: list[ScriptCandidate] = Field(default_factory=list)
    created_at: str


class ScriptCandidate(DomainModel):
    id: str
    batch_id: str
    position: int = Field(ge=1)
    title: str
    angle: str
    hypothesis: str
    script: str
    shots: list[StoryboardShot]
    provider: str
    claims_used: list[str] = Field(default_factory=list)
    claims_needing_evidence: list[str] = Field(default_factory=list)
    quality: ScriptQuality
    selected_video_id: str | None = None
    created_at: str
    updated_at: str


class StageSummary(DomainModel):
    stage: VideoStage
    label: str
    next_action: str
    tone: str


class PerformanceSummary(DomainModel):
    label: str
    tone: str
    best_views: int | None = None
    best_orders: int | None = None
    best_revenue: float | None = None
    source_publication_id: str | None = None


class VideoView(DomainModel):
    video: Video
    stage: StageSummary
    performance: PerformanceSummary
    # 已发布且有指标时的中文表现提炼（规则生成），否则 None；前端契约字段。
    performance_brief: str | None = None


class WorkspaceSnapshot(DomainModel):
    id: str
    name: str
    mode: str
    traffic_threshold: int
    order_threshold: int
    account_groups: list[AccountGroup]
    accounts: list[Account]
    products: list[Product]
    batches: list[Batch]
    videos: list[VideoView]
