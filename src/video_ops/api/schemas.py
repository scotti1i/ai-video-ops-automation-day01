"""HTTP 输入合同；输出直接复用领域对象。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from video_ops.domain.models import (
    NARRATIVE_BLOCKS,
    ConnectionStatus,
    NarrativeBlock,
    StoryboardShot,
)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextSourceInput(RequestModel):
    kind: str = "text"
    label: str
    content: str = ""
    href: str | None = None
    file_name: str | None = None


class CreateVideoRequest(RequestModel):
    title: str = Field(min_length=1, max_length=100)
    goal: str = Field(min_length=1, max_length=1000)
    account_ids: list[str] = Field(default_factory=list)
    product_id: str | None = None
    brief: str = ""
    sources: list[ContextSourceInput] = Field(default_factory=list)
    parent_video_id: str | None = None
    variation_note: str | None = None
    batch_id: str | None = None


class UpdateVideoTitleRequest(RequestModel):
    title: str = Field(min_length=1, max_length=100)


class ScriptSettingsInput(RequestModel):
    language: Literal["zh-CN", "en-US"] | None = None
    writing_tone: Literal["natural", "direct", "warm", "expert"] = "natural"
    duration_seconds: Literal[20, 25, 30] | None = None
    narrative_blocks: list[NarrativeBlock] = Field(
        default_factory=lambda: list(NARRATIVE_BLOCKS)
    )

    @field_validator("narrative_blocks")
    @classmethod
    def validate_narrative_blocks(cls, value: list[NarrativeBlock]) -> list[NarrativeBlock]:
        if len(value) != len(NARRATIVE_BLOCKS) or set(value) != set(NARRATIVE_BLOCKS):
            raise ValueError("叙事中段必须各包含一次 problem、proof 和 objection")
        return value


class GenerateBatchRequest(RequestModel):
    product_id: str | None = None
    brief: str = Field(default="", max_length=20_000)
    reference_url: str | None = Field(default=None, max_length=2000)
    count: int = Field(default=10, ge=1, le=10)
    producer: str = Field(default="mock", min_length=1, max_length=40)
    script_settings: ScriptSettingsInput | None = None


class UpdateCandidateRequest(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    script: str = Field(min_length=1, max_length=40_000)
    shots: list[StoryboardShot] = Field(min_length=1, max_length=12)


class RegenerateCandidateRequest(RequestModel):
    producer: str = Field(default="mock", min_length=1, max_length=40)


class SelectCandidatesRequest(RequestModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=20)


class GenerateArtifactsRequest(RequestModel):
    instruction: str = Field(default="根据 Context 生成脚本和分镜", min_length=1, max_length=4000)
    producer: str = Field(default="mock", min_length=1, max_length=40)


class ImportArtifactsRequest(RequestModel):
    script: str = Field(min_length=1)
    shots: list[StoryboardShot] | None = None
    note: str = Field(default="外部脚本导入", max_length=240)


class UpdateScriptRequest(RequestModel):
    content: str = Field(min_length=1)
    note: str = Field(default="直接编辑", max_length=240)
    shots: list[StoryboardShot] | None = None


class RegisterMediaRequest(RequestModel):
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(default="application/octet-stream", max_length=120)
    size_bytes: int = Field(gt=0)
    checksum: str = Field(min_length=1, max_length=160)
    storage_path: str = Field(min_length=1, max_length=2000)
    source: Literal["external", "user"] = "external"


class ArrangePublicationsRequest(RequestModel):
    account_ids: list[str] = Field(min_length=1)
    scheduled_at: str | None = None
    auto_execute_mock: bool = True


class ExecutePublicationRequest(RequestModel):
    confirmed: bool = False


class ImportPublicationRequest(RequestModel):
    account_id: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    published_at: str | None = None


class ReconcilePublicationRequest(RequestModel):
    external_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    published_at: str | None = None


class ConfirmPublicationAbsentRequest(RequestModel):
    confirmed_absent: Literal[True]
    note: str = Field(min_length=1, max_length=500)


class BranchVideoRequest(RequestModel):
    variation: str = Field(min_length=1, max_length=1000)
    comment_ids: list[str] = Field(default_factory=list)


class CreateBatchRequest(RequestModel):
    name: str = Field(min_length=1, max_length=160)
    variations: list[str] = Field(min_length=1, max_length=50)


class WorkspaceImportRequest(RequestModel):
    format: Literal["json", "csv"]
    payload: str = Field(min_length=1, max_length=5_000_000)
    mapping: dict[str, str] = Field(default_factory=dict)
    conflict_strategy: Literal["skip"] = "skip"


class CreateAccountGroupRequest(RequestModel):
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0


class CreateAccountRequest(RequestModel):
    group_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=120)
    handle: str = Field(min_length=1, max_length=160)
    platform: Literal["youtube", "mock-social", "tiktok", "douyin"]
    connection_status: ConnectionStatus = ConnectionStatus.NEEDS_AUTH
    context: str = Field(default="", max_length=8000)
    connector_ref: str | None = Field(default=None, max_length=500)


class CreateProductRequest(RequestModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=20_000)
    selling_points: list[str] = Field(default_factory=list, max_length=100)
    url: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=2000)
