import { Badge, Button, EmptyState } from "@fifty/workbench-ui";
import { GitBranch } from "lucide-react";
import { useMemo, useState } from "react";
import { LineageDialog } from "../../dialogs/lineage-dialog";
import type { VideoDetailTab, VideoView, Workspace } from "../../domain";
import type { PanelProps } from "./types";

// ============================================================
// 提炼 / 再做一版面板（design-v7-canvas.md：闭环最值钱的一环）
//
// 「提炼」和「再做一版」两个节点共用这一个面板：提炼结论就是再做一版的入参，
// 拆成两屏只会让人在两个门之间来回找答案。
// 一行只有两件事：这条赢在哪（后端 performance_brief 原文，不改写、不加戏）、
// 一个动作（再做一版）。口播正文一律去视频详情看，这里不出现。
// ============================================================

/** 「待观察」是内部说法，画面上说人话（v7 术语表） */
const PERFORMANCE_LABEL: Record<string, string> = { 待观察: "已发布，还没有数据" };

interface SpawnRow {
  view: VideoView;
  /** 已经带着它开过下一批的子视频条数 */
  children: number;
}

// 赢家在前：先看成交，再看播放——真实转化只由回流数据授予（v5 质量诚实条款）
function byPerformance(a: SpawnRow, b: SpawnRow): number {
  const orders = (b.view.performance.best_orders ?? -1) - (a.view.performance.best_orders ?? -1);
  return orders || (b.view.performance.best_views ?? -1) - (a.view.performance.best_views ?? -1);
}

/** 有提炼结论的视频 + 各自已裂变的子视频数；没有结论的不进这个面板 */
function distilledRows(workspace: Workspace): SpawnRow[] {
  const children = new Map<string, number>();
  for (const view of workspace.videos) {
    const parent = view.video.parent_video_id;
    if (parent) children.set(parent, (children.get(parent) ?? 0) + 1);
  }
  return workspace.videos
    .filter((view) => view.performance_brief !== null)
    .map((view) => ({ view, children: children.get(view.video.id) ?? 0 }))
    .sort(byPerformance);
}

interface SpawnItemProps {
  row: SpawnRow;
  /** 排最前、还没再做过的那条：同屏唯一的 primary（v6 组件规格） */
  recommended: boolean;
  onOpenVideo: (videoId: string, tab?: VideoDetailTab) => void;
  onSpawn: (videoId: string) => void;
}

function SpawnItem({ row, recommended, onOpenVideo, onSpawn }: SpawnItemProps) {
  const { view, children } = row;
  const label = PERFORMANCE_LABEL[view.performance.label] ?? view.performance.label;
  return <li className="grid gap-2 py-4 first:pt-0 last:pb-0">
    <div className="flex items-start justify-between gap-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <button
          aria-label={`看这一条：${view.video.title}`}
          className="min-h-11 max-w-full cursor-pointer truncate rounded-sm text-left text-sm font-semibold leading-5 text-ink outline-none transition-colors hover:text-brand focus-visible:ring-2 focus-visible:ring-focus sm:min-h-6"
          onClick={() => onOpenVideo(view.video.id, "publish")}
          title={view.video.title}
          type="button"
        >
          <span>{view.video.title}</span>
        </button>
        <Badge tone={view.performance.tone}>{label}</Badge>
      </div>
      <Button className="min-h-11 shrink-0 sm:min-h-9" onClick={() => onSpawn(view.video.id)} size="sm" variant={recommended ? "primary" : "secondary"}>再做一版</Button>
    </div>
    <p className="m-0 break-words text-sm leading-6 text-ink-soft">{view.performance_brief}</p>
    {children ? <p className="m-0 text-[13px] leading-5 text-ink-muted">照着它又做了新版 · {children} 条</p> : null}
  </li>;
}

export function SpawnPanel({ workspace, onChanged, onOpenVideo, onClose }: PanelProps) {
  const rows = useMemo(() => distilledRows(workspace), [workspace]);
  const [spawnId, setSpawnId] = useState<string>();
  const spawning = rows.find((row) => row.view.video.id === spawnId)?.view;
  const recommendedId = rows.find((row) => !row.children)?.view.video.id;

  // 空态诚实：结论是回流数据换来的，不是这里缺了个按钮
  if (!rows.length) return <EmptyState
    action={{ label: "回到流程图看发布进度", onClick: onClose }}
    description="视频发出去、平台把数据传回来之后，这里会自动列出哪条视频赢了、为什么赢。"
    icon={GitBranch}
    title="还没有拿到数据的视频"
  />;

  return <div className="grid gap-3">
    <p className="m-0 text-[13px] leading-5 text-ink-muted">{rows.length} 条已经拿到数据 · 按成交和播放排序，赢的排在前面。</p>
    <ul className="m-0 grid list-none divide-y divide-border p-0">
      {rows.map((row) => <SpawnItem
        key={row.view.video.id}
        onOpenVideo={onOpenVideo}
        onSpawn={setSpawnId}
        recommended={row.view.video.id === recommendedId}
        row={row}
      />)}
    </ul>
    {spawning ? <LineageDialog
      onCompleted={onChanged}
      onOpenChange={(open) => { if (!open) setSpawnId(undefined); }}
      open
      performanceBrief={spawning.performance_brief}
      video={spawning.video}
    /> : null}
  </div>;
}
