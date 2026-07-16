import { Badge, Button, EmptyState, Tabs, TabsContent, TabsList, TabsTrigger, toast } from "@fifty/workbench-ui";
import { CalendarClock, CalendarPlus, Plus, RefreshCw, Users } from "lucide-react";
import { useState, type ReactNode } from "react";
import { api, ApiError } from "../../api";
import { platformLabel, PublishDialog } from "../../dialogs/publish-dialog";
import { AccountDialog } from "../../dialogs/resource-dialogs";
import type { Account, Publication, Tone, Video, VideoView, Workspace } from "../../domain";
import { accountLabel, formatDate } from "../../format";
import type { PanelProps } from "./types";

// ============================================================
// 「发布」面板（design-v7-canvas.md）：吃掉原「账号」页与「发布日历」页。
//
// 三块用分段组织，一次只看一块：
//   待发布 —— 有成片、还没安排发布的视频（复用 PublishDialog）
//   排期与记录 —— 全部发布任务：时间 / 视频 / 账号 / 状态 / 平台结果 / 操作
//   账号 —— 连接状态与新增（复用 AccountDialog）
//
// 640px 抽屉里不摆六列表格：每条任务竖着读，长链接一律 break-all 折行。
// 真正的发布控件（执行 / 重试 / 核对）在视频抽屉的发布页签，本面板只负责
// 把「哪条需要你」摆出来，用 onOpenVideo 送过去，不复制第二套控件。
// ============================================================

const PUBLICATION_STATUS: Record<Publication["status"], { label: string; tone: Tone }> = {
  draft: { label: "待发布", tone: "neutral" },
  scheduled: { label: "已排期", tone: "info" },
  publishing: { label: "发布中", tone: "info" },
  succeeded: { label: "已发布", tone: "success" },
  succeeded_with_warnings: { label: "已发布·有提示", tone: "warning" },
  failed: { label: "失败", tone: "danger" },
  unknown: { label: "待核对", tone: "warning" },
};

const ACCOUNT_STATUS: Record<Account["connection_status"], { label: string; tone: Tone }> = {
  connected: { label: "已连接", tone: "success" },
  mock: { label: "示例账号", tone: "info" },
  needs_auth: { label: "需授权", tone: "warning" },
  disconnected: { label: "不可用", tone: "danger" },
};

const AVAILABLE: Account["connection_status"][] = ["connected", "mock"];

interface TaskRow { publication: Publication; view: VideoView; account?: Account }

/** 排期即时间轴：有排期看排期，发过看发布时间，都没有就看建立时间 */
function taskTime(publication: Publication): string {
  return publication.scheduled_at ?? publication.published_at ?? publication.created_at;
}

function taskRows(workspace: Workspace): TaskRow[] {
  return workspace.videos
    .flatMap((view) => view.video.publications.map((publication) => ({
      publication,
      view,
      account: workspace.accounts.find((item) => item.id === publication.account_id),
    })))
    .sort((a, b) => taskTime(a.publication).localeCompare(taskTime(b.publication)));
}

/** 待发布：有成片、还没建过发布任务的视频。已有任务的都在「排期与记录」里 */
function arrangeableVideos(workspace: Workspace): VideoView[] {
  return workspace.videos.filter((view) => view.video.media.length > 0 && !view.video.publications.length);
}

/**
 * 这一条要不要你动手：失败、待核对、任务还没执行、YouTube 排期待确认。
 * 其余（演示平台到点自动发、平台已受理）都不该占用你的注意力。
 */
function needsYou(row: TaskRow): boolean {
  const { status, external_id } = row.publication;
  if (status === "failed" || status === "unknown" || status === "draft") return true;
  return status === "scheduled" && row.account?.platform === "youtube" && !external_id;
}

// ============================================================
// 三块共用的骨架：一句实话 + 一条列表，不套卡片
// ============================================================

