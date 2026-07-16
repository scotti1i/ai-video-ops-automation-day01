import {
  Button, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, toast,
} from "@fifty/workbench-ui";
import { FileCheck2 } from "lucide-react";
import { useState } from "react";
import { createPortal } from "react-dom";
import { api, ApiError } from "../../api";
import { CandidateReview } from "../../components/candidate-review";
import { activeScriptProducer, type Batch, type ScriptCandidate, type StoryboardShot, type Workspace } from "../../domain";
import type { PanelProps } from "./types";

// ============================================================
// 「选稿」面板（design-v7-canvas.md：判断在面板里，不在画布上）
//
// 原「脚本候选」弹窗搬进 640px 抽屉。内容合同一条不改：
// 默认零勾选 · 「只选可以拍的」是快捷动作 · 0 选中时主按钮禁用并提示。
// 「批次」在 v7 里只剩这一处存在——同一批天然处在同一阶段，多批才需要切。
// ============================================================

/** 待选脚本 = 这一批里还没被选进成片的（后端可能不带 candidates 字段） */
function pendingOf(batch: Batch): ScriptCandidate[] {
  return (batch.candidates ?? []).filter((candidate) => !candidate.selected_video_id);
}

/** 「只选可以拍的」快捷动作；默认零勾选，要用户自己比较过再选 */
function readyIds(candidates: ScriptCandidate[]): Set<string> {
  return new Set(candidates.filter((item) => item.quality.status === "ready_to_test").map((item) => item.id));
}

function productName(batch: Batch, workspace: Workspace): string {
  if (!batch.product_id) return "还没选商品";
  return workspace.products.find((product) => product.id === batch.product_id)?.title ?? "这个商品找不到了";
}

// 空态三种，都得诚实：没开过批 ≠ 脚本还在生成 ≠ 这批挑完了。三种都指出下一步在哪。
// 「生成中」的判据和 pipeline-model 的 generate 计数同一条：有依据、还没出脚本。
const EMPTY_COPY = {
  none: { title: "还没有脚本", hint: "回流程图点「这批想做什么」，写好的脚本会先到这里等你挑。" },
  generating: { title: "AI 正在写脚本", hint: "你填的商品和要求已经收到，脚本写好会自动出现在这里。想看进度，回流程图看「生成脚本」那一步。" },
  done: { title: "脚本都挑完了", hint: "挑中的脚本已经在「成片」等你上传视频。想再对比一轮，回流程图点「这批想做什么」。" },
};

function emptyReason(workspace: Workspace): keyof typeof EMPTY_COPY {
  if (!workspace.batches.length) return "none";
  return workspace.batches.some((batch) => !batch.video_ids.length) ? "generating" : "done";
}

function EmptyPick({ workspace, onClose }: { workspace: Workspace; onClose: () => void }) {
  const copy = EMPTY_COPY[emptyReason(workspace)];
  return <div className="grid justify-items-center gap-3 py-8 text-center">
    <FileCheck2 aria-hidden className="size-6 text-ink-muted" />
    <div className="max-w-xs">
      <p className="m-0 text-sm font-semibold text-ink">{copy.title}</p>
      <p className="mb-0 mt-1.5 text-[13px] leading-5 text-ink-soft">{copy.hint}</p>
    </div>
    <Button onClick={onClose} variant="secondary">返回</Button>
  </div>;
}

