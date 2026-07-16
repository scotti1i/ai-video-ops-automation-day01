import { HumanApproval, IrreversibleWarning } from "@fifty/workbench-ai";
import { Badge, Button, Checkbox, Dialog, DialogContent, Field, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Tabs, TabsContent, TabsList, TabsTrigger, toast } from "@fifty/workbench-ui";
import { FormEvent, useState } from "react";
import { api, ApiError } from "../api";
import type { Account, Publication, Video, Workspace } from "../domain";
import { formatDate, toLocalDateTime } from "../format";

// 平台码 → 中文名。发布面板也复用这里的映射，全产品一处维护；
// 永不把 mock/demo 之类的内部码露给用户。
const PLATFORM_LABEL: Record<string, string> = { youtube: "YouTube", tiktok: "TikTok", douyin: "抖音", "mock-social": "示例平台" };

export function platformLabel(platform: string | undefined): string {
  if (!platform) return "未识别平台";
  return PLATFORM_LABEL[platform] ?? platform;
}

function AccountChecks({ accounts, selected, onChange }: { accounts: Account[]; selected: string[]; onChange: (value: string[]) => void }) {
  const toggle = (id: string, checked: boolean) => onChange(checked ? [...selected, id] : selected.filter((item) => item !== id));
  return <fieldset className="grid gap-2 rounded-md border border-border p-3"><legend className="px-1 text-sm font-semibold text-ink">发布账号</legend>{accounts.map((account) => <label className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-muted" key={account.id}><Checkbox checked={selected.includes(account.id)} onCheckedChange={(value) => toggle(account.id, value === true)} /><span className="font-medium">{account.name}</span><Badge className="ml-auto">{platformLabel(account.platform)}</Badge></label>)}</fieldset>;
}

interface DialogProps { video: Video; workspace: Workspace; open: boolean; onOpenChange: (open: boolean) => void; onCompleted: () => Promise<void> }

export function PublishDialog({ video, workspace, open, onOpenChange, onCompleted }: DialogProps) {
  const [mode, setMode] = useState<"arrange" | "history">("arrange");
  const [accountIds, setAccountIds] = useState(video.account_ids);
  const [scheduledAt, setScheduledAt] = useState("");
  const [historyAccount, setHistoryAccount] = useState(video.account_ids[0] ?? "");
  const [externalId, setExternalId] = useState("");
  const [url, setUrl] = useState("");
  const [publishedAt, setPublishedAt] = useState(toLocalDateTime(new Date().toISOString()));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();

  const save = () => mode === "arrange"
    ? api.arrange(video.id, accountIds, scheduledAt ? new Date(scheduledAt).toISOString() : null)
    : api.importPublication(video.id, { account_id: historyAccount, external_id: externalId, url, published_at: new Date(publishedAt).toISOString() });

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setPending(true); setError(undefined);
    try { await save(); await onCompleted(); onOpenChange(false); toast.success(mode === "arrange" ? "已安排发布" : "历史视频已关联"); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "操作失败，请重试。"); }
    finally { setPending(false); }
  };

  return <Dialog onOpenChange={onOpenChange} open={open}><DialogContent description="不管是新安排的发布，还是以前发过的视频，都会归到同一条视频下：一起看数据，再决定要不要照着它再做一版。" title={`${video.title} · 发布`}><form className="grid gap-4" onSubmit={(event) => void submit(event)}><Tabs onValueChange={(value) => setMode(value as "arrange" | "history")} value={mode}><TabsList className="grid w-full grid-cols-2"><TabsTrigger value="arrange">安排发布</TabsTrigger><TabsTrigger value="history">关联历史视频</TabsTrigger></TabsList><TabsContent value="arrange"><div className="grid gap-4"><AccountChecks accounts={workspace.accounts} onChange={setAccountIds} selected={accountIds} /><Field htmlFor="schedule-at" label="发布时间" hint="留空就先放进待发布、不定时间；真正发到 YouTube 前还要你手动确认一次。"><Input id="schedule-at" min={toLocalDateTime(new Date().toISOString())} onChange={(event) => setScheduledAt(event.target.value)} type="datetime-local" value={scheduledAt} /></Field></div></TabsContent><TabsContent value="history"><div className="grid gap-3"><Field htmlFor="history-account" label="已发布账号" required><Select onValueChange={setHistoryAccount} value={historyAccount}><SelectTrigger id="history-account"><SelectValue placeholder="选择账号" /></SelectTrigger><SelectContent>{workspace.accounts.map((account) => <SelectItem key={account.id} value={account.id}>{account.name} · {platformLabel(account.platform)}</SelectItem>)}</SelectContent></Select></Field><Field htmlFor="external-id" label="平台视频编号" hint="视频在平台上的编号，一般能在视频链接里找到。" required><Input id="external-id" onChange={(event) => setExternalId(event.target.value)} required value={externalId} /></Field><Field htmlFor="history-url" label="视频链接" required><Input id="history-url" onChange={(event) => setUrl(event.target.value)} required type="url" value={url} /></Field><Field htmlFor="published-at" label="发布时间" required><Input id="published-at" onChange={(event) => setPublishedAt(event.target.value)} required type="datetime-local" value={publishedAt} /></Field></div></TabsContent></Tabs>{error ? <p className="m-0 text-sm text-danger" role="alert">{error}</p> : null}<div className="flex justify-end gap-2"><Button onClick={() => onOpenChange(false)} type="button" variant="secondary">取消</Button><Button disabled={mode === "arrange" ? !accountIds.length : !historyAccount} loading={pending} loadingLabel="保存中" type="submit">{mode === "arrange" ? "安排发布" : "关联到本视频"}</Button></div></form></DialogContent></Dialog>;
}