function Section({ summary, action, children }: { summary: string; action?: ReactNode; children: ReactNode }) {
  return <section className="grid gap-3">
    <div className="flex items-start justify-between gap-3">
      <p className="m-0 text-[13px] leading-5 text-ink-soft">{summary}</p>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
    {children}
  </section>;
}

function PanelList({ label, children }: { label: string; children: ReactNode }) {
  return <ul aria-label={label} className="m-0 grid list-none divide-y divide-border rounded-[14px] border border-border p-0">{children}</ul>;
}

/** 「看这一条」：标题即入口，键盘可达、焦点可见 */
function VideoLink({ title, videoId, onOpenVideo }: { title: string; videoId: string; onOpenVideo: PanelProps["onOpenVideo"] }) {
  return <button
    aria-label={`看这一条：${title}`}
    className="m-0 rounded-[6px] text-left text-sm font-semibold text-ink outline-none hover:underline focus-visible:ring-2 focus-visible:ring-focus"
    onClick={() => onOpenVideo(videoId, "publish")}
    type="button"
  >{title}</button>;
}

// ============================================================
// ① 待发布：有成片，等你安排
// ============================================================

function ArrangeSection({ workspace, onChanged, onOpenVideo }: Omit<PanelProps, "onClose" | "footerSlot">) {
  const [target, setTarget] = useState<Video>();
  const views = arrangeableVideos(workspace);
  if (!views.length) return <EmptyState
    description="在「成片」节点把做好的视频传上来后，它会自动出现在这里等你安排发布。以前发过的视频，也能从任意一条视频的「发布」页关联进来。"
    icon={CalendarPlus}
    title="没有要安排发布的视频"
  />;
  return <Section summary={`${views.length} 条视频可以安排发布，也能关联以前发过的视频`}>
    <PanelList label="待发布视频">
      {views.map((view) => <li className="flex items-start gap-3 px-4 py-3.5" key={view.video.id}>
        <div className="grid min-w-0 flex-1 gap-0.5">
          <VideoLink onOpenVideo={onOpenVideo} title={view.video.title} videoId={view.video.id} />
          <p className="m-0 break-words text-[13px] leading-5 text-ink-muted">
            上传于 {formatDate(view.video.media.at(-1)?.created_at ?? null)}
          </p>
        </div>
        <Button className="min-h-11 shrink-0 sm:min-h-9" onClick={() => setTarget(view.video)} size="sm" variant="secondary">安排发布</Button>
      </li>)}
    </PanelList>
    {target ? <PublishDialog
      onCompleted={onChanged}
      onOpenChange={(next) => { if (!next) setTarget(undefined); }}
      open
      video={target}
      workspace={workspace}
    /> : null}
  </Section>;
}

// ============================================================
// ② 排期与发布记录
// ============================================================

function SyncButton({ publication, onChanged }: { publication: Publication; onChanged: () => Promise<void> }) {
  const [pending, setPending] = useState(false);
  const sync = async () => {
    setPending(true);
    try { await api.sync(publication.id); await onChanged(); toast.success("数据已同步"); }
    catch (cause) { toast.error(cause instanceof ApiError ? cause.message : "同步失败"); }
    finally { setPending(false); }
  };
  return <Button className="min-h-11 sm:min-h-9" loading={pending} loadingLabel="同步中" onClick={() => void sync()} size="sm" variant="secondary">
    <RefreshCw aria-hidden="true" className="size-3.5" />同步
  </Button>;
}

function TaskAction({ row, onChanged, onOpenVideo }: { row: TaskRow; onChanged: () => Promise<void>; onOpenVideo: PanelProps["onOpenVideo"] }) {
  if (needsYou(row)) return <Button
    aria-label={`去处理：${row.view.video.title}`}
    className="min-h-11 sm:min-h-9"
    onClick={() => onOpenVideo(row.view.video.id, "publish")}
    size="sm"
    variant="secondary"
  >处理<span aria-hidden="true">→</span></Button>;
  if (row.publication.status === "publishing") return <span className="text-[13px] text-ink-muted">平台处理中</span>;
  if (row.publication.external_id) return <SyncButton onChanged={onChanged} publication={row.publication} />;
  return <span className="text-[13px] text-ink-muted">等排期时间</span>;
}

