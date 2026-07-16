import { Badge, Button, Checkbox, Field, Input, Textarea, cn } from "@fifty/workbench-ui";
import { AlertTriangle, Check, ChevronDown, Edit3, RefreshCw, X } from "lucide-react";
import { FormEvent, useState } from "react";
import type { ScriptCandidate, ScriptQuality, StoryboardShot } from "../domain";
import { ShotEditor } from "./shot-editor";

const ROLE_COPY: Record<string, string> = {
  hook: "钩子", pain: "痛点", problem: "痛点", feature: "卖点", value: "卖点", proof: "证明",
  objection: "打消顾虑", cta: "引导下单", body: "过渡",
};

function duration(shots: StoryboardShot[]): number {
  return shots.reduce((total, shot) => total + shot.duration_seconds, 0);
}

function preview(script: string): string {
  const lines = script.replace(/^[#>*\s-]+/gm, "").split(/(?<=[。！？!?])|\n+/).map((item) => item.trim()).filter(Boolean);
  return lines.slice(0, 2).join(" ");
}

// 质量诚实（v5 内容合同）：只说结构写全了，真实转化只由回流数据授予。
// 「可以拍了」「还差证据」是 v7 术语表的人话说法，status 枚举不动。
function qualityCopy(quality: ScriptQuality) {
  return quality.status === "ready_to_test"
    ? { label: "可以拍了", tone: "success" as const }
    : { label: "还没准备好", tone: "warning" as const };
}

function qualityReason(quality: ScriptQuality): string {
  const failed = quality.checks.find((check) => !check.passed);
  if (!failed) return "该写的都写到了";
  return failed.detail || failed.label;
}

function ShotList({ shots }: { shots: StoryboardShot[] }) {
  return <section aria-label="镜头清单"><div className="mb-2 flex items-center justify-between gap-3"><h4 className="m-0 text-sm font-semibold text-ink">镜头清单</h4><span className="text-xs tabular-nums text-ink-muted">{shots.length} 个镜头 · {duration(shots)} 秒</span></div><div className="overflow-hidden rounded-md border border-border"><div className="hidden grid-cols-[72px_64px_1.1fr_1.2fr_1fr] gap-3 border-b border-border bg-surface-muted px-3 py-2 text-xs font-semibold text-ink-muted sm:grid"><span>作用</span><span>时长</span><span>画面</span><span>台词</span><span>字幕</span></div>{shots.map((shot, index) => <article className="grid gap-2 border-b border-border p-3 last:border-b-0 sm:grid-cols-[72px_64px_1.1fr_1.2fr_1fr] sm:gap-3 sm:py-2.5" key={`${shot.order}-${index}`}><div className="flex items-center justify-between gap-2 sm:block"><Badge tone={index === 0 ? "brand" : undefined}>{ROLE_COPY[shot.role] ?? shot.role ?? "过渡"}</Badge><span className="text-xs tabular-nums text-ink-muted sm:hidden">{shot.duration_seconds} 秒</span></div><span className="hidden text-xs tabular-nums text-ink-soft sm:block">{shot.duration_seconds} 秒</span><p className="m-0 text-sm leading-5 text-ink"><span className="mr-1 font-semibold text-ink-muted sm:hidden">画面：</span>{shot.visual || "—"}</p><p className="m-0 text-sm leading-5 text-ink-soft"><span className="mr-1 font-semibold text-ink-muted sm:hidden">台词：</span>{shot.voiceover || "—"}</p><p className="m-0 text-sm leading-5 text-ink-soft"><span className="mr-1 font-semibold text-ink-muted sm:hidden">字幕：</span>{shot.on_screen_text || "—"}</p></article>)}</div></section>;
}

function QualityDetails({ candidate }: { candidate: ScriptCandidate }) {
  const quality = candidate.quality;
  const passed = quality.checks.filter((check) => check.passed).length;
  return <section aria-label="脚本写全了吗"><div className="mb-2 flex items-center justify-between gap-3"><h4 className="m-0 text-sm font-semibold text-ink">脚本写全了吗</h4><span className="text-xs font-semibold tabular-nums text-ink-soft">{passed} / {quality.checks.length} 项达标</span></div><ul className="m-0 grid list-none gap-1.5 p-0 sm:grid-cols-2">{quality.checks.map((check) => <li className="flex min-h-9 items-start gap-2 rounded-md bg-surface-muted px-2.5 py-2 text-xs leading-5" key={check.key}>{check.passed ? <Check aria-hidden className="mt-0.5 size-3.5 shrink-0 text-success" /> : <X aria-hidden className="mt-0.5 size-3.5 shrink-0 text-warning" />}<span><span className="font-semibold text-ink">{check.label}</span>{check.detail ? <span className="ml-1 text-ink-muted">{check.detail}</span> : null}</span></li>)}</ul>{quality.risks.length ? <div className="mt-2 flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-xs leading-5 text-ink-soft"><AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0 text-warning" /><p className="m-0"><span className="font-semibold text-ink">改前先看：</span>{quality.risks.join("；")}</p></div> : null}</section>;
}

function ClaimDetails({ candidate }: { candidate: ScriptCandidate }) {
  if (!candidate.claims_used.length && !candidate.claims_needing_evidence.length) return null;
  return <section aria-label="商品卖点" className="grid gap-2 text-xs leading-5 sm:grid-cols-2"><div className="rounded-md border border-border p-3"><h4 className="m-0 font-semibold text-ink">这条用到的商品卖点</h4><p className="mb-0 mt-1 text-ink-soft">{candidate.claims_used.length ? candidate.claims_used.join("、") : "没用到具体卖点"}</p></div><div className={cn("rounded-md border p-3", candidate.claims_needing_evidence.length ? "border-warning bg-warning-soft" : "border-border")}><h4 className="m-0 font-semibold text-ink">没根据的说法（发之前先核实）</h4><p className="mb-0 mt-1 text-ink-soft">{candidate.claims_needing_evidence.length ? candidate.claims_needing_evidence.join("、") : "没有"}</p></div></section>;
}

interface EditorProps {
  candidate: ScriptCandidate;
  pending: boolean;
  onCancel: () => void;
  onSave: (title: string, script: string, shots: StoryboardShot[]) => Promise<void>;
}

function CandidateEditor({ candidate, pending, onCancel, onSave }: EditorProps) {
  const [title, setTitle] = useState(candidate.title);
  const [script, setScript] = useState(candidate.script);
  const [shots, setShots] = useState(candidate.shots);
  const submit = (event: FormEvent) => { event.preventDefault(); void onSave(title.trim(), script.trim(), shots); };
  return <form className="grid gap-4" onSubmit={submit}><div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]"><Field htmlFor={`candidate-title-${candidate.id}`} label="内容标题" required><Input id={`candidate-title-${candidate.id}`} onChange={(event) => setTitle(event.target.value)} required value={title} /></Field><Field htmlFor={`candidate-script-${candidate.id}`} label="完整台词" required><Textarea className="min-h-28" id={`candidate-script-${candidate.id}`} onChange={(event) => setScript(event.target.value)} required value={script} /></Field></div><ShotEditor idPrefix={`candidate-shot-${candidate.id}`} onChange={setShots} shots={shots} title="镜头清单" /><div className="flex justify-end gap-2"><Button disabled={pending} onClick={onCancel} type="button" variant="quiet">取消</Button><Button loading={pending} loadingLabel="保存中" type="submit">保存并重新检查</Button></div></form>;
}

interface Props {
  candidate: ScriptCandidate;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  onSave: (candidate: ScriptCandidate, title: string, script: string, shots: StoryboardShot[]) => Promise<void>;
  onRegenerate: (candidate: ScriptCandidate) => Promise<void>;
}

export function CandidateReview({ candidate, checked, onCheckedChange, onSave, onRegenerate }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState<"save" | "rewrite">();
  const [error, setError] = useState<string>();
  const status = qualityCopy(candidate.quality);
  const reason = qualityReason(candidate.quality);
  const saved = async (title: string, script: string, shots: StoryboardShot[]) => {
    setPending("save"); setError(undefined);
    try { await onSave(candidate, title, script, shots); setEditing(false); }
    catch { setError("没能保存，请再试一次。"); }
    finally { setPending(undefined); }
  };
  const regenerate = async () => {
    setPending("rewrite"); setError(undefined);
    try { await onRegenerate(candidate); }
    catch { setError("这条没能重写，原来的脚本还留着。"); }
    finally { setPending(undefined); }
  };
  return (
    <article className={cn("overflow-hidden rounded-md border bg-surface", checked ? "border-brand" : "border-border")}>
      <div className="grid min-h-[82px] grid-cols-[44px_minmax(0,1fr)] items-stretch">
        <div className="grid place-items-center border-r border-border" title={candidate.selected_video_id ? "已选去拍" : "选择这条"}>
          <Checkbox
            aria-label={`选择脚本：${candidate.title}`}
            checked={candidate.selected_video_id ? true : checked}
            className="relative size-11 border-0 bg-transparent after:absolute after:size-5 after:rounded-sm after:border after:border-border-strong after:bg-surface hover:border-0 data-[state=checked]:border-0 data-[state=checked]:bg-transparent data-[state=checked]:after:border-brand data-[state=checked]:after:bg-brand [&>span]:relative [&>span]:z-10"
            disabled={Boolean(candidate.selected_video_id)}
            onCheckedChange={(value) => onCheckedChange(value === true)}
          />
        </div>
        <button
          aria-expanded={expanded}
          className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 px-3 py-2.5 text-left outline-none hover:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus sm:grid-cols-[minmax(140px,1.1fr)_minmax(150px,1.3fr)_48px_minmax(140px,.9fr)_16px]"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          <div className="min-w-0"><div className="flex min-w-0 items-center gap-2"><span className="truncate text-sm font-semibold text-ink">{candidate.title}</span>{candidate.provider === "mock" ? <span className="shrink-0 text-xs text-ink-muted">示例</span> : null}</div><p className="mb-0 mt-1 truncate text-xs font-medium text-brand">{candidate.angle}</p></div>
          <p className="col-span-2 m-0 line-clamp-2 text-[13px] leading-5 text-ink-soft sm:col-span-1">{preview(candidate.script)}</p>
          <span className="hidden text-xs tabular-nums text-ink-muted sm:block">{duration(candidate.shots)} 秒</span>
          <span className="col-span-2 flex min-w-0 items-center gap-1.5 sm:col-span-1"><Badge tone={status.tone}>{candidate.selected_video_id ? "已选去拍" : status.label}</Badge><span className="truncate text-xs text-ink-muted">{reason}</span></span>
          <ChevronDown aria-hidden className={cn("size-4 text-ink-muted transition-transform", expanded && "rotate-180")} />
        </button>
      </div>
      {expanded ? <div className="grid gap-5 border-t border-border bg-canvas p-3 sm:p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="m-0 text-xs font-semibold text-brand">这条主打 · {candidate.angle}</p><p className="mb-0 mt-1 text-sm leading-6 text-ink-soft">{candidate.hypothesis}</p></div>{!editing && !candidate.selected_video_id ? <div className="flex gap-2"><Button disabled={Boolean(pending)} onClick={(event) => { event.stopPropagation(); setEditing(true); }} size="sm" variant="secondary"><Edit3 aria-hidden className="size-3.5" />编辑脚本</Button><Button loading={pending === "rewrite"} loadingLabel="重写中" onClick={(event) => { event.stopPropagation(); void regenerate(); }} size="sm" variant="quiet"><RefreshCw aria-hidden className="size-3.5" />重写这一条</Button></div> : null}</div>{editing ? <CandidateEditor candidate={candidate} onCancel={() => setEditing(false)} onSave={saved} pending={pending === "save"} /> : <><section aria-label="完整台词"><h4 className="m-0 text-sm font-semibold text-ink">完整台词</h4><p className="mb-0 mt-2 whitespace-pre-wrap rounded-md border border-border bg-surface p-3 text-sm leading-7 text-ink">{candidate.script}</p></section><ShotList shots={candidate.shots} /><ClaimDetails candidate={candidate} /><QualityDetails candidate={candidate} /></>}{error ? <p className="m-0 text-sm text-danger" role="alert">{error}</p> : null}</div> : null}
    </article>
  );
}
