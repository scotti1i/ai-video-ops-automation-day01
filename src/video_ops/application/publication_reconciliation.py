"""发布结果归一与人工核对；只改变对应发布记录。"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from video_ops.application.errors import ApplicationError, PlatformError
from video_ops.domain.models import Publication, PublicationStatus

LOGGER = logging.getLogger(__name__)
PUBLISH_LEASE = timedelta(hours=3)
PUBLISH_RECEIPT_STATES = {
    PublicationStatus.SCHEDULED,
    PublicationStatus.SUCCEEDED,
    PublicationStatus.SUCCEEDED_WITH_WARNINGS,
}
REMOTE_TRANSITIONS = {
    PublicationStatus.SCHEDULED: PUBLISH_RECEIPT_STATES,
    PublicationStatus.SUCCEEDED: {
        PublicationStatus.SUCCEEDED,
        PublicationStatus.SUCCEEDED_WITH_WARNINGS,
    },
    PublicationStatus.SUCCEEDED_WITH_WARNINGS: {
        PublicationStatus.SUCCEEDED,
        PublicationStatus.SUCCEEDED_WITH_WARNINGS,
    },
}
COMMENT_WARNING_PREFIXES = {"youtube": "YouTube 评论"}


def begin_publish(publication: Publication) -> tuple[Publication, str]:
    claimed = datetime.now(UTC)
    claim_token = f"claim-{uuid4().hex}"
    publishing = publication.model_copy(
        update={
            "status": PublicationStatus.PUBLISHING,
            "error": None,
            "claim_token": claim_token,
            "lease_expires_at": (claimed + PUBLISH_LEASE).isoformat(),
            "updated_at": claimed.isoformat(),
        }
    )
    return publishing, claim_token


def publish_once(adapter, request: dict, publication: Publication) -> Publication:
    try:
        receipt = adapter.publish(request)
    except PlatformError as exc:
        return record_publish_error(publication, exc, updated_at=_now())
    except Exception:
        LOGGER.exception("平台发布进程异常中断: %s", publication.id)
        error = PlatformError(
            "publish",
            "unknown_outcome",
            "发布进程异常中断，平台结果未知；核对前不会重试。",
        )
        return record_publish_error(publication, error, updated_at=_now())
    try:
        return record_publish_receipt(publication, receipt, updated_at=_now())
    except (KeyError, TypeError, ValueError):
        LOGGER.warning("平台返回了无法核验的发布回执: %s", publication.id)
        error = PlatformError(
            "publish",
            "invalid_receipt_unknown",
            "平台返回的发布回执不完整，结果未知；核对前不会重试。",
            raw_ref=receipt.get("raw_ref") if isinstance(receipt, dict) else None,
        )
        return record_publish_error(publication, error, updated_at=_now())


def _now() -> str:
    return datetime.now(UTC).isoformat()


def refresh_comment_warning(
    publication: Publication,
    *,
    platform: str,
    unavailable_reason: str | None,
    updated_at: str,
) -> Publication:
    prefix = COMMENT_WARNING_PREFIXES.get(platform)
    warnings = [
        warning
        for warning in publication.warnings
        if prefix is None or not warning.startswith(prefix)
    ]
    if unavailable_reason:
        warnings.append(unavailable_reason)
    warnings = list(dict.fromkeys(warnings))
    if warnings == publication.warnings:
        return publication
    return publication.model_copy(update={"warnings": warnings, "updated_at": updated_at})


def record_publish_error(
    publication: Publication,
    error: PlatformError,
    *,
    updated_at: str,
) -> Publication:
    unknown_codes = {"unknown_outcome", "timeout_unknown", "invalid_receipt_unknown"}
    status = (
        PublicationStatus.UNKNOWN
        if error.code in unknown_codes
        else PublicationStatus.FAILED
    )
    return publication.model_copy(
        update={
            "status": status,
            "error": error.message,
            "raw_ref": error.raw_ref,
            "claim_token": None,
            "lease_expires_at": None,
            "updated_at": updated_at,
        }
    )


def record_publish_receipt(
    publication: Publication,
    receipt: dict,
    *,
    updated_at: str,
) -> Publication:
    state = _publish_receipt_state(receipt)
    external_id = receipt["platform_content_id"]
    if not isinstance(external_id, str) or not external_id.strip():
        raise ValueError("platform_content_id is required")
    receipt_warnings = receipt.get("warnings", [])
    if not isinstance(receipt_warnings, list) or not all(
        isinstance(item, str) for item in receipt_warnings
    ):
        raise TypeError("warnings must be a list of strings")
    warnings = list(dict.fromkeys([*publication.warnings, *receipt_warnings]))
    return publication.model_copy(
        update={
            "status": state,
            "external_id": external_id.strip(),
            "url": receipt.get("url"),
            "published_at": receipt.get("published_at"),
            "warnings": warnings,
            "raw_ref": receipt.get("raw_ref"),
            "claim_token": None,
            "lease_expires_at": None,
            "updated_at": updated_at,
        }
    )


def _publish_receipt_state(receipt: dict) -> PublicationStatus:
    if not isinstance(receipt, dict):
        raise TypeError("publish receipt must be a mapping")
    state = PublicationStatus(receipt["state"])
    if state not in PUBLISH_RECEIPT_STATES:
        raise ValueError(f"invalid publish receipt state: {state}")
    return state


def validate_remote_transition(
    publication: Publication,
    remote: dict,
) -> PublicationStatus:
    try:
        state = PublicationStatus(remote["state"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ApplicationError(
            "invalid_platform_response",
            "平台返回的发布状态无法识别，本地记录未改变。",
        ) from exc
    if state not in REMOTE_TRANSITIONS.get(publication.status, set()):
        raise ApplicationError(
            "invalid_platform_response",
            f"平台状态不能从 {publication.status.value} 回退到 {state.value}。",
        )
    return state


def mark_interrupted(publication: Publication, *, updated_at: str) -> Publication:
    if publication.status != PublicationStatus.PUBLISHING or not _lease_expired(
        publication.lease_expires_at,
        updated_at,
    ):
        return publication
    return publication.model_copy(
        update={
            "status": PublicationStatus.UNKNOWN,
            "error": "发布进程曾中断，平台是否接收未知，请先核对。",
            "claim_token": None,
            "lease_expires_at": None,
            "updated_at": updated_at,
        }
    )


def _lease_expired(lease_expires_at: str | None, observed_at: str) -> bool:
    if not lease_expires_at:
        return True
    try:
        lease = datetime.fromisoformat(lease_expires_at.replace("Z", "+00:00"))
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if lease.tzinfo is None or observed.tzinfo is None:
        return True
    return lease <= observed


def reconcile_unknown_publication(
    publication: Publication,
    *,
    external_id: str,
    url: str,
    published_at: str | None,
    external_id_in_use: bool,
    updated_at: str,
) -> Publication:
    if publication.status != PublicationStatus.UNKNOWN:
        raise ApplicationError("invalid_state", "只有结果未知的任务需要人工核对。")
    platform_id = external_id.strip()
    if not platform_id or not url.strip():
        raise ApplicationError("invalid_input", "请填写核对后的平台视频编号和链接。")
    if external_id_in_use:
        raise ApplicationError("external_id_conflict", "该平台视频已关联到另一条记录。")
    return publication.model_copy(
        update={
            "status": PublicationStatus.SUCCEEDED,
            "external_id": platform_id,
            "url": url.strip(),
            "published_at": published_at,
            "error": None,
            "warnings": [*publication.warnings, "平台结果已由用户人工核对。"],
            "updated_at": updated_at,
        }
    )


def confirm_unknown_not_created(
    publication: Publication,
    *,
    note: str,
    updated_at: str,
) -> Publication:
    if publication.status != PublicationStatus.UNKNOWN:
        raise ApplicationError("invalid_state", "只有结果未知的任务需要人工核对。")
    audit_note = note.strip()
    if not audit_note:
        raise ApplicationError("invalid_input", "请填写在平台后台的核对说明。")
    warning = f"{updated_at} 人工核对：确认平台未创建，允许重试。说明：{audit_note}"
    return publication.model_copy(
        update={
            "status": PublicationStatus.FAILED,
            "error": "已人工确认平台未创建，可安全重试。",
            "warnings": [*publication.warnings, warning],
            "raw_ref": None,
            "updated_at": updated_at,
        }
    )
