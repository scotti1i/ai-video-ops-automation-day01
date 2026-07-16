import { cn } from "@fifty/workbench-ui";
import { Handle, type Node, type NodeProps } from "@xyflow/react";
import { Activity, Clapperboard, GitFork, ListChecks, RotateCcw, Send, Sparkles, TriangleAlert, Trophy, Wand2, type LucideIcon } from "lucide-react";
import { memo, type CSSProperties } from "react";
import { NODE_HEIGHT, NODE_WIDTH, type PipelineNodeId, type PipelineNodeModel, type PipelineStatus } from "./pipeline-model";

// ============================================================
// 阶段节点（design-v8-canvas-feel.md：对标 liblib/ComfyUI 的节点卡片长相）
//
// 卡片解剖：头部（阶段图标色块 + 名字 + 计数徽章）· 状态行（圆点 + 文字）· 左右端口圆点。
// 端口是视觉锚点、非交互（拓扑锁死）——连线从它出入，但拖不出新线。
// 配色是我们自己的墨蓝纸白，不碰 liblib 的皮；借的是结构与手感。
// 画布上永远不出现口播正文。
// ============================================================

const STAGE_ICON: Record<PipelineNodeId, LucideIcon> = {
  brief: Sparkles,
  generate: Wand2,
  pick: ListChecks,
  media: Clapperboard,
  publish: Send,
  metrics: Activity,
  distill: Trophy,
  spawn: GitFork,
};

/** 展开卡片的头部要echo节点身份，共用同一套图标 */
export function stageIcon(id: PipelineNodeId): LucideIcon {
  return STAGE_ICON[id];
}

// 三种状态各一套色：卡片描边 / 图标色块 / 状态圆点 / 徽章
const FRAME: Record<PipelineStatus, string> = {
  attention: "border-brand",
  auto: "border-border",
  blocked: "border-danger",
};
const CHIP: Record<PipelineStatus, string> = {
  attention: "bg-brand-soft text-brand",
  auto: "bg-surface-muted text-ink-muted",
  blocked: "bg-danger-soft text-danger",
};
const DOT: Record<PipelineStatus, string> = {
  attention: "bg-brand",
  auto: "bg-ink-muted/50",
  blocked: "bg-danger",
};
const STATUS_TEXT: Record<PipelineStatus, string> = {
  attention: "text-brand",
  auto: "text-ink-muted",
  blocked: "text-danger",
};
const BADGE: Record<PipelineStatus, string> = {
  attention: "bg-brand text-white",
  auto: "bg-surface-muted text-ink-soft",
  blocked: "bg-danger text-white",
};
// 端口圆点：随状态染色，白心 + 描边（liblib/comfy 的招牌锚点）
const PORT: Record<PipelineStatus, string> = {
  attention: "var(--brand)",
  auto: "var(--border-strong)",
  blocked: "var(--danger)",
};

interface NodeButtonProps {
  model: PipelineNodeModel;
  onOpen: (id: PipelineNodeId) => void;
  className?: string;
  style?: CSSProperties;
}

/** 画布节点与手机列表项共用同一张卡片——同样的解剖、同样的一个动作 */
export function PipelineNodeButton({ model, onOpen, className, style }: NodeButtonProps) {
  const Icon = STAGE_ICON[model.id];
  return <button
    aria-label={`${model.label}：${model.statusLabel}，${model.countLabel}`}
    className={cn(
      "flex cursor-pointer flex-col gap-2 rounded-[12px] border bg-surface px-3.5 py-3 text-left shadow-sm outline-none transition-[transform,box-shadow,border-color] duration-150 ease-out",
      "hover:-translate-y-0.5 hover:shadow-[var(--shadow-overlay)] focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2",
      FRAME[model.status],
      className,
    )}
    data-pipeline-node={model.id}
    onClick={() => onOpen(model.id)}
    style={style}
    title={model.description}
    type="button"
  >
    <span className="flex min-w-0 items-center gap-2.5">
      <span className={cn("grid size-7 shrink-0 place-items-center rounded-[8px] transition-colors", CHIP[model.status])}>
        <Icon aria-hidden="true" className="size-4" />
      </span>
      <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">{model.label}</span>
      {/* brief 是入口/设置节点，不是排队阶段——不显示计数（右上角一个 3 无意义） */}
      {model.count > 0 && model.id !== "brief" ? <span className={cn("grid h-6 min-w-6 shrink-0 place-items-center rounded-full px-1.5 text-[13px] font-semibold tabular-nums", BADGE[model.status])}>{model.count}</span> : null}
    </span>
    {/* 第二行放真内容（头条脚本/最高播放/赢家），不放"自动/等你"标签——状态只靠圆点颜色。
        空阶段没有内容时才退回状态词。 */}
    <span aria-hidden="true" className="flex items-center gap-1.5 pl-0.5 text-[13px]">
      {model.status === "blocked"
        ? <TriangleAlert className={cn("size-3.5 shrink-0", STATUS_TEXT.blocked)} />
        : <span className={cn("size-2 shrink-0 rounded-full", DOT[model.status])} />}
      <span className={cn("min-w-0 flex-1 truncate", model.detail ? "text-ink-soft" : cn("font-medium", STATUS_TEXT[model.status]))}>
        {model.detail || (model.count > 0 ? model.countLabel : model.statusLabel)}
      </span>
    </span>
  </button>;
}

