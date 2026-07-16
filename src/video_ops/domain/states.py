"""领域状态只在这里计算，界面不维护第二套规则。"""

from __future__ import annotations

from .models import (
    MetricSnapshot,
    PerformanceSummary,
    Publication,
    PublicationStatus,
    StageSummary,
    Video,
    VideoStage,
)

STAGE_COPY: dict[VideoStage, tuple[str, str, str]] = {
    VideoStage.NEEDS_SCRIPT: ("待脚本", "生成脚本", "warning"),
    VideoStage.NEEDS_MEDIA: ("待成片", "上传成片", "warning"),
    VideoStage.READY_TO_PUBLISH: ("待发布", "安排发布", "brand"),
    VideoStage.PUBLISHING: ("发布中", "查看进度", "info"),
    VideoStage.SCHEDULED: ("已排期", "查看排期", "info"),
    VideoStage.PUBLISH_FAILED: ("发布失败", "查看原因", "danger"),
    VideoStage.NEEDS_RECONCILIATION: ("待核对", "核对平台", "danger"),
    VideoStage.PUBLISHED: ("已发布", "同步数据", "success"),
}


def _publication_stage(publications: list[Publication]) -> VideoStage:
    statuses = {item.status for item in publications}
    # 未知结果可能造成重复发布，优先于可重试的失败。
    if PublicationStatus.UNKNOWN in statuses:
        return VideoStage.NEEDS_RECONCILIATION
    if PublicationStatus.FAILED in statuses:
        return VideoStage.PUBLISH_FAILED
    if PublicationStatus.PUBLISHING in statuses:
        return VideoStage.PUBLISHING
    if PublicationStatus.DRAFT in statuses:
        return VideoStage.READY_TO_PUBLISH
    if PublicationStatus.SCHEDULED in statuses:
        return VideoStage.SCHEDULED
    return VideoStage.PUBLISHED


def stage_summary(video: Video) -> StageSummary:
    if not video.scripts or not video.storyboards:
        stage = VideoStage.NEEDS_SCRIPT
    elif not video.media:
        stage = VideoStage.NEEDS_MEDIA
    elif not video.publications:
        stage = VideoStage.READY_TO_PUBLISH
    else:
        stage = _publication_stage(video.publications)
    label, action, tone = STAGE_COPY[stage]
    return StageSummary(stage=stage, label=label, next_action=action, tone=tone)


def _latest_metric(publication: Publication) -> MetricSnapshot | None:
    if not publication.metrics:
        return None
    return max(publication.metrics, key=lambda item: item.captured_at)


def best_publication_metric(video: Video) -> tuple[Publication, MetricSnapshot] | None:
    """播放最高的那次发布及其最新快照；没有指标时返回 None。"""
    candidates = [(item, _latest_metric(item)) for item in video.publications]
    candidates = [(pub, metric) for pub, metric in candidates if metric is not None]
    return _peak(candidates, "views") if candidates else None


def _format_views(views: int) -> str:
    if views < 10_000:
        return str(views)
    text = f"{views / 10_000:.1f}".removesuffix(".0")
    return f"{text}万"


def _headline_clause(views: int, orders: int | None) -> str:
    if not orders:
        return f"最佳发布播放 {_format_views(views)}，暂无订单"
    conversion = orders / views * 100 if views else 0.0
    return (
        f"最佳发布播放 {_format_views(views)}、订单 {orders} 单"
        f"（转化率 {conversion:.2f}%，订单/播放口径）"
    )


def _median_clause(views: int, peer_median_views: float | None, peer_scope: str) -> str | None:
    if not peer_median_views or not views:
        return None
    return f"播放约为{peer_scope}中位数的 {views / peer_median_views:.1f} 倍"


def _comment_clause(video: Video) -> str | None:
    comments = [comment for pub in video.publications for comment in pub.comments]
    top = max(comments, key=lambda item: item.likes, default=None)
    if top is None:
        return None
    content = top.content if len(top.content) <= 40 else f"{top.content[:39]}…"
    return f"高赞评论（{top.likes} 赞）：「{content}」"


def performance_brief(
    video: Video,
    *,
    peer_median_views: float | None = None,
    peer_scope: str = "同批",
) -> str | None:
    """把最佳发布的回流数据提炼成给下一轮裂变用的一句中文，规则生成。"""
    best = best_publication_metric(video)
    if best is None:
        return None
    metric = best[1]
    views = metric.views or 0
    clauses = [
        _headline_clause(views, metric.orders),
        _median_clause(views, peer_median_views, peer_scope),
        _comment_clause(video),
    ]
    return "；".join(item for item in clauses if item) + "。"


def _peak(
    candidates: list[tuple[Publication, MetricSnapshot]],
    field: str,
) -> tuple[Publication, MetricSnapshot]:
    return max(candidates, key=lambda item: getattr(item[1], field) or 0)


def performance_summary(
    video: Video,
    traffic_threshold: int,
    order_threshold: int,
) -> PerformanceSummary:
    candidates = [(item, _latest_metric(item)) for item in video.publications]
    candidates = [(pub, metric) for pub, metric in candidates if metric is not None]
    if not candidates:
        return PerformanceSummary(label="待观察", tone="neutral")

    views_pub, views_metric = _peak(candidates, "views")
    orders_pub, orders_metric = _peak(candidates, "orders")
    revenue_pub, revenue_metric = _peak(candidates, "revenue")
    best_views = views_metric.views
    best_orders = orders_metric.orders
    best_revenue = revenue_metric.revenue
    high_traffic = (best_views or 0) >= traffic_threshold
    high_orders = (best_orders or 0) >= order_threshold
    if high_traffic and high_orders:
        label, tone = "流量成交双高", "success"
    elif high_orders:
        label, tone = "成交高", "success"
    elif high_traffic:
        label, tone = "流量高", "info"
    else:
        label, tone = "待观察", "neutral"
    source_ids = {
        views_pub.id if best_views is not None else None,
        orders_pub.id if best_orders is not None else None,
        revenue_pub.id if best_revenue is not None else None,
    } - {None}
    return PerformanceSummary(
        label=label,
        tone=tone,
        best_views=best_views,
        best_orders=best_orders,
        best_revenue=best_revenue,
        source_publication_id=source_ids.pop() if len(source_ids) == 1 else None,
    )
