import { Badge, Button, Checkbox, Dialog, DialogContent, Field, Tabs, TabsContent, TabsList, TabsTrigger, Textarea } from "@fifty/workbench-ui";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { blankShot, ShotEditor } from "../components/shot-editor";
import type { ScriptArtifact, StoryboardShot, Video } from "../domain";

type Mode = "ai" | "edit" | "import";
/** 写脚本用哪一路由 workspace.active_script_producer 决定，这里只透传，不再限定枚举 */
type Producer = string;

const SOURCE_COPY: Record<string, string> = {
  mock: "示例生成 · 未调用真实模型",
  model: "AI 生成",
  import: "导入",
  user: "手工编辑",
  external: "外部提供",
};

export function cleanScriptContent(content: string): string {
  const legacyLine = (line: string) => /^#{1,6}\s*(?:已有脚本样例|办公室五分钟鲜榨果汁)\s*$/.test(line)
    || /^【(?:样例生成|模拟输出)[^】]*】\s*$/.test(line)
    || (/^这条先测试/.test(line) && line.includes("下一条只换成"));
  return content.split(/\r?\n/).filter((line) => !legacyLine(line.trim())).join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export function scriptSourceCopy(source: string): string {
  return SOURCE_COPY[source] ?? "已保存版本";
}

function versionNote(script: ScriptArtifact): string {
  const note = script.note.replace(/\s*·\s*由\s+.+\s+生成\s*$/, "").trim();
  if (script.source === "mock" && /(?:零密钥|样例生成|演示工作区)/.test(note)) return "示例工作区自带";
  return note || "生成这个版本";
}

function ConversationHistory({ video }: { video: Video }) {
  const turns = video.scripts.filter((item) => ["mock", "model"].includes(item.source));
  if (!turns.length) return <p className="m-0 text-sm text-ink-muted">还没有 AI 生成的版本。你让 AI 改过之后，新版本会留在这里。</p>;
  return <section aria-label="脚本版本记录" className="grid max-h-56 gap-2 overflow-y-auto rounded-md border border-border bg-surface-muted p-3" role="log">{turns.map((turn) => <article className="grid gap-1 rounded-md bg-surface p-3" key={turn.id}><div className="flex items-center gap-2"><Badge>第 {turn.version} 版</Badge><p className="m-0 text-xs font-semibold text-ink-soft">{scriptSourceCopy(turn.source)}</p></div><p className="m-0 text-sm text-ink">{versionNote(turn)}</p><p className="m-0 line-clamp-3 text-sm leading-6 text-ink-muted">{cleanScriptContent(turn.content)}</p></article>)}</section>;
}

interface Props { video: Video; producer: Producer; open: boolean; onOpenChange: (open: boolean) => void; onCompleted: () => Promise<void> }

export function ArtifactDialog({ video, producer, open, onOpenChange, onCompleted }: Props) {
  const currentScript = cleanScriptContent(video.scripts.at(-1)?.content ?? "");
  const currentShots = useMemo(() => video.storyboards.at(-1)?.shots ?? [blankShot(1)], [video.storyboards]);
  const [mode, setMode] = useState<Mode>(currentScript ? "edit" : "ai");
  const [instruction, setInstruction] = useState("");
  const [script, setScript] = useState(currentScript);
  const [shots, setShots] = useState<StoryboardShot[]>(currentShots);
  const [includeShots, setIncludeShots] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => { if (open) { setScript(currentScript); setShots(currentShots); setIncludeShots(false); } }, [currentScript, currentShots, open]);

  const save = async () => {
    if (mode === "ai") await api.generate(video.id, instruction || video.goal, producer);
    else if (mode === "import") await api.importArtifacts(video.id, script, includeShots ? shots : undefined);
    else await api.updateScript(video.id, script, "在详情里手动改的", shots);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setPending(true); setError(undefined);
    try { await save(); await onCompleted(); onOpenChange(false); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "保存失败，请重试。"); }
    finally { setPending(false); }
  };

  const submitLabel = mode === "ai" ? "发送并生成新版本" : "保存为新版本";
  return <Dialog onOpenChange={onOpenChange} open={open}><DialogContent className="w-[min(760px,calc(100vw-32px))]" description={`当前视频：${video.title}。每次保存都会保留旧版本。`} title="编辑脚本和镜头"><form className="grid gap-4" onSubmit={(event) => void submit(event)}><Tabs onValueChange={(value) => setMode(value as Mode)} value={mode}><TabsList className="grid w-full grid-cols-3"><TabsTrigger value="ai">AI 对话</TabsTrigger><TabsTrigger value="edit">直接编辑</TabsTrigger><TabsTrigger value="import">导入新版</TabsTrigger></TabsList><TabsContent value="ai"><div className="grid gap-3"><ConversationHistory video={video} /><Field htmlFor="rewrite-instruction" label={video.scripts.length ? "继续告诉 AI 怎么改" : "告诉 AI 这次怎么写"} hint={producer === "mock" ? "现在用的是示例生成器，不会调用真实模型。" : "会用已连接的 AI 模型。"}><Textarea id="rewrite-instruction" onChange={(event) => setInstruction(event.target.value)} placeholder="例：保留核心卖点，换成对比开场，缩短到 25 秒" required value={instruction} /></Field></div></TabsContent><TabsContent value="import"><div className="grid gap-3"><Field htmlFor="replace-script" label="新脚本"><Textarea id="replace-script" onChange={(event) => setScript(event.target.value)} required value={script} /></Field><label className="flex items-center gap-2 text-sm font-medium text-ink"><Checkbox checked={includeShots} onCheckedChange={(value) => setIncludeShots(value === true)} />同时导入已有镜头</label>{includeShots ? <ShotEditor idPrefix="imported-shot" onChange={setShots} shots={shots} title="已有镜头" /> : <p className="m-0 text-xs text-ink-muted">不勾选时，系统会照脚本自动拆好镜头，之后能改。</p>}</div></TabsContent><TabsContent value="edit"><div className="grid gap-4"><Field htmlFor="edit-script" label="脚本内容"><Textarea className="min-h-40" id="edit-script" onChange={(event) => setScript(event.target.value)} required value={script} /></Field><ShotEditor idPrefix="edited-shot" onChange={setShots} shots={shots} /></div></TabsContent></Tabs>{error ? <p className="m-0 text-sm text-danger" role="alert">{error}</p> : null}<div className="flex justify-end gap-2"><Button onClick={() => onOpenChange(false)} type="button" variant="secondary">取消</Button><Button loading={pending} loadingLabel="保存中" type="submit">{submitLabel}</Button></div></form></DialogContent></Dialog>;
}