/** 平台结果：有链接给链接，失败给原因，还没有就不占位 */
function TaskResult({ publication }: { publication: Publication }) {
  if (publication.url) return <a className="break-all text-[13px] text-brand hover:underline" href={publication.url} rel="noreferrer" target="_blank">查看平台视频</a>;
  if (publication.error) return <p className="m-0 break-words text-[13px] leading-5 text-ink-soft">原因：{publication.error}</p>;
  return null;
}

function TaskItem({ row, onChanged, onOpenVideo }: { row: TaskRow; onChanged: () => Promise<void>; onOpenVideo: PanelProps["onOpenVideo"] }) {
  const status = PUBLICATION_STATUS[row.publication.status];
  return <li className="grid gap-2 px-4 py-3.5">
    <div className="flex items-start gap-3">
      <div className="grid min-w-0 flex-1 gap-0.5">
        <VideoLink onOpenVideo={onOpenVideo} title={row.view.video.title} videoId={row.view.video.id} />
        <p className="m-0 break-words text-[13px] leading-5 text-ink-muted">
          <time className="tabular-nums">{formatDate(taskTime(row.publication))}</time> · {accountLabel(row.account)} · {platformLabel(row.account?.platform)}
        </p>
      </div>
      <Badge tone={status.tone}>{status.label}</Badge>
    </div>
    <div className="flex items-end justify-between gap-3">
      <div className="min-w-0 flex-1"><TaskResult publication={row.publication} /></div>
      <div className="shrink-0"><TaskAction onChanged={onChanged} onOpenVideo={onOpenVideo} row={row} /></div>
    </div>
  </li>;
}

function TasksSection({ rows, onChanged, onOpenVideo }: { rows: TaskRow[]; onChanged: () => Promise<void>; onOpenVideo: PanelProps["onOpenVideo"] }) {
  if (!rows.length) return <EmptyState
    description="把一条做好的视频安排发布后，它的发布记录会带着时间、平台结果和失败原因出现在这里。"
    icon={CalendarClock}
    title="还没有发布记录"
  />;
  const handling = rows.filter(needsYou).length;
  return <Section summary={handling ? `${rows.length} 条发布记录 · ${handling} 条需要你处理` : `${rows.length} 条发布记录 · 都不用你动手`}>
    <PanelList label="排期与发布记录">
      {rows.map((row) => <TaskItem key={row.publication.id} onChanged={onChanged} onOpenVideo={onOpenVideo} row={row} />)}
    </PanelList>
  </Section>;
}

// ============================================================
// ③ 账号与连接状态
// ============================================================

function InspectButton({ account, onChanged }: { account: Account; onChanged: () => Promise<void> }) {
  const [pending, setPending] = useState(false);
  const inspect = async () => {
    setPending(true);
    try { await api.inspectAccount(account.id); await onChanged(); toast.success(`${account.name} 连接正常`); }
    catch (cause) { toast.error(`检查未通过：${cause instanceof ApiError ? cause.message : "请先检查发布平台连接和账号授权。"}`); }
    finally { setPending(false); }
  };
  return <Button className="min-h-11 sm:min-h-9" loading={pending} loadingLabel="检查中" onClick={() => void inspect()} size="sm" variant="secondary">
    <RefreshCw aria-hidden="true" className="size-3.5" />检查连接
  </Button>;
}