function ReconcileForm({ publication, onCancel, onCompleted }: { publication: Publication; onCancel: () => void; onCompleted: () => Promise<void> }) {
  const [externalId, setExternalId] = useState("");
  const [url, setUrl] = useState("");
  const [publishedAt, setPublishedAt] = useState(toLocalDateTime(new Date().toISOString()));
  const [auditNote, setAuditNote] = useState("");
  const [confirmedAbsent, setConfirmedAbsent] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setPending(true); setError(undefined);
    try { await api.reconcile(publication.id, { external_id: externalId, url, published_at: new Date(publishedAt).toISOString() }); await onCompleted(); toast.success("平台结果已关联"); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "核对失败"); }
    finally { setPending(false); }
  };
  const resetAbsent = async () => {
    setPending(true); setError(undefined);
    try { await api.confirmAbsent(publication.id, auditNote); await onCompleted(); toast.success("可以重试了"); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "核对失败"); }
    finally { setPending(false); }
  };
  return <form className="grid gap-3 rounded-md border border-warning bg-warning/5 p-3" onSubmit={(event) => void submit(event)}><p className="m-0 text-sm font-semibold">核对平台结果</p><p className="m-0 text-xs leading-5 text-ink-muted">如果平台上确实已经生成了视频，把它的编号和链接填进来，就能接回原来的发布记录。</p><Field htmlFor={`reconcile-id-${publication.id}`} label="平台视频编号" required><Input id={`reconcile-id-${publication.id}`} onChange={(event) => setExternalId(event.target.value)} required value={externalId} /></Field><Field htmlFor={`reconcile-url-${publication.id}`} label="视频链接" required><Input id={`reconcile-url-${publication.id}`} onChange={(event) => setUrl(event.target.value)} required type="url" value={url} /></Field><Field htmlFor={`reconcile-time-${publication.id}`} label="发布时间" required><Input id={`reconcile-time-${publication.id}`} onChange={(event) => setPublishedAt(event.target.value)} required type="datetime-local" value={publishedAt} /></Field><Button loading={pending} loadingLabel="核对中" size="sm" type="submit">保存核对结果</Button><div className="grid gap-3 border-t border-warning/30 pt-3"><p className="m-0 text-sm font-semibold">平台未创建视频</p><IrreversibleWarning>误判会导致重复发布。请先在平台后台搜索标题、频道和发布时间。</IrreversibleWarning><Field htmlFor={`absent-note-${publication.id}`} label="核对说明" required><Input id={`absent-note-${publication.id}`} onChange={(event) => setAuditNote(event.target.value)} placeholder="例如：频道后台和发布时间表里都没有这条记录" value={auditNote} /></Field><label className="flex items-start gap-2 text-xs leading-5 text-ink-muted"><Checkbox checked={confirmedAbsent} onCheckedChange={(value) => setConfirmedAbsent(value === true)} /><span>我已在平台后台确认没有创建视频</span></label><Button disabled={!confirmedAbsent || !auditNote.trim()} loading={pending} loadingLabel="保存中" onClick={() => void resetAbsent()} size="sm" type="button" variant="secondary">确认未创建，允许重试</Button></div>{error ? <p className="m-0 text-sm text-danger" role="alert">{error}</p> : null}<Button onClick={onCancel} size="sm" type="button" variant="secondary">取消</Button></form>;
}

