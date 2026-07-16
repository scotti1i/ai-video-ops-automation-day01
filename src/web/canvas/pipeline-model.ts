import { Position } from "@xyflow/react";
import type { Batch, ScriptCandidate, VideoStage, VideoView, Workspace } from "../domain";
import { formatNumber } from "../format";
import type { PanelKey } from "./panels/types";

// ============================================================
// 流水线模型（design-v7-canvas.md：一屏 = 一个环）
//
// 形状固定：八个阶段，最后一个连回起点。节点不可增删、连线不可重连——
// 我们不是在做 n8n，是在用画布表达一个已知的流程。
// 坐标手写：八个节点不值得引自动布局。上排五个、下排三个，边全是直线。
// ============================================================

export type PipelineNodeId = "brief" | "generate" | "pick" | "media" | "publish" | "metrics" | "distill" | "spawn";

/** 只有三种，不许更多：等你（品牌深色描边）· 自动（灰）· 出问题（红） */
export type PipelineStatus = "attention" | "auto" | "blocked";

export const NODE_WIDTH = 208;
export const NODE_HEIGHT = 82;

interface PipelineShapeNode {
  id: PipelineNodeId;
  /** 人话名字：「选稿」不是「候选评审」 */
  label: string;
  /** 抽屉副标题，也是节点的无障碍描述 */
  description: string;
  panel: PanelKey;
  /** manual = 该阶段要人拍板（有条目就「等你」）；auto = 系统推进 */
  kind: "manual" | "auto";
  /** 徽章单位：进 aria 文案；节点没有真内容可显示时，副行退回「N 条…」也会用到 */
  unit: string;
  position: { x: number; y: number };
  targetPosition: Position;
  sourcePosition: Position;
}

const COLUMN = [0, 272, 544, 816, 1088];
const TOP = 0;
const BOTTOM = 260;

// 数组顺序 = 流程顺序 = 节点 DOM 顺序 = Tab 顺序，三者靠这一处对齐。
const PIPELINE_SHAPE_NODES: PipelineShapeNode[] = [
  {
    id: "brief",
    label: "这批想做什么",
    description: "填商品、参考视频、要做几条、风格要求——这批视频照着这些来做。",
    panel: "brief",
    kind: "auto",
    unit: "批视频在做",
    position: { x: COLUMN[0], y: TOP },
    targetPosition: Position.Bottom,
    sourcePosition: Position.Right,
  },
  {
    id: "generate",
    label: "生成脚本",
    description: "还没写脚本的视频，在这里一键生成。",
    panel: "generate",
    kind: "auto",
    unit: "条脚本要写",
    position: { x: COLUMN[1], y: TOP },
    targetPosition: Position.Left,
    sourcePosition: Position.Right,
  },
  {
    id: "pick",
    label: "选稿",
    description: "对比 AI 写好的脚本，读全文、改写，挑出要拍的那几条。",
    panel: "pick",
    kind: "manual",
    unit: "条脚本要挑",
    position: { x: COLUMN[2], y: TOP },
    targetPosition: Position.Left,
    sourcePosition: Position.Right,
  },
  {
    id: "media",
    label: "成片",
    description: "一条条上传做好的视频，看竖屏预览。",
    panel: "media",
    kind: "manual",
    unit: "条要拍",
    position: { x: COLUMN[3], y: TOP },
    targetPosition: Position.Left,
    sourcePosition: Position.Right,
  },
  {
    id: "publish",
    label: "发布",
    description: "选账号、定发布时间，看发布记录，处理没发出去的。",
    panel: "publish",
    kind: "auto",
    unit: "条在发布",
    position: { x: COLUMN[4], y: TOP },
    targetPosition: Position.Left,
    sourcePosition: Position.Bottom,
  },
  {
    id: "metrics",
    label: "数据",
    description: "每条视频发出去后的播放、点赞、评论。",
    panel: "metrics",
    kind: "auto",
    unit: "条有数据",
    position: { x: COLUMN[4], y: BOTTOM },
    targetPosition: Position.Top,
    sourcePosition: Position.Left,
  },
  {
    id: "distill",
    label: "谁赢了",
    description: "这一轮哪条视频赢了、为什么赢。",
    panel: "spawn",
    kind: "auto",
    unit: "条有结论",
    position: { x: COLUMN[2], y: BOTTOM },
    targetPosition: Position.Right,
    sourcePosition: Position.Left,
  },
  {
    id: "spawn",
    label: "再做一版",
    description: "照着赢的那条，再做一批新的。",
    panel: "spawn",
    kind: "manual",
    unit: "条可再做一版",
    position: { x: COLUMN[0], y: BOTTOM },
    targetPosition: Position.Right,
    sourcePosition: Position.Top,
  },
];

