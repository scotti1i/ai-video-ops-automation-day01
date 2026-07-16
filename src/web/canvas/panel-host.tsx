import { useEffect, useRef, useState, type ComponentType } from "react";
import type { VideoDetailTab, Workspace } from "../domain";
import { NodePanel } from "./node-panel";
import { stageIcon } from "./nodes";
import { BriefPanel } from "./panels/brief-panel";
import { GeneratePanel } from "./panels/generate-panel";
import { MediaPanel } from "./panels/media-panel";
import { MetricsPanel } from "./panels/metrics-panel";
import { PickPanel } from "./panels/pick-panel";
import { PublishPanel } from "./panels/publish-panel";
import { SpawnPanel } from "./panels/spawn-panel";
import type { PanelKey, PanelProps } from "./panels/types";
import { PIPELINE_SHAPE, type PipelineNodeId } from "./pipeline-model";

// ============================================================
// 面板宿主：判断在面板里，不在画布上。
// 抽屉标题 / 副标题来自被点的节点（同一个面板从「提炼」和「再做一版」
// 两个门进来，标题告诉你从哪个门进的）。
//
// 节点 → 面板只有这一张表；八个节点、七个面板（提炼与再做一版共用 spawn）。
// ============================================================
const PANELS: Record<PanelKey, ComponentType<PanelProps>> = {
  brief: BriefPanel,
  generate: GeneratePanel,
  pick: PickPanel,
  media: MediaPanel,
  publish: PublishPanel,
  metrics: MetricsPanel,
  spawn: SpawnPanel, // 同时承载「提炼」节点
};

export interface PanelHostProps {
  nodeId: PipelineNodeId | undefined;
  workspace: Workspace;
  onChanged: () => Promise<void>;
  onOpenVideo: (videoId: string, tab?: VideoDetailTab) => void;
  onClose: () => void;
}

export function PanelHost({ nodeId, onClose, ...rest }: PanelHostProps) {
  const node = PIPELINE_SHAPE.find((item) => item.id === nodeId);
  const opened = useRef<PipelineNodeId | undefined>(undefined);
  // 主动作栏的落点：面板 portal 进来，常驻抽屉底部。没有面板填充时它就是 0 高度。
  const [footerSlot, setFooterSlot] = useState<HTMLDivElement | null>(null);
  // 抽屉是受控的、没有 trigger，Radix 关闭后不会自己还焦点：手动还给刚才那个节点，
  // 否则 Esc 之后 Tab 会从文档头重来。
  useEffect(() => {
    if (nodeId) { opened.current = nodeId; return; }
    const last = opened.current;
    if (!last) return;
    opened.current = undefined;
    document.querySelector<HTMLElement>(`[data-pipeline-node="${last}"]`)?.focus();
  }, [nodeId]);

  const Panel = node ? PANELS[node.panel] : undefined;
  return <NodePanel
    anchorId={node?.id}
    description={node?.description}
    footer={<div ref={setFooterSlot} />}
    icon={node ? stageIcon(node.id) : undefined}
    onClose={onClose}
    open={Boolean(node)}
    title={node?.label ?? ""}
  >
    {node && Panel ? <Panel footerSlot={footerSlot} onClose={onClose} {...rest} /> : null}
  </NodePanel>;
}
