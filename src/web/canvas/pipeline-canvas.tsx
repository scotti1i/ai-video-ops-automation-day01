import { Button, IconButton } from "@fifty/workbench-ui";
import { Background, BackgroundVariant, MarkerType, MiniMap, Panel, ReactFlow, useNodesState, useReactFlow, type Edge, type FitViewOptions, type NodeChange } from "@xyflow/react";
import { Maximize2, Minus, Plus, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { VideoDetailTab, Workspace } from "../domain";
import { PipelineNodeList, PipelineStageNode, type PipelineFlowNode } from "./nodes";
import { PanelHost } from "./panel-host";
import { PIPELINE_EDGES, buildPipelineNodes, type PipelineNodeId, type PipelineNodeModel } from "./pipeline-model";

// ============================================================
// 画布外壳（design-v8-canvas-feel.md：手感对标 liblib/ComfyUI，拓扑锁死）
//
// 从静态图升级成活画布：可平移、可缩放、点阵背景跟着动、有小地图和缩放控件、
// 节点可拖并记住位置。但拓扑锁死——加不了节点、拖不出新线、右键无加节点菜单。
// 我们抄的是它的手感，不是它的可编辑性。
// ============================================================

const NODE_TYPES = { stage: PipelineStageNode };

// 进入即把整个环铺进视口；之后用户自由平移缩放，不再强制归位。
const FIT_VIEW: FitViewOptions = { padding: 0.18, maxZoom: 1, minZoom: 0.4 };
const MIN_ZOOM = 0.4;
const MAX_ZOOM = 1.5;

const EDGE_COLOR = "var(--border-strong)";
const EDGE_MARKER = { type: MarkerType.ArrowClosed, width: 15, height: 15, color: EDGE_COLOR };

// 边是静态的：形状不随数据变。贝塞尔粗线 + 箭头；只有闭环那条回边流动，表示「环在转」。
const FLOW_EDGES: Edge[] = PIPELINE_EDGES.map((edge) => ({
  id: edge.id,
  source: edge.source,
  target: edge.target,
  type: "default",
  animated: edge.loop,
  markerEnd: EDGE_MARKER,
  style: { stroke: EDGE_COLOR, strokeWidth: 2 },
  focusable: false,
  selectable: false,
  deletable: false,
  reconnectable: false,
}));

const NARROW = "(max-width: 639px)";

function narrowQuery(): MediaQueryList | null {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(NARROW) : null;
}

/** 手机与桌面共用同一份节点模型，只换渲染器——不做两套逻辑 */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => narrowQuery()?.matches ?? false);
  useEffect(() => {
    const query = narrowQuery();
    if (!query) return undefined;
    const sync = () => setNarrow(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);
  return narrow;
}

// ------------------------------------------------------------
// 布局持久化：节点可拖，位置按工作区存本地。只动坐标，不动拓扑。
// ------------------------------------------------------------
type Layout = Record<string, { x: number; y: number }>;

function layoutKey(workspaceId: string): string {
  return `pipeline-layout:v1:${workspaceId}`;
}

function loadLayout(workspaceId: string): Layout {
  try {
    const raw = window.localStorage.getItem(layoutKey(workspaceId));
    return raw ? (JSON.parse(raw) as Layout) : {};
  } catch {
    return {};
  }
}

function saveLayout(workspaceId: string, nodes: PipelineFlowNode[]): void {
  try {
    const layout: Layout = {};
    for (const node of nodes) layout[node.id] = node.position;
    window.localStorage.setItem(layoutKey(workspaceId), JSON.stringify(layout));
  } catch {
    // 本地存储不可用（隐私模式等）就不记忆位置，不影响使用
  }
}

function toFlowNode(model: PipelineNodeModel, onOpen: (id: PipelineNodeId) => void, layout: Layout): PipelineFlowNode {
  return {
    id: model.id,
    type: "stage",
    position: layout[model.id] ?? model.position,
    data: { model, onOpen },
    draggable: true,
    selectable: false,
    connectable: false,
    deletable: false,
    // 焦点由节点内的 <button> 自己拿，别让 xyflow 再套一层 tabIndex（会变成两个 Tab 站）
    focusable: false,
  };
}

function miniColor(status: PipelineNodeModel["status"]): string {
  return status === "attention" ? "var(--brand)" : status === "blocked" ? "var(--danger)" : "var(--border-strong)";
}

/** 左下缩放控件 + 恢复默认布局：自绘，比 xyflow 默认 Controls 克制、样式跟得上 */
function CanvasControls({ onResetLayout }: { onResetLayout: () => void }) {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  return <div className="flex items-center gap-1 rounded-[10px] border border-border bg-surface p-1 shadow-sm">
    <IconButton aria-label="放大" className="size-8" onClick={() => void zoomIn()} variant="quiet"><Plus className="size-4" /></IconButton>
    <IconButton aria-label="缩小" className="size-8" onClick={() => void zoomOut()} variant="quiet"><Minus className="size-4" /></IconButton>
    <IconButton aria-label="适配全部" className="size-8" onClick={() => void fitView(FIT_VIEW)} variant="quiet"><Maximize2 className="size-4" /></IconButton>
    <span aria-hidden="true" className="mx-0.5 h-4 w-px bg-border" />
    <IconButton aria-label="恢复默认布局" className="size-8" onClick={onResetLayout} variant="quiet"><RotateCcw className="size-4" /></IconButton>
  </div>;
}

function FlowCanvas({ workspaceId, models, onOpen }: { workspaceId: string; models: PipelineNodeModel[]; onOpen: (id: PipelineNodeId) => void }) {
  const initial = useMemo(() => {
    const layout = loadLayout(workspaceId);
    return models.map((model) => toFlowNode(model, onOpen, layout));
    // 只在工作区切换时重建初值；后续 models 变化走下面的 effect 合并
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);
  const [nodes, setNodes, onNodesChange] = useNodesState<PipelineFlowNode>(initial);

  // 数据每 2.5s 轮询刷新：只更新节点的计数/状态，保留用户拖过的位置。
  useEffect(() => {
    setNodes((prev) => models.map((model) => {
      const existing = prev.find((node) => node.id === model.id);
      return { ...toFlowNode(model, onOpen, {}), position: existing?.position ?? model.position };
    }));
  }, [models, onOpen, setNodes]);

  const handleChange = useCallback((changes: NodeChange<PipelineFlowNode>[]) => {
    onNodesChange(changes);
    if (changes.some((change) => change.type === "position" && change.dragging === false)) {
      setNodes((current) => { saveLayout(workspaceId, current); return current; });
    }
  }, [onNodesChange, setNodes, workspaceId]);

  const resetLayout = useCallback(() => {
    try { window.localStorage.removeItem(layoutKey(workspaceId)); } catch { /* ignore */ }
    setNodes(models.map((model) => toFlowNode(model, onOpen, {})));
  }, [models, onOpen, setNodes, workspaceId]);

  // 65px = 顶栏 64 + 1px 下边框
  return <div className="h-[calc(100svh-65px)] w-full">
    <ReactFlow
      aria-label="视频流水线"
      deleteKeyCode={null}
      edges={FLOW_EDGES}
      edgesFocusable={false}
      edgesReconnectable={false}
      elementsSelectable={false}
      fitView
      fitViewOptions={FIT_VIEW}
      maxZoom={MAX_ZOOM}
      minZoom={MIN_ZOOM}
      nodeTypes={NODE_TYPES}
      nodes={nodes}
      nodesConnectable={false}
      nodesFocusable={false}
      onNodesChange={handleChange}
      panOnDrag
      proOptions={{ hideAttribution: false }}
      selectNodesOnDrag={false}
      zoomOnDoubleClick={false}
    >
      <Background color="var(--border-strong)" gap={20} size={1} variant={BackgroundVariant.Dots} />
      <Panel position="bottom-left"><CanvasControls onResetLayout={resetLayout} /></Panel>
      <MiniMap
        ariaLabel="流水线缩略图"
        className="!bottom-4 !right-4 !m-0 overflow-hidden rounded-[10px] border border-border !bg-surface shadow-sm"
        maskColor="var(--surface-muted)"
        nodeColor={(node) => miniColor((node.data as PipelineFlowNode["data"]).model.status)}
        nodeStrokeWidth={0}
        pannable
        style={{ width: 168, height: 108 }}
        zoomable
      />
    </ReactFlow>
  </div>;
}

export interface PipelineCanvasProps {
  workspace: Workspace;
  onChanged: () => Promise<void>;
  onOpenVideo: (videoId: string, tab?: VideoDetailTab) => void;
}

/**
 * 首跑引导：新工作区里八个节点全是 0，画布再自解释也没有入口。
 * 不遮画布——空环本身就是"这个产品在干什么"的最好说明，只在它上面压一句话和一个动作。
 */
function FirstRun({ onStart }: { onStart: () => void }) {
  return <div className="pointer-events-none absolute inset-x-0 top-6 z-10 flex justify-center px-4">
    <div className="pointer-events-auto max-w-lg rounded-[14px] border border-border bg-surface px-5 py-4 text-center shadow-[var(--shadow-overlay)]">
      <p className="m-0 text-sm leading-6 text-ink">
        这是一条闭环：说清这批想做什么 → AI 给一批脚本 → 你挑 → 拍成片 → 发出去 → 数据回来 → 赢的那条再做一版。
      </p>
      <p className="mb-0 mt-1 text-[13px] leading-5 text-ink-muted">现在还是空的，从第一批开始。</p>
      <Button className="mt-3" onClick={onStart} size="sm">开始第一批视频</Button>
    </div>
  </div>;
}

export function PipelineCanvas({ workspace, onChanged, onOpenVideo }: PipelineCanvasProps) {
  const [openNodeId, setOpenNodeId] = useState<PipelineNodeId>();
  const onOpen = useCallback((id: PipelineNodeId) => setOpenNodeId(id), []);
  const close = useCallback(() => setOpenNodeId(undefined), []);
  const models = useMemo(() => buildPipelineNodes(workspace), [workspace]);
  const narrow = useNarrow();
  const firstRun = !workspace.videos.length && !workspace.batches.length;
  return <>
    <div className="relative">
      {firstRun ? <FirstRun onStart={() => onOpen("brief")} /> : null}
      {narrow
        ? <div className="p-4"><PipelineNodeList nodes={models} onOpen={onOpen} /></div>
        : <FlowCanvas models={models} onOpen={onOpen} workspaceId={workspace.id} />}
    </div>
    <PanelHost nodeId={openNodeId} onChanged={onChanged} onClose={close} onOpenVideo={onOpenVideo} workspace={workspace} />
  </>;
}