export const PIPELINE_SHAPE: readonly PipelineShapeNode[] = PIPELINE_SHAPE_NODES;

export interface PipelineEdgeModel {
  id: string;
  source: PipelineNodeId;
  target: PipelineNodeId;
  /** 闭环那条回边（再做一版 → 起点）：只有它流动，表示「环在转」 */
  loop: boolean;
}

// 顺序即流程，最后一个连回第一个——边不单独维护，从顺序推出来。
export const PIPELINE_EDGES: PipelineEdgeModel[] = PIPELINE_SHAPE_NODES.map((node, index) => {
  const next = PIPELINE_SHAPE_NODES[(index + 1) % PIPELINE_SHAPE_NODES.length];
  return { id: `${node.id}-${next.id}`, source: node.id, target: next.id, loop: index === PIPELINE_SHAPE_NODES.length - 1 };
});

export type PipelineNodeModel = PipelineShapeNode & {
  status: PipelineStatus;
  /** 「等你」「自动」「出问题」——状态不能只靠颜色表达 */
  statusLabel: string;
  count: number;
  /** aria 用的完整计数文案 */
  countLabel: string;
  /** 节点里的真内容：这一步最相关的一条（脚本名/视频名/最高播放/赢家），不是标签 */
  detail: string;
};

// ============================================================
// 状态推导：从 workspace 客户端聚合，不加接口
// ============================================================

const BLOCKED_STAGES: VideoStage[] = ["publish_failed", "needs_reconciliation"];
const PUBLISH_STAGES: VideoStage[] = ["ready_to_publish", "scheduled", "publishing", ...BLOCKED_STAGES];

const STATUS_LABEL: Record<PipelineStatus, string> = { attention: "等你", auto: "这步不用管", blocked: "出问题" };

function countStage(videos: VideoView[], stages: VideoStage[]): number {
  return videos.filter((view) => stages.includes(view.stage.stage)).length;
}

/** 待选候选：批次里还没被选进成片的（后端可能不带 candidates 字段） */
function pending(batch: Batch): ScriptCandidate[] {
  return (batch.candidates ?? []).filter((candidate) => !candidate.selected_video_id);
}

function pipelineCounts(workspace: Workspace): Record<PipelineNodeId, number> {
  const videos = workspace.videos;
  const parents = new Set(videos.map((view) => view.video.parent_video_id).filter((id): id is string => Boolean(id)));
  const unfinished = new Set(videos.filter((view) => view.stage.stage !== "published").map((view) => view.video.batch_id));
  const distilled = videos.filter((view) => view.performance_brief !== null);
  return {
    // 活跃批次：还有待选稿，或还有视频没发出去。全部发完就归零，不会随时间涨。
    brief: workspace.batches.filter((batch) => pending(batch).length > 0 || unfinished.has(batch.id)).length,
    // 待生成：缺脚本的视频 + 只有依据还没出候选的批次
    generate: countStage(videos, ["needs_script"]) + workspace.batches.filter((batch) => !pending(batch).length && !batch.video_ids.length).length,
    pick: workspace.batches.reduce((total, batch) => total + pending(batch).length, 0),
    media: countStage(videos, ["needs_media"]),
    publish: countStage(videos, PUBLISH_STAGES),
    metrics: videos.filter((view) => view.video.publications.some((publication) => publication.metrics.length > 0)).length,
    distill: distilled.length,
    // 可再做一版：有提炼结论、且还没带着基因开过下一批
    spawn: distilled.filter((view) => !parents.has(view.video.id)).length,
  };
}

