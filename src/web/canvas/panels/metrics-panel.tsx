import { Button, EmptyState, InlineAlert, toast } from "@fifty/workbench-ui";
import { ChevronRight, LineChart } from "lucide-react";
import { useMemo, useState } from "react";
import { api, ApiError } from "../../api";
import type { CommentSnapshot, Publication, VideoView, Workspace } from "../../domain";
import { formatDate, formatMoney, formatNumber } from "../../format";
import type { PanelProps } from "./types";

// ============================================================
// 「数据回流」面板（design-v7-canvas.md：各发布任务的指标快照与评论）
//
// 跨视频的汇总视角：一条已发布视频一行——最佳播放/订单/成交、快照时间点、
// 观众评论、一个同步动作。单条细节点标题进详情抽屉，不在这里重画一遍。
// 「谁赢了、赢在哪个变量」是「提炼」面板的事；这里只回流事实，不下判断。
// ============================================================

interface MetricsRow {
  view: VideoView;
  /** 已经拿到平台编号的发布任务：只有它们能同步数据 */
  tasks: Publication[];
  snapshots: number;
  /** 最近一次快照时间，跨发布任务取最新 */
  capturedAt: string | null;
  /** 跨发布任务合并、按点赞排序的观众评论 */
  comments: CommentSnapshot[];
}

function buildRow(view: VideoView): MetricsRow {
  const tasks = view.video.publications.filter((item) => item.external_id);
  const captured = tasks.flatMap((task) => task.metrics.map((metric) => metric.captured_at)).sort();
  return {
    view,
    tasks,
    snapshots: tasks.reduce((total, task) => total + task.metrics.length, 0),
    capturedAt: captured.at(-1) ?? null,
    comments: tasks.flatMap((task) => task.comments).sort((a, b) => b.likes - a.likes),
  };
}

function buildRows(workspace: Workspace): MetricsRow[] {
  return workspace.videos
    .map(buildRow)
    .filter((row) => row.tasks.length > 0)
    // 跑得好的排前面：这一屏先回答“哪条值得带去下一批”
    .sort((a, b) => (b.view.performance.best_views ?? -1) - (a.view.performance.best_views ?? -1));
}

function SyncAction({ row, onChanged }: { row: MetricsRow; onChanged: () => Promise<void> }) {
  const [pending, setPending] = useState(false);
  const sync = async () => {
    setPending(true);
    // 一行 = 一条视频，可能发在多个账号：一次把这条的发布任务全同步，不让用户逐个点
    try {
      await Promise.all(row.tasks.map((task) => api.sync(task.id)));
      await onChanged();
      toast.success("数据已同步");
    } catch (cause) {
      toast.error(cause instanceof ApiError ? cause.message : "同步失败");
    } finally {
      setPending(false);
    }
  };
  return <Button aria-label={`同步「${row.view.video.title}」的数据`} className="min-h-11 shrink-0 sm:min-h-9" loading={pending} loadingLabel="同步中" onClick={() => void sync()} size="sm" variant="secondary">同步数据</Button>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><dt className="text-xs text-ink-muted">{label}</dt><dd className="m-0 mt-1 break-all text-sm font-semibold tabular-nums text-ink">{value}</dd></div>;
}

function Comments({ comments }: { comments: CommentSnapshot[] }) {
  const top = comments.slice(0, 3);
  return (
    <details className="group">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded-md text-[13px] text-ink-soft outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 sm:min-h-9 [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden="true" className="size-3.5 transition-transform duration-150 group-open:rotate-90" />
        观众评论 {comments.length} 条
      </summary>
      <ul className="m-0 grid list-none gap-2 p-0 pb-1 pt-1">
        {top.map((comment) => (
          <li key={comment.id}>
            <blockquote className="m-0 border-l-2 border-border pl-3 text-[13px] leading-5 text-ink-soft">
              {comment.content}
              <footer className="mt-1 text-xs text-ink-muted">{comment.author} · {comment.likes} 赞</footer>
            </blockquote>
          </li>
        ))}
      </ul>
      {comments.length > top.length ? <p className="m-0 mt-2 text-xs text-ink-muted">按点赞排序，只显示前 {top.length} 条；其余在视频详情里。</p> : null}
    </details>
  );
}

function Row({ row, onOpenVideo, onChanged }: { row: MetricsRow; onOpenVideo: PanelProps["onOpenVideo"]; onChanged: () => Promise<void> }) {
  const { performance, video } = row.view;
  // 没快照的行不另开一套排版：三个指标照样渲染成“—”，只有这句话变
  const freshness = row.snapshots ? `更新过 ${row.snapshots} 次 · 最近 ${formatDate(row.capturedAt)}` : "还没有数据";
  return (
    <li className="grid gap-2.5 py-4">
      <div className="flex items-start justify-between gap-3">
        <button className="min-w-0 rounded-md text-left text-sm font-semibold text-ink outline-none hover:underline focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2" onClick={() => onOpenVideo(video.id, "publish")} type="button">
          {video.title}
        </button>
        <SyncAction onChanged={onChanged} row={row} />
      </div>
      <p className="m-0 text-xs text-ink-muted">发在 {row.tasks.length} 个账号 · {freshness}</p>
      <dl className="m-0 grid grid-cols-3 gap-3">
        <Metric label="最佳播放" value={formatNumber(performance.best_views)} />
        <Metric label="最佳订单" value={formatNumber(performance.best_orders)} />
        <Metric label="最佳成交额" value={formatMoney(performance.best_revenue)} />
      </dl>
      {row.comments.length ? <Comments comments={row.comments} /> : null}
    </li>
  );
}

export function MetricsPanel({ workspace, onChanged, onOpenVideo }: PanelProps) {
  const rows = useMemo(() => buildRows(workspace), [workspace]);
  if (!rows.length) {
    return <EmptyState description="视频发出去以后，播放量、订单和评论会自动出现在这里。" icon={LineChart} title="还没有数据" />;
  }
  const withData = rows.filter((row) => row.snapshots > 0).length;
  return (
    <div className="grid gap-4">
      {/* 演示工作区的数字是样例生成的，不能让它冒充真实回流 */}
      {workspace.mode === "demo" ? <InlineAlert title="示例数据" tone="info">这些播放、订单和成交额是示例数字，不是真实平台数据。</InlineAlert> : null}
      <p className="m-0 text-[13px] text-ink-muted">{rows.length} 条已发布 · {withData} 条有数据 · 按最佳播放排序</p>
      <ul className="m-0 grid list-none divide-y divide-border border-y border-border p-0">
        {rows.map((row) => <Row key={row.view.video.id} onChanged={onChanged} onOpenVideo={onOpenVideo} row={row} />)}
      </ul>
    </div>
  );
}
