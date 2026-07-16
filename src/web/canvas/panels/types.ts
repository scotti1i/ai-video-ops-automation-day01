import type { VideoDetailTab, Workspace } from "../../domain";

// ============================================================
// 面板契约（design-v7-canvas.md：判断在面板里，不在画布上）
//
// 点节点 → 右侧 640px 抽屉（DetailDrawer）→ 渲染对应面板。
// 抽屉的标题栏、描述、关闭按钮、Esc 由 panel-host 接管：
// 面板只渲染正文，不要自己写 <h1>、不要自己画关闭按钮。
// 正文横向永不溢出（design.md v6 抽屉结构硬约定）：长链接、长文件名
// 一律 break-all 折行，禁止用 truncate 的 nowrap 赌容器宽度。
// ============================================================

export interface PanelProps {
  /** 当前工作区快照，只读；写完调 onChanged 拿新的，不要就地改 */
  workspace: Workspace;
  /** 数据变更后刷新工作区；await 它之后再关面板或给 toast */
  onChanged: () => Promise<void>;
  /** 打开单条视频详情抽屉——面板里「看这一条」的唯一出口 */
  onOpenVideo: (videoId: string, tab?: VideoDetailTab) => void;
  /** 关闭本面板；面板内「完成/取消」用它，Esc 与关闭按钮已由抽屉接管 */
  onClose: () => void;
  /**
   * 主动作栏的槽位：用 createPortal 把动作栏放进去，它会常驻在抽屉底部、不随正文滚动。
   * 不要在正文里用 `sticky bottom-0` 自己做——正文是带 p-6 的滚动容器，
   * sticky 会被包含块钳在内边距上沿，底下漏出一道 24px 的缝（负 margin 补偿无效）。
   * 边框与内边距自己给（槽位只保证不被压缩）：`border-t border-border bg-surface px-6 py-4`。
   */
  footerSlot: HTMLElement | null;
}

/**
 * 面板键：七个面板，七个 agent。
 * 画布有八个节点——「提炼」与「再做一版」共用 spawn 面板：
 * 提炼结论（performance_brief）正是裂变的入参，见 design.md v6 页面级修正第 4 条。
 * 节点 → 面板的映射在 pipeline-model.ts 的 PIPELINE_SHAPE.panel 里，改一行即可。
 */
export type PanelKey = "brief" | "generate" | "pick" | "media" | "publish" | "metrics" | "spawn";