/** 播放最高的一条（有指标的）——数据回流/提炼节点直接展示真数字 */
function topByViews(videos: VideoView[]): VideoView | undefined {
  return videos
    .filter((view) => view.performance.best_views !== null)
    .sort((a, b) => (b.performance.best_views ?? 0) - (a.performance.best_views ?? 0))[0];
}

/**
 * 节点里放真内容，不放标签。TapNow 的节点装的是那张图/那段词，我们装这一步最相关的一条：
 * 头条脚本名、待拍视频名、最高播放、赢家标题。空阶段返回空串，节点就只显示计数。
 */
function nodeDetail(workspace: Workspace, id: PipelineNodeId): string {
  const videos = workspace.videos;
  switch (id) {
    case "brief": {
      // 入口/设置节点：显示当前在跑的一批，没有就提示开始——不显示计数（见 nodes.tsx 隐藏徽章）
      const active = workspace.batches.filter((batch) => pending(batch).length > 0 || batch.video_ids.length > 0)[0];
      return active ? active.name : "点开设置这批视频";
    }
    case "generate":
      // 下一条待生成脚本的视频（队列顺位），不是"自动"
      return videos.find((view) => view.stage.stage === "needs_script")?.video.title ?? "";
    case "pick": {
      // 19 条里挑一条冒充全部是误导——给可拍/差证据的分布（聚合、准确）
      const candidates = workspace.batches.flatMap((batch) => pending(batch));
      if (!candidates.length) return "";
      const ready = candidates.filter((candidate) => candidate.quality?.status === "ready_to_test").length;
      return `${ready} 条能拍 · ${candidates.length - ready} 条要再改`;
    }
    case "media":
      return videos.find((view) => view.stage.stage === "needs_media")?.video.title ?? "";
    case "publish": {
      const failing = videos.find((view) => BLOCKED_STAGES.includes(view.stage.stage));
      if (failing) return failing.video.title;
      return videos.find((view) => PUBLISH_STAGES.includes(view.stage.stage))?.video.title ?? "";
    }
    case "metrics": {
      const top = topByViews(videos);
      return top ? `${formatNumber(top.performance.best_views)} 播放 · ${top.video.title}` : "";
    }
    case "distill": {
      const top = topByViews(videos.filter((view) => view.performance_brief !== null));
      return top ? `${formatNumber(top.performance.best_views)} 播放 · ${top.video.title}` : "";
    }
    case "spawn": {
      const parents = new Set(videos.map((view) => view.video.parent_video_id).filter(Boolean));
      const winner = topByViews(videos.filter((view) => view.performance_brief !== null && !parents.has(view.video.id)));
      return winner?.video.title ?? "";
    }
    default:
      return "";
  }
}

/** 从 workspace 推导八个节点的计数、状态与真内容；12 条和 500 条视频只有数字与内容不同 */
export function buildPipelineNodes(workspace: Workspace): PipelineNodeModel[] {
  const counts = pipelineCounts(workspace);
  // 发布失败、需对账都发生在「发布」阶段，出问题只挂在它身上。
  // 红徽章只数出问题的那几条：顺利在发的此刻不用你知道，红色的 4 会读成「4 个问题」。
  const failing = countStage(workspace.videos, BLOCKED_STAGES);
  return PIPELINE_SHAPE_NODES.map((shape) => {
    const blocked = shape.id === "publish" && failing > 0;
    const count = blocked ? failing : counts[shape.id];
    const status: PipelineStatus = blocked ? "blocked" : shape.kind === "manual" && count > 0 ? "attention" : "auto";
    const unit = blocked ? "条出问题" : shape.unit;
    return {
      ...shape,
      status,
      statusLabel: STATUS_LABEL[status],
      count,
      countLabel: count ? `${count} ${unit}` : "暂无待办",
      detail: nodeDetail(workspace, shape.id),
    };
  });
}
