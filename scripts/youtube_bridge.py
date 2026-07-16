#!/usr/bin/env python3
"""只读调用现有 YouTube 凭据，不触发交互授权、不输出凭据。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
COMMENT_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


def emit(payload: dict, code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(code)


def credentials(uploader_dir: Path):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token = uploader_dir / "token.json"
    if not token.exists():
        emit({"ok": False, "code": "auth_required", "message": "YouTube token 不存在"}, 2)
    creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            emit({"ok": False, "code": "auth_expired", "message": "YouTube 授权已失效"}, 2)
    if not creds.valid:
        emit({"ok": False, "code": "auth_required", "message": "YouTube 授权不可用"}, 2)
    return creds


def youtube_client(uploader_dir: Path):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=credentials(uploader_dir), cache_discovery=False)


def comment_token_reason(token: Path) -> str | None:
    if not token.is_file():
        return "YouTube 评论授权文件不存在"
    try:
        data = json.loads(token.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "YouTube 评论授权文件不可读取"
    if COMMENT_SCOPE not in set(data.get("scopes") or []):
        return "YouTube 评论读取缺少 youtube.force-ssl 授权"
    return None


def comment_client(token: Path):
    """评论使用独立授权；失败只降级评论，不吞掉视频指标。"""
    reason = comment_token_reason(token)
    if reason:
        return None, reason
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(token))
    try:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
    except RefreshError:
        return None, "YouTube 评论授权已失效"
    if not creds.valid:
        return None, "YouTube 评论授权不可用"
    return build("youtube", "v3", credentials=creds, cache_discovery=False), None


def inspect_account(uploader_dir: Path) -> None:
    client = youtube_client(uploader_dir)
    response = client.channels().list(part="snippet,statistics", mine=True).execute()
    items = response.get("items", [])
    if not items:
        emit({"ok": False, "code": "not_found", "message": "授权账号没有 YouTube 频道"}, 3)
    channels = [
        {
            "id": item["id"],
            "title": item["snippet"].get("title", ""),
            "handle": item["snippet"].get("customUrl", ""),
            "video_count": item.get("statistics", {}).get("videoCount"),
        }
        for item in items
    ]
    emit({"ok": True, "channels": channels})


def collect(uploader_dir: Path, video_id: str, comment_token: Path | None) -> None:
    from googleapiclient.errors import HttpError

    client = youtube_client(uploader_dir)
    response = client.videos().list(part="snippet,statistics,status", id=video_id).execute()
    items = response.get("items", [])
    if not items:
        emit({"ok": False, "code": "not_found", "message": "没有找到该 YouTube 视频"}, 3)
    video = items[0]
    comments = []
    comment_api, unavailable_reason = comment_client(
        comment_token or uploader_dir / "token.json"
    )
    if comment_api:
        try:
            comment_response = comment_api.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=50,
                order="relevance",
                textFormat="plainText",
            ).execute()
            comments = extract_comments(comment_response)
        except HttpError as exc:
            unavailable_reason = comment_unavailable_reason(exc)
            if unavailable_reason is None:
                raise
    emit(
        {
            "ok": True,
            "video": {
                "id": video["id"],
                "title": video["snippet"].get("title", ""),
                "published_at": video["snippet"].get("publishedAt"),
                "privacy_status": video["status"].get("privacyStatus"),
                "publish_at": video["status"].get("publishAt"),
                "statistics": video.get("statistics", {}),
            },
            "comments": comments,
            "comments_unavailable_reason": unavailable_reason,
        }
    )


def extract_comments(response: dict) -> list[dict]:
    rows = []
    for item in response.get("items", []):
        snippet = item["snippet"]["topLevelComment"]["snippet"]
        rows.append(
            {
                "id": item["snippet"]["topLevelComment"]["id"],
                "author": snippet.get("authorDisplayName", "YouTube 用户"),
                "content": snippet.get("textDisplay", ""),
                "likes": snippet.get("likeCount", 0),
                "published_at": snippet.get("publishedAt"),
                "total_reply_count": item["snippet"].get("totalReplyCount", 0),
                "replies_included": len(item.get("replies", {}).get("comments", [])),
            }
        )
    return rows


def http_error_reason(exc) -> str:
    try:
        payload = json.loads(exc.content.decode("utf-8"))
        errors = payload.get("error", {}).get("errors", [])
        return errors[0].get("reason", "") if errors else ""
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return ""


def comment_unavailable_reason(exc) -> str | None:
    """把评论级权限限制留成证据，不让它吞掉已经读到的指标。"""
    if getattr(exc.resp, "status", None) != 403:
        return None
    reason = http_error_reason(exc)
    if reason == "commentsDisabled":
        return "YouTube 评论已关闭"
    if reason in {"forbidden", "insufficientPermissions"}:
        return "YouTube 评论当前授权不可读取"
    return None


def classify_error(exc: Exception) -> tuple[str, str, bool]:
    try:
        from googleapiclient.errors import HttpError
    except ModuleNotFoundError:
        HttpError = ()
    if isinstance(exc, HttpError):
        reason = http_error_reason(exc)
        if reason in {"quotaExceeded", "dailyLimitExceeded"}:
            return "quota_exceeded", "YouTube API 配额已用完", True
        if reason in {"rateLimitExceeded", "userRateLimitExceeded"}:
            return "rate_limited", "YouTube API 调用过于频繁", True
        if reason in {"authError", "insufficientPermissions", "forbidden"}:
            return "auth_required", "YouTube 授权不足或已失效", False
        if getattr(exc.resp, "status", None) == 404:
            return "not_found", "YouTube 资源不存在", False
        return "youtube_error", f"YouTube API 调用失败 ({reason or exc.resp.status})", True
    if isinstance(exc, TimeoutError):
        return "timeout", "YouTube API 调用超时", True
    return "youtube_error", f"YouTube 调用失败 ({type(exc).__name__})", False


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--uploader-dir", type=Path, required=True)
    parser.add_argument("--comment-token", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect")
    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--video-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            inspect_account(args.uploader_dir)
        else:
            collect(args.uploader_dir, args.video_id, args.comment_token)
    except Exception as exc:
        code, message, retryable = classify_error(exc)
        emit(
            {
                "ok": False,
                "code": code,
                "message": message,
                "retryable": retryable,
            },
            4,
        )


if __name__ == "__main__":
    main()
