import { Badge, EmptyState, cn } from "@fifty/workbench-ui";
import { ChevronRight, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import type { Batch, VideoView, Workspace } from "../../domain";
import { formatDate } from "../../format";
import { scriptSettingsSummary } from "../../script-settings";
import type { PanelProps } from "./types";

// ============================================================
// 「生成候选」面板：全只读。这一步系统自己跑，人不拍板。
// 只回答两件事：这批照着什么做（依据）、现在做到哪了（状态）。
//
// design-v7-canvas.md：画布上永远不出现口播正文——这里也不出现。
// 候选正文是「选稿」面板的事，这里只给依据和去处。
// ============================================================

/**
 * 停在这一步的批次：依据存下了、候选一条都没出来。
 * 判定与 pipeline-model.ts 的徽章口径同源（`!pending && !video_ids`），
 * 徽章说 N，面板就得数得出 N——两处不能各说各的。
 */
function stalledBatches(workspace: Workspace): Batch[] {
  return workspace.batches.filter((batch) =>
    !(batch.candidates ?? []).some((candidate) => !candidate.selected_video_id) && !batch.video_ids.length);
}

/** 徽章的另一半：视频建好了、脚本还没生成（裂变出来的子视频多半停在这） */
function pendingScripts(workspace: Workspace): VideoView[] {
  return workspace.videos.filter((view) => view.stage.stage === "needs_script");
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <>
    <dt className="m-0 text-[13px] leading-6 text-ink-muted">{label}</dt>
    <dd className="m-0 min-w-0 break-words text-sm leading-6 text-ink">{children}</dd>
  </>;
}

function BatchBasis({ batch, workspace }: { batch: Batch; workspace: Workspace }) {
  const product = workspace.products.find((item) => item.id === batch.product_id);
  return <section className="min-w-0">
    <div className="flex items-start justify-between gap-3">
      <h3 className="m-0 min-w-0 break-words text-base font-semibold text-ink">{batch.name}</h3>
      <Badge className="shrink-0" tone="neutral">正在写脚本</Badge>
    </div>
    <dl className="mt-3 grid grid-cols-[96px_minmax(0,1fr)] gap-x-4 gap-y-2">
      <Fact label="商品">{product?.title ?? "没选商品"}</Fact>
      <Fact label="想拍的方向">{batch.brief.trim() || "没写，系统自己定方向"}</Fact>
      <Fact label="参考视频">
        {/* 长链接一律折行：truncate 的 nowrap 会把整列撑宽、顶破抽屉（design.md v6 抽屉结构硬约定） */}
        {batch.reference_url
          ? <a className="break-all text-brand underline underline-offset-2 outline-none focus-visible:ring-2 focus-visible:ring-focus" href={batch.reference_url} rel="noreferrer" target="_blank">{batch.reference_url}</a>
          : "没给参考"}
      </Fact>
      <Fact label="已生成脚本"><span className="tabular-nums">{(batch.candidates ?? []).length}</span> 条</Fact>
      <Fact label="写稿设置">{batch.script_settings ? scriptSettingsSummary(batch.script_settings) : "用默认设置"}</Fact>
      <Fact label="开始时间">{formatDate(batch.created_at)}</Fact>
    </dl>
  </section>;
}

// 整行可点，不放"看这一条"按钮——想看就点。不显示 VID 编号，对用户没意义。
function PendingScriptRow({ view, batchName, onOpenVideo }: { view: VideoView; batchName?: string; onOpenVideo: PanelProps["onOpenVideo"] }) {
  return <li>
    <button
      className="group flex w-full items-center gap-3 rounded-[8px] px-2 py-2.5 text-left outline-none hover:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
      onClick={() => onOpenVideo(view.video.id, "script")}
      type="button"
    >
      <span className="min-w-0 flex-1 truncate text-sm text-ink">{view.video.title}</span>
      {batchName ? <span className="max-w-[38%] shrink-0 truncate text-[13px] text-ink-muted">{batchName}</span> : null}
      <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-ink-muted opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
  </li>;
}

export function GeneratePanel({ workspace, onOpenVideo, onClose }: PanelProps) {
  const batches = stalledBatches(workspace);
  const pending = pendingScripts(workspace);

  if (!batches.length && !pending.length) {
    return <EmptyState
      action={{ label: "返回", onClick: onClose }}
      description="从「这批想做什么」开始：选商品、写想拍的方向、定要几条，系统就会自动写出一组角度不同的脚本。"
      icon={Sparkles}
      title="现在没有在写的脚本"
    />;
  }

  const batchNames = new Map(workspace.batches.map((batch) => [batch.id, batch.name]));
  return <div className="grid min-w-0 gap-4">
    {batches.map((batch) => <BatchBasis batch={batch} key={batch.id} workspace={workspace} />)}
    {pending.length ? <section className={cn("min-w-0", batches.length && "border-t border-border pt-4")}>
      <h3 className="m-0 mb-1 text-[13px] font-semibold text-ink-muted">还缺脚本 · <span className="tabular-nums">{pending.length}</span> 条</h3>
      <ul className="m-0 grid list-none p-0">
        {pending.map((view) => <PendingScriptRow batchName={view.video.batch_id ? batchNames.get(view.video.batch_id) : undefined} key={view.video.id} onOpenVideo={onOpenVideo} view={view} />)}
      </ul>
    </section> : null}
  </div>;
}