function AccountItem({ account, group, onChanged }: { account: Account; group: string | undefined; onChanged: () => Promise<void> }) {
  const status = ACCOUNT_STATUS[account.connection_status];
  return <li className="grid gap-2 px-4 py-3.5">
    <div className="flex items-start gap-3">
      <div className="grid min-w-0 flex-1 gap-0.5">
        <p className="m-0 break-words text-sm font-semibold text-ink">{account.name}</p>
        <p className="m-0 break-all text-[13px] leading-5 text-ink-muted">{account.handle} · {platformLabel(account.platform)} · {group ?? "未分组"}</p>
      </div>
      <Badge tone={status.tone}>{status.label}</Badge>
    </div>
    <div className="flex items-end justify-between gap-3">
      <p className="m-0 min-w-0 flex-1 break-words text-[13px] leading-5 text-ink-soft">{account.context || "还没写账号风格：写清楚说话风格、面向人群和不能碰的话题。"}</p>
      <div className="shrink-0"><InspectButton account={account} onChanged={onChanged} /></div>
    </div>
  </li>;
}

function AccountsSection({ workspace, onChanged }: { workspace: Workspace; onChanged: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const groups = new Map(workspace.account_groups.map((item) => [item.id, item.name]));
  const available = workspace.accounts.filter((item) => AVAILABLE.includes(item.connection_status)).length;
  const blocked = workspace.accounts.length - available;
  return <>
    {workspace.accounts.length ? <Section
      action={<Button className="min-h-11 sm:min-h-9" onClick={() => setOpen(true)} size="sm" variant="secondary"><Plus aria-hidden="true" className="size-4" />新增</Button>}
      summary={`${available}/${workspace.accounts.length} 个账号可发布${blocked ? ` · ${blocked} 个需处理` : ""}`}
    >
      <PanelList label="账号与连接状态">
        {workspace.accounts.map((account) => <AccountItem account={account} group={groups.get(account.group_id)} key={account.id} onChanged={onChanged} />)}
      </PanelList>
    </Section> : <EmptyState
      action={{ label: "新增账号 / 分组", onClick: () => setOpen(true) }}
      description="连接一个真实账号，或先用示例账号把整个流程跑一遍——示例账号发布的是示例数据，不会真的对外发出去。"
      icon={Users}
      title="还没有账号"
    />}
    <AccountDialog onCompleted={onChanged} onOpenChange={setOpen} open={open} workspace={workspace} />
  </>;
}

// ============================================================
// 面板本体
// ============================================================

type PublishTab = "arrange" | "tasks" | "accounts";

function TabCount({ value }: { value: number }) {
  if (!value) return null;
  return <span className="ml-1.5 tabular-nums text-ink-muted">{value}</span>;
}

export function PublishPanel({ workspace, onChanged, onOpenVideo }: PanelProps) {
  const rows = taskRows(workspace);
  const arrange = arrangeableVideos(workspace);
  // 有要你处理的任务就先给你看它——「现在该干什么」优先于固定顺序
  const [tab, setTab] = useState<PublishTab>(rows.some(needsYou) ? "tasks" : "arrange");
  return <Tabs onValueChange={(value) => setTab(value as PublishTab)} value={tab}>
    <TabsList aria-label="发布面板分区" className="grid w-full grid-cols-3">
      <TabsTrigger value="arrange">待发布<TabCount value={arrange.length} /></TabsTrigger>
      <TabsTrigger value="tasks">排期与记录<TabCount value={rows.length} /></TabsTrigger>
      <TabsTrigger value="accounts">账号<TabCount value={workspace.accounts.length} /></TabsTrigger>
    </TabsList>
    <TabsContent value="arrange"><ArrangeSection onChanged={onChanged} onOpenVideo={onOpenVideo} workspace={workspace} /></TabsContent>
    <TabsContent value="tasks"><TasksSection onChanged={onChanged} onOpenVideo={onOpenVideo} rows={rows} /></TabsContent>
    <TabsContent value="accounts"><AccountsSection onChanged={onChanged} workspace={workspace} /></TabsContent>
  </Tabs>;
}