export function PublicationControl({ publication, account, onCompleted }: { publication: Publication; account?: Account; onCompleted: () => Promise<void> }) {
  const [pending, setPending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const scheduledYouTubeUpload = publication.status === "scheduled"
    && account?.platform === "youtube"
    && !publication.external_id;
  const canExecute = ["draft", "failed"].includes(publication.status) || scheduledYouTubeUpload;

  const act = async (confirmed: boolean) => {
    setPending(true);
    const polling = canExecute ? window.setInterval(() => { void onCompleted(); }, 2_500) : undefined;
    try { if (canExecute) await api.execute(publication.id, confirmed); else await api.sync(publication.id); await onCompleted(); setConfirming(false); toast.success(canExecute ? "已开始发布" : "数据已同步"); }
    catch (cause) { toast.error(cause instanceof ApiError ? cause.message : "操作失败"); }
    finally { if (polling) window.clearInterval(polling); setPending(false); }
  };

  if (canExecute && account?.platform === "youtube" && confirming) return <HumanApproval approveLabel="确认上传到 YouTube" description={`会上传到 ${account.name}。为了安全，视频先设成「仅自己可见」；${publication.scheduled_at ? "你已设好发布时间，到点由 YouTube 自动公开。" : "你没设发布时间，上传后会一直保持「仅自己可见」，需要你之后手动公开。"}`} onApprove={() => void act(true)} onReject={() => setConfirming(false)} pending={pending} title="需要人工确认"><IrreversibleWarning>平台一旦上传，本工作台没法自动撤回，请先确认视频、标题和账号都对。</IrreversibleWarning></HumanApproval>;
  if (publication.status === "unknown" && reconciling) return <ReconcileForm onCancel={() => setReconciling(false)} onCompleted={onCompleted} publication={publication} />;
  if (publication.status === "unknown") return <Button onClick={() => setReconciling(true)} size="sm" variant="secondary">核对平台结果</Button>;
  if (publication.status === "publishing") return <Button loading loadingLabel="发布中" size="sm" variant="secondary">发布中</Button>;
  if (canExecute) return <Button loading={pending} loadingLabel="发布中" onClick={() => account?.platform === "youtube" ? setConfirming(true) : void act(false)} size="sm">{publication.status === "failed" ? "重试" : scheduledYouTubeUpload ? "确认排期上传" : "执行发布"}</Button>;
  if (publication.external_id) return <Button loading={pending} loadingLabel="同步中" onClick={() => void act(false)} size="sm" variant="secondary">同步数据</Button>;
  return <span className="text-xs text-ink-muted">定于 {formatDate(publication.scheduled_at)} 发布</span>;
}