// onOpenVideo 这里用不上：待选脚本还不是视频，选进成片才有 video_id。
export function PickPanel({ workspace, onChanged, onClose, footerSlot }: PanelProps) {
  const [chosenId, setChosenId] = useState<string>();
  const [selected, setSelected] = useState<Set<string>>(new Set()); // 默认零勾选
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();

  const draftBatches = workspace.batches.filter((batch) => pendingOf(batch).length > 0);
  // 当前批次从数据推出来，不用 effect 同步：手选的批次挑完就自动落到最新一批。
  const batch = draftBatches.find((item) => item.id === chosenId) ?? draftBatches.at(-1);
  const candidates = batch ? pendingOf(batch) : [];
  // 勾选集合永远和屏幕上这批取交集——切批、选完刷新都不用清空动作，特殊情况就没了。
  const picked = candidates.filter((candidate) => selected.has(candidate.id));

  if (!batch) return <EmptyPick onClose={onClose} workspace={workspace} />;

  const toggle = (id: string, checked: boolean) => setSelected((current) => {
    const next = new Set(current);
    if (checked) next.add(id); else next.delete(id);
    return next;
  });
  // 编辑与重写都不留本地副本：写完拿 onChanged 的新工作区（面板契约）。
  const save = async (candidate: ScriptCandidate, title: string, script: string, shots: StoryboardShot[]) => {
    await api.updateCandidate(candidate.batch_id, candidate.id, { title, script, shots });
    await onChanged();
  };
  const regenerate = async (candidate: ScriptCandidate) => {
    await api.regenerateCandidate(candidate.batch_id, candidate.id, activeScriptProducer(workspace));
    await onChanged();
  };
  const confirm = async () => {
    if (!picked.length) return;
    setPending(true); setError(undefined);
    try {
      const result = await api.selectCandidates(batch.id, picked.map((candidate) => candidate.id));
      await onChanged();
      toast.success(`已挑 ${result.videos.length} 条，去拍吧`);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "没能提交，请再试一次。");
    } finally { setPending(false); }
  };

  return <div className="grid gap-4">
    <section className="grid gap-2">
      {draftBatches.length > 1
        ? <label className="grid gap-1.5"><span className="text-[13px] font-medium text-ink-soft">当前这批</span>
          <Select onValueChange={setChosenId} value={batch.id}>
            <SelectTrigger aria-label="切换这批视频"><SelectValue /></SelectTrigger>
            <SelectContent>{draftBatches.map((item) =>
              <SelectItem key={item.id} value={item.id}>{item.name} · 还有 {pendingOf(item).length} 条要挑</SelectItem>)}
            </SelectContent>
          </Select>
        </label>
        : <p className="m-0 text-sm font-semibold text-ink">{batch.name}</p>}
      {/* 这批的依据只给判断脚本用得上的一行；完整依据是「生成候选」面板的事，不在这儿重画一遍 */}
      <p className="m-0 line-clamp-2 text-[13px] leading-5 text-ink-muted">
        {productName(batch, workspace)} · {batch.brief || "根据商品资料，帮你想几个不同思路做对比"}
      </p>
    </section>

    <section className="grid gap-2 border-t border-border pt-3">
      <div className="flex items-center justify-between gap-3">
        <p className="m-0 text-[13px] font-semibold tabular-nums text-ink">{candidates.length} 条脚本等你挑</p>
        <div className="flex gap-1">
          <Button onClick={() => setSelected(readyIds(candidates))} size="sm" variant="quiet">只选可以拍的</Button>
          <Button disabled={!picked.length} onClick={() => setSelected(new Set())} size="sm" variant="quiet">清空</Button>
        </div>
      </div>
      {/* 质量诚实压成一句：结构过关 ≠ 真实转化 */}
      <p className="m-0 text-[13px] leading-5 text-ink-muted">「可以拍了」只是脚本写全了，能不能卖货，得发出去看数据才知道。</p>
    </section>

    <div aria-label="脚本" className="grid gap-2.5" role="group">
      {candidates.map((candidate) => <CandidateReview
        candidate={candidate}
        checked={selected.has(candidate.id)}
        key={candidate.id}
        onCheckedChange={(checked) => toggle(candidate.id, checked)}
        onRegenerate={regenerate}
        onSave={save}
      />)}
    </div>

    {/* 主按钮常驻抽屉底：10 条脚本读下来，不该再滚回去找它。走 footerSlot，别在正文里 sticky。 */}
    {footerSlot ? createPortal(
      <div className="grid gap-2 border-t border-border bg-surface px-6 py-4">
        {error ? <p className="m-0 text-[13px] leading-5 text-danger" role="alert">{error}</p> : null}
        <div className="flex items-center justify-between gap-3">
          <p className="m-0 text-[13px] leading-5 text-ink-muted">
            {picked.length ? "没挑的会留下，不会消失。" : "先勾选要拍的脚本"}
          </p>
          <Button
            className="shrink-0"
            disabled={!picked.length}
            loading={pending}
            loadingLabel="正在送去拍"
            onClick={() => void confirm()}
          >
            <FileCheck2 aria-hidden className="size-4" />选好 {picked.length} 条，拿去拍
          </Button>
        </div>
      </div>, footerSlot) : null}
  </div>;
}