export interface PipelineNodeData extends Record<string, unknown> {
  model: PipelineNodeModel;
  onOpen: (id: PipelineNodeId) => void;
}

export type PipelineFlowNode = Node<PipelineNodeData, "stage">;

const NODE_STYLE: CSSProperties = { width: NODE_WIDTH, height: NODE_HEIGHT };

/** 端口圆点：~9px、白心描边、随状态染色。非交互（cursor default），只是连线的视觉锚点。 */
function portStyle(status: PipelineStatus): CSSProperties {
  return { width: 9, height: 9, borderRadius: 9999, background: "var(--surface)", border: `1.5px solid ${PORT[status]}`, cursor: "default" };
}

/** hover 悬浮速览（对标 n8n 的 NodeToolbar）：节点上方冒出一句"这一步在做什么" + 打开提示 */
function NodePeek({ model }: { model: PipelineNodeModel }) {
  return <div
    aria-hidden="true"
    className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-[190px] -translate-x-1/2 translate-y-1 rounded-[10px] bg-ink px-3 py-2 text-left text-[12px] leading-4 text-surface opacity-0 shadow-[var(--shadow-overlay)] transition-[opacity,transform] duration-150 ease-out group-hover/node:translate-y-0 group-hover/node:opacity-100"
  >
    <span className="block leading-4 opacity-85">{model.description}</span>
    <span className="mt-1 block font-semibold">打开 →</span>
  </div>;
}

// memo 是硬要求：xyflow 每次视口变化都会重渲染节点，不 memo 会发抖
export const PipelineStageNode = memo(function PipelineStageNode({ data }: NodeProps<PipelineFlowNode>) {
  const { model, onOpen } = data;
  return <div className="group/node relative" style={NODE_STYLE}>
    <Handle isConnectable={false} position={model.targetPosition} style={portStyle(model.status)} type="target" />
    <PipelineNodeButton className="h-full w-full" model={model} onOpen={onOpen} />
    <Handle isConnectable={false} position={model.sourcePosition} style={portStyle(model.status)} type="source" />
    <NodePeek model={model} />
  </div>;
});

/** 手机 390：画布退化为纵向阶段列表——同样的卡片、同样的顺序、同样的一个动作 */
export function PipelineNodeList({ nodes, onOpen }: { nodes: PipelineNodeModel[]; onOpen: (id: PipelineNodeId) => void }) {
  return <ol className="m-0 grid list-none gap-2.5 p-0">
    {nodes.map((model, index) => <li className="relative" key={model.id}>
      {index > 0 ? <span aria-hidden="true" className="absolute -top-2.5 left-6 h-2.5 w-px bg-border-strong" /> : null}
      <PipelineNodeButton className="w-full" model={model} onOpen={onOpen} />
    </li>)}
    <li className="flex items-center gap-1.5 px-3.5 pt-1.5 text-[13px] text-ink-muted">
      <RotateCcw aria-hidden="true" className="size-3.5 shrink-0" />「再做一版」会照着赢的那条，回到「这批想做什么」重新开一轮
    </li>
  </ol>;
}
