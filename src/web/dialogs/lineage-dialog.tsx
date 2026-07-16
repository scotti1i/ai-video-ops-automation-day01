import { Button, Checkbox, Dialog, DialogContent, Field, Input, Tabs, TabsContent, TabsList, TabsTrigger, Textarea, toast } from "@fifty/workbench-ui";
import { FormEvent, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import type { CommentSnapshot, Video } from "../domain";

type Mode = "single" | "batch";

function CommentPicker({ comments, selected, onChange }: { comments: CommentSnapshot[]; selected: string[]; onChange: (value: string[]) => void }) {
  const toggle = (id: string, checked: boolean) => onChange(checked ? [...selected, id] : selected.filter((item) => item !== id));
  if (!comments.length) return <p className="m-0 text-sm text-ink-muted">还没有可以引用的评论，这次只记下它是从这条视频改出来的。</p>;
  return <fieldset className="grid max-h-44 gap-2 overflow-auto rounded-md border border-border p-3"><legend className="px-1 text-sm font-semibold text-ink">引用用户评论</legend>{comments.map((comment) => <label className="flex items-start gap-2 rounded-md p-2 text-sm hover:bg-surface-muted" key={comment.id}><Checkbox checked={selected.includes(comment.id)} className="mt-0.5" onCheckedChange={(value) => toggle(comment.id, value === true)} /><span><span className="font-semibold">{comment.author}</span><span className="ml-2 text-xs text-ink-muted">{comment.likes} 赞</span><span className="mt-1 block text-ink-soft">{comment.content}</span></span></label>)}</fieldset>;
}

interface LineageDialogProps {
  video: Video;
  /** 后端规则生成的父视频表现提炼（performance_brief）；null 时不渲染该块 */
  performanceBrief?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCompleted: () => Promise<void>;
}

export function LineageDialog({ video, performanceBrief, open, onOpenChange, onCompleted }: LineageDialogProps) {
  const comments = useMemo(() => video.publications.flatMap((item) => item.comments), [video.publications]);
  const [mode, setMode] = useState<Mode>("single");
  const [variation, setVariation] = useState("");
  const [commentIds, setCommentIds] = useState<string[]>([]);
  const [batchName, setBatchName] = useState("");
  const [variations, setVariations] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();

  const save = () => mode === "single"
    ? api.branch(video.id, variation, commentIds)
    : api.batch(video.id, batchName, variations.split("\n").map((item) => item.trim()).filter(Boolean));

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setPending(true); setError(undefined);
    try { await save(); await onCompleted(); onOpenChange(false); toast.success(mode === "single" ? "新的一版建好了" : "这批视频都建好了"); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "没能创建，请再试一次。"); }
    finally { setPending(false); }
  };

  return <Dialog onOpenChange={onOpenChange} open={open}><DialogContent description={`会照着这条视频再做，你只用写这次改哪里。`} title={`${video.title} · 再做一版`}><form className="grid gap-4" onSubmit={(event) => void submit(event)}>{performanceBrief ? <section aria-label="这条视频的表现" className="rounded-md border border-border bg-surface-muted px-3 py-2.5"><p className="m-0 text-xs font-semibold text-ink-muted">这条视频的表现</p><p className="mb-0 mt-1 text-sm leading-6 text-ink">{performanceBrief}</p></section> : null}<Tabs onValueChange={(value) => setMode(value as Mode)} value={mode}><TabsList className="grid w-full grid-cols-2"><TabsTrigger value="single">做一条</TabsTrigger><TabsTrigger value="batch">做多条</TabsTrigger></TabsList><TabsContent value="single"><div className="grid gap-4"><Field htmlFor="variation" label="这次改什么" hint="例：人物不变，换浴室场景和反问开场。" required><Textarea id="variation" onChange={(event) => setVariation(event.target.value)} required value={variation} /></Field><CommentPicker comments={comments} onChange={setCommentIds} selected={commentIds} /></div></TabsContent><TabsContent value="batch"><div className="grid gap-4"><Field htmlFor="batch-name" label="这批视频的名字" required><Input id="batch-name" onChange={(event) => setBatchName(event.target.value)} placeholder="例：浴室场景第二轮" required value={batchName} /></Field><Field htmlFor="variations" label="每一版改什么" hint="每行写一个改动，系统按每行各做一条视频，都能查到是从这条改的。" required><Textarea className="min-h-40" id="variations" onChange={(event) => setVariations(event.target.value)} placeholder={"换人物：美区宝妈\n换场景：酒店浴室\n换开场：先展示失败结果"} required value={variations} /></Field></div></TabsContent></Tabs>{error ? <p className="m-0 text-sm text-danger" role="alert">{error}</p> : null}<div className="flex justify-end gap-2"><Button onClick={() => onOpenChange(false)} type="button" variant="secondary">取消</Button><Button disabled={mode === "batch" && !variations.trim()} loading={pending} loadingLabel="创建中" type="submit">{mode === "single" ? "创建这一条" : "创建这批视频"}</Button></div></form></DialogContent></Dialog>;
}
