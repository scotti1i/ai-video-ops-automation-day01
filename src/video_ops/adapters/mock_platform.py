"""零密钥平台实现，覆盖成功、失败、延迟、指标和评论。

指标不是随机数生成器：每个外部编号先按哈希落进爆款/普通/扑街三档（约 2:6:2），
播放沿 S 型曲线随"发布后经过时长"爬升再进入平台期，订单按 播放×点击率×转化率
推导，收入等于订单×单价。同一发布在同一时刻永远得到同一条曲线，时钟可注入。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from video_ops.application.errors import PlatformError
from video_ops.domain.models import CommentSnapshot, MetricSnapshot


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _stable_number(value: str, minimum: int, span: int) -> int:
    digest = sha256(value.encode()).hexdigest()
    return minimum + int(digest[:8], 16) % span


def _stable_ratio(value: str, minimum: float, maximum: float) -> float:
    return minimum + (maximum - minimum) * (_stable_number(value, 0, 10_000) / 10_000)


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


@dataclass(frozen=True)
class _TrafficProfile:
    """一条发布的流量档位：平台期规模、增长节奏和转化链路。"""

    name: str
    plateau_views: int
    midpoint_hours: float
    steepness: float
    click_rate: float
    conversion_rate: float


def _profile_for(external_id: str) -> _TrafficProfile:
    """按外部编号哈希分档，约 2:6:2 的爆款/普通/扑街。"""
    bucket = _stable_number(f"profile:{external_id}", 0, 10)
    if bucket < 2:
        return _TrafficProfile(
            name="爆款",
            plateau_views=_stable_number(f"plateau:{external_id}", 180_000, 320_001),
            midpoint_hours=float(_stable_number(f"mid:{external_id}", 14, 9)),
            steepness=_stable_ratio(f"steep:{external_id}", 0.12, 0.18),
            click_rate=_stable_ratio(f"click:{external_id}", 0.020, 0.030),
            conversion_rate=_stable_ratio(f"convert:{external_id}", 0.007, 0.011),
        )
    if bucket < 8:
        return _TrafficProfile(
            name="普通",
            plateau_views=_stable_number(f"plateau:{external_id}", 6_000, 42_001),
            midpoint_hours=float(_stable_number(f"mid:{external_id}", 24, 13)),
            steepness=_stable_ratio(f"steep:{external_id}", 0.07, 0.11),
            click_rate=_stable_ratio(f"click:{external_id}", 0.012, 0.020),
            conversion_rate=_stable_ratio(f"convert:{external_id}", 0.004, 0.007),
        )
    return _TrafficProfile(
        name="扑街",
        plateau_views=_stable_number(f"plateau:{external_id}", 400, 2_201),
        midpoint_hours=float(_stable_number(f"mid:{external_id}", 6, 7)),
        steepness=_stable_ratio(f"steep:{external_id}", 0.25, 0.40),
        click_rate=_stable_ratio(f"click:{external_id}", 0.006, 0.012),
        conversion_rate=_stable_ratio(f"convert:{external_id}", 0.001, 0.004),
    )


def _curve_progress(elapsed_hours: float, midpoint_hours: float, steepness: float) -> float:
    """S 型累计曲线：0 起步，增速先爬升后衰减，最终停在 1.0 的平台期。"""

    def logistic(hours: float) -> float:
        return 1.0 / (1.0 + math.exp(-steepness * (hours - midpoint_hours)))

    start = logistic(0.0)
    return max(0.0, (logistic(elapsed_hours) - start) / (1.0 - start))


def _publish_anchor(external_id: str, previous: MetricSnapshot | None, now: datetime) -> datetime:
    """曲线时间零点：沿用上一条快照记录的锚点，保证同一发布可复现。"""
    stored = previous.raw.get("published_anchor") if previous else None
    if isinstance(stored, str) and (parsed := _parse_datetime(stored)):
        return parsed
    base = _parse_datetime(previous.captured_at) if previous else None
    initial_age = timedelta(hours=_stable_number(f"age:{external_id}", 2, 5))
    return (base or now) - initial_age


def _unit_price(external_id: str) -> float:
    """商品单价按外部编号哈希落在 19.9–49.9。"""
    return round(19.9 + _stable_number(f"price:{external_id}", 0, 301) / 10, 2)


def _no_less_than_previous(value: int, previous: MetricSnapshot | None, field: str) -> int:
    """累计口径的指标只增不减，种子自带的历史高点不被抹掉。"""
    floor = getattr(previous, field) if previous else None
    return max(value, floor or 0)


class MockPlatformAdapter:
    platform = "mock-social"
    _clock: Callable[[], datetime] = staticmethod(_utc_now)

    def __init__(self, clock: Callable[[], datetime] | None = None):
        if clock is not None:
            self._clock = clock

    def capabilities(self) -> dict[str, bool]:
        return {
            "publish": True,
            "schedule": True,
            "thumbnail": True,
            "basic_metrics": True,
            "comments": True,
        }

    def inspect_account(self, connector_ref: str | None) -> dict:
        return {
            "platform_account_id": connector_ref or "mock-account",
            "display_name": "样例社媒账号",
            "handle": "@demo_social",
            "raw_ref": "sample://accounts/mock-account",
        }

    def publish(self, request: dict) -> dict:
        if request.get("simulate_failure"):
            raise PlatformError(
                "publish",
                "platform_rejected",
                "样例平台拒绝了这条任务；请检查账号连接后重试。",
                retryable=True,
            )
        suffix = sha256(request["idempotency_key"].encode()).hexdigest()[:10]
        return {
            "state": "succeeded",
            "platform_content_id": f"mock-{suffix}",
            "url": f"https://example.invalid/video/mock-{suffix}",
            "published_at": self._clock().isoformat(),
            "warnings": [],
            "raw_ref": f"sample://publications/mock-{suffix}",
        }

    def get_publication(self, external_id: str) -> dict:
        return {
            "state": "succeeded",
            "platform_content_id": external_id,
            "url": f"https://example.invalid/video/{external_id}",
        }

    def collect_metrics(
        self,
        publication_id: str,
        external_id: str,
        previous: MetricSnapshot | None = None,
    ) -> MetricSnapshot:
        now = self._clock()
        anchor = _publish_anchor(external_id, previous, now)
        profile = _profile_for(external_id)
        elapsed_hours = max(0.0, (now - anchor).total_seconds() / 3600)
        progress = _curve_progress(elapsed_hours, profile.midpoint_hours, profile.steepness)
        views = _no_less_than_previous(int(profile.plateau_views * progress), previous, "views")
        order_rate = (
            profile.click_rate
            * profile.conversion_rate
            * _stable_ratio(f"order-jitter:{external_id}", 0.9, 1.1)
        )
        orders = _no_less_than_previous(int(views * order_rate), previous, "orders")
        revenue = round(orders * _unit_price(external_id), 2)
        if previous and previous.revenue:
            revenue = max(revenue, previous.revenue)
        return MetricSnapshot(
            id=f"metric-{sha256((now.isoformat() + publication_id).encode()).hexdigest()[:16]}",
            publication_id=publication_id,
            captured_at=now.isoformat(),
            views=views,
            likes=self._engagement(views, previous, "likes", external_id, 0.020, 0.055),
            comments=self._engagement(views, previous, "comments", external_id, 0.0007, 0.0016),
            shares=self._engagement(views, previous, "shares", external_id, 0.0004, 0.0009),
            orders=orders,
            revenue=revenue,
            raw={
                "sample": True,
                "source": "mock-social",
                "profile": profile.name,
                "published_anchor": anchor.isoformat(),
            },
        )

    @staticmethod
    def _engagement(
        views: int,
        previous: MetricSnapshot | None,
        field: str,
        external_id: str,
        minimum: float,
        maximum: float,
    ) -> int:
        """互动量按确定性比例跟随播放。"""
        rate = _stable_ratio(f"{field}:{external_id}", minimum, maximum)
        return _no_less_than_previous(int(views * rate), previous, field)

    def collect_comments(
        self,
        publication_id: str,
        external_id: str,
    ) -> tuple[list[CommentSnapshot], str | None]:
        captured = self._clock().isoformat()
        rows = [
            ("c1", "Mia", "能不能换一个更日常的场景再测一次？", 37),
            ("c2", "Alex", "前两秒直接给结果，我会更想看下去。", 21),
        ]
        comments = [
            CommentSnapshot(
                id=f"comment-{external_id}-{comment_id}",
                publication_id=publication_id,
                external_id=f"{external_id}-{comment_id}",
                author=author,
                content=content,
                likes=likes,
                commented_at=captured,
                captured_at=captured,
                raw={"sample": True},
            )
            for comment_id, author, content, likes in rows
        ]
        return comments, None
