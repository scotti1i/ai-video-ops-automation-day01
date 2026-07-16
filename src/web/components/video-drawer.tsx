import type { ArtifactRef, EvidenceRef, RunEvent } from "@fifty/run-contract";
import { ArtifactFrame, EvidencePanel, RunTimeline } from "@fifty/workbench-ai";
import { Badge, Button, DetailDrawer, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, InlineAlert, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Tabs, TabsContent, TabsList, TabsTrigger, cn, toast } from "@fifty/workbench-ui";
import { CalendarPlus, Check, FileEdit, FileText, GitBranch, MoreHorizontal, Send, Upload, Video as VideoIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { ArtifactDialog, cleanScriptContent, scriptSourceCopy } from "../dialogs/artifact-dialog";
import { LineageDialog } from "../dialogs/lineage-dialog";
import { PublicationControl, PublishDialog } from "../dialogs/publish-dialog";
import { UploadDialog } from "../dialogs/media/upload-dialog";
import { activeScriptProducer, type MediaArtifact, type Publication, type ScriptArtifact, type StoryboardArtifact, type VideoDetailTab, type VideoStage, type VideoView, type Workspace } from "../domain";
import { accountLabel, formatDate, formatMoney, formatNumber, latestMetric, performanceLabel } from "../format";
import { ScriptQualityPanel } from "./script-quality-panel";

type PublicationEventCopy = Pick<RunEvent, "type" | "status" | "summary"> & {
  detail: string;
};

const PUBLICATION_EVENT_COPY: Record<Publication["status"], PublicationEventCopy> = {
  draft: {
    type: "tool.requested",
    status: "idle",
    summary: "等待发布",
    detail: "已排进发布队列，还没发出去",
  },
  scheduled: {
    type: "tool.requested",
    status: "queued",
    summary: "已排期",
    detail: "到点自动发布",
  },
  publishing: {
    type: "step.started",
    status: "running",
    summary: "正在发布",
    detail: "平台正在处理",
  },
  succeeded: {
    type: "tool.completed",
    status: "succeeded",
    summary: "发布成功",
    detail: "平台已确认发布",
  },
  succeeded_with_warnings: {
    type: "tool.completed",
    status: "succeeded",
    summary: "发布成功，有提示",
    detail: "看下面的平台提示",
  },
  failed: {
    type: "tool.failed",
    status: "failed",
    summary: "发布失败",
    detail: "看原因后可以重试",
  },
  unknown: {
    type: "approval.requested",
    status: "waiting_for_human",
    summary: "结果待确认",
    detail: "先到平台确认，别重复发布",
  },
};

// 抽屉副标题按发布状态分叉：未发布/发布中只说下一步该干什么，一个字不提“数据”（BUG-1）
const NEXT_STEP: Partial<Record<VideoStage, string>> = {
  needs_script: "下一步：写脚本",
  needs_media: "下一步：拍视频",
  ready_to_publish: "下一步：发布",
  publishing: "正在发布",
  scheduled: "已排期，等发布",
  publish_failed: "发布没成功，看原因",
  needs_reconciliation: "发布结果待确认",
};

function drawerSubtitle(view: VideoView): string {
  const next = NEXT_STEP[view.stage.stage];
  if (next) return next;
  // 到这里只剩“已发布”：有数据就显示表现，没数据就照实说还没起来
  return `${view.stage.label} · ${performanceLabel(view.performance.label)}`;
}

function versionNote(script: ScriptArtifact): string {
  const note = script.note.replace(/\s*·\s*由\s+.+\s+生成\s*$/, "").trim();
  if (script.source === "mock" && /(?:零密钥|样例生成|演示工作区)/.test(note)) return "示例自带";
  return note || scriptSourceCopy(script.source);
}

function publicationMessage(value: string): string {
  return value.replaceAll("样例", "示例").replaceAll("mock-social", "示例平台");
}

function platformCopy(platform?: string): string {
  if (!platform) return "未识别平台";
  return { youtube: "YouTube", tiktok: "TikTok", douyin: "抖音", "mock-social": "示例平台" }[platform] ?? platform;
}

function evidence(view: VideoView): EvidenceRef[] {
  const context = view.video.contexts.at(-1);
  if (!context) return [];
  const base: EvidenceRef[] = [{ id: context.id, label: "这条视频的要求", kind: "input", excerpt: context.brief }];
  return [...base, ...context.sources.map((source) => ({ id: source.id, label: source.label, kind: "source" as const, href: source.href ?? undefined, excerpt: source.file_name === "existing-script.md" ? cleanScriptContent(source.content) : source.content || source.file_name || undefined }))];
}

function publicationRunEvent(videoId: string, publication: Publication): RunEvent {
  const copy = PUBLICATION_EVENT_COPY[publication.status];
  return {
    event_id: publication.id,
    run_id: videoId,
    type: copy.type,
    status: copy.status,
    timestamp: publication.updated_at,
    summary: copy.summary,
    detail: publication.error ? publicationMessage(publication.error) : publication.url ?? copy.detail,
  };
}

function runEvents(view: VideoView): RunEvent[] {
  const video = view.video;
  const events: RunEvent[] = [{ event_id: `${video.id}-created`, run_id: video.id, type: "run.created", status: "succeeded", timestamp: video.created_at, summary: "新建了这条视频", detail: video.goal }];
  if (video.scripts.length) events.push({ event_id: video.scripts.at(-1)!.id, run_id: video.id, type: "artifact.updated", status: "succeeded", timestamp: video.scripts.at(-1)!.created_at, summary: `脚本改到了第 ${video.scripts.at(-1)!.version} 版`, detail: versionNote(video.scripts.at(-1)!) });
  if (video.media.length) events.push({ event_id: video.media.at(-1)!.id, run_id: video.id, type: "artifact.updated", status: "succeeded", timestamp: video.media.at(-1)!.created_at, summary: "上传了视频", detail: video.media.at(-1)!.file_name });
  video.publications.forEach((item) => events.push(publicationRunEvent(video.id, item)));
  return events.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
}

function ContextSection({ view }: { view: VideoView }) {
  const items = evidence(view);
  return <div className="grid gap-4"><div className="rounded-md border border-border bg-surface-muted p-3"><p className="m-0 text-xs font-semibold text-ink-muted">本次目标</p><p className="mb-0 mt-1 text-sm leading-6 text-ink">{view.video.goal}</p></div><EvidencePanel evidence={items} limitation={view.video.contexts.length > 1 ? `当前显示第 ${view.video.contexts.at(-1)?.version} 版，旧版本仍保留。` : undefined} realEvidence={items.some((item) => item.kind === "source" && item.href?.startsWith("http"))} /></div>;
}

function VersionPicker({ scripts, value, onChange }: { scripts: ScriptArtifact[]; value: number; onChange: (value: number) => void }) {
  if (!scripts.length) return null;
  return <Select onValueChange={(next) => onChange(Number(next))} value={String(value)}><SelectTrigger aria-label="查看脚本版本" className="w-36"><SelectValue /></SelectTrigger><SelectContent>{[...scripts].reverse().map((item) => <SelectItem key={item.id} value={String(item.version)}>第 {item.version} 版</SelectItem>)}</SelectContent></Select>;
}

function StoryboardPreview({ board }: { board?: StoryboardArtifact }) {
  // 有脚本没镜头才提示去拆；“还没有脚本”的空态在别处只说一次（BUG-2）
  if (!board) return <InlineAlert title="还没拆镜头" tone="warning">点「编辑脚本」，给每个镜头补上画面、台词、字幕和时长。</InlineAlert>;
  const duration = board.shots.reduce((total, item) => total + item.duration_seconds, 0);
  return <section aria-label="镜头清单" className="overflow-hidden rounded-md border border-border"><header className="flex items-center justify-between gap-3 border-b border-border bg-surface-muted px-4 py-3"><div><h3 className="m-0 text-sm font-semibold text-ink">镜头清单</h3><p className="mb-0 mt-0.5 text-xs text-ink-muted">{board.shots.length} 个镜头 · 共 {duration} 秒</p></div><span className="text-xs font-medium text-ink-soft">按播放顺序</span></header><ol className="m-0 list-none divide-y divide-border p-0">{board.shots.map((shot) => <li className="grid grid-cols-[2rem_minmax(0,1fr)_auto] gap-3 px-4 py-4" key={shot.order}><span className="grid size-8 place-items-center rounded-md bg-surface-selected text-xs font-semibold tabular-nums text-brand">{String(shot.order).padStart(2, "0")}</span><dl className="m-0 grid min-w-0 gap-3 sm:grid-cols-2"><div><dt className="text-xs font-semibold text-ink-muted">画面</dt><dd className="m-0 mt-1 text-sm leading-5 text-ink">{shot.visual}</dd></div><div><dt className="text-xs font-semibold text-ink-muted">台词</dt><dd className="m-0 mt-1 text-sm leading-5 text-ink-soft">{shot.voiceover || "—"}</dd></div>{shot.on_screen_text ? <div className="sm:col-span-2"><dt className="text-xs font-semibold text-ink-muted">字幕</dt><dd className="m-0 mt-1 text-sm leading-5 text-brand">{shot.on_screen_text}</dd></div> : null}</dl><span className="text-xs tabular-nums text-ink-muted">{shot.duration_seconds}s</span></li>)}</ol></section>;
}

function ArtifactsSection({ view, onChanged }: { view: VideoView; onChanged: () => Promise<void> }) {
  const video = view.video;
  const latestVersion = video.scripts.at(-1)?.version ?? 0;
  const [selectedVersion, setSelectedVersion] = useState(latestVersion);
  const [restoring, setRestoring] = useState(false);
  useEffect(() => setSelectedVersion(latestVersion), [latestVersion, video.id]);
  const script = video.scripts.find((item) => item.version === selectedVersion) ?? video.scripts.at(-1);
  const board = [...video.storyboards].filter((item) => item.version <= (script?.version ?? 0)).at(-1) ?? video.storyboards.at(-1);
  const restore = async () => {
    if (!script) return;
    setRestoring(true);
    try { await api.updateScript(video.id, cleanScriptContent(script.content), `切回第 ${script.version} 版`, board?.shots); await onChanged(); toast.success("已切回这个版本，并存成了最新一版。"); }
    catch (cause) { toast.error(cause instanceof ApiError ? cause.message : "没能切回，请重试"); }
    finally { setRestoring(false); }
  };
  // 空态整屏只留一句 + 一个动作，指向上面那颗“写脚本”按钮（BUG-2）
  if (!script) return <InlineAlert title="还没有脚本" tone="info">这条还没有脚本，点上面的「写脚本」开始。</InlineAlert>;
  const artifact: ArtifactRef = { id: script.id, label: `脚本 · 第 ${script.version} 版`, kind: "report" };
  const shotCount = board?.shots.length ?? 0;
  const duration = board?.shots.reduce((total, item) => total + item.duration_seconds, 0) ?? 0;
  return <div className="grid gap-4"><div className="flex flex-wrap items-center gap-2"><p className="m-0 mr-auto text-xs text-ink-muted">{board ? `${shotCount} 个镜头 · 共 ${duration} 秒` : `第 ${script.version} 版`}</p><VersionPicker onChange={setSelectedVersion} scripts={video.scripts} value={selectedVersion} />{script.version !== latestVersion ? <Button className="min-h-11 sm:min-h-9" loading={restoring} loadingLabel="切换中" onClick={() => void restore()} size="sm" variant="quiet">切回这个版本</Button> : null}</div><ScriptQualityPanel claimsNeedingEvidence={script.claims_needing_evidence} claimsUsed={script.claims_used} quality={script.quality} /><ArtifactFrame artifact={artifact} meta={`${formatDate(script.created_at)} · ${scriptSourceCopy(script.source)}`}><pre className="m-0 whitespace-pre-wrap font-sans text-sm leading-6 text-ink-soft">{cleanScriptContent(script.content)}</pre></ArtifactFrame><StoryboardPreview board={board} /></div>;
}

function MediaPreview({ media }: { media: MediaArtifact }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [media.id]);

  if (media.storage_path.startsWith("sample://")) {
    return (
      <InlineAlert title="示例视频不能播放" tone="info">
        上传你自己的视频后，就能在这里预览。
      </InlineAlert>
    );
  }
  if (!media.mime_type.startsWith("video/")) {
    return <InlineAlert title="当前文件无法在线预览" tone="warning">可以替换为 MP4、MOV 或 WebM 视频。</InlineAlert>;
  }
  if (failed) {
    return <InlineAlert title="视频文件打不开" tone="danger">文件可能被移动或删除，请重新上传。</InlineAlert>;
  }
  return (
    <video
      aria-label={`视频预览：${media.file_name}`}
      // 短视频以竖屏为主：不锁 16:9、不铺满宽度，按成片自身比例显示并限高，避免两侧黑边
      className="mx-auto max-h-[min(60vh,520px)] max-w-full rounded-md bg-ink"
      controls
      onError={() => setFailed(true)}
      playsInline
      preload="metadata"
      src={`/api/media/${encodeURIComponent(media.id)}/content`}
    >
      当前浏览器无法播放这个视频。
    </video>
  );
}

function MediaSection({ view }: { view: VideoView }) {
  const script = view.video.scripts.at(-1);
  const media = view.video.media.at(-1);
  return (
    <div className="grid gap-4">
      <section className="border-b border-border pb-4">
        <h3 className="m-0 text-sm font-semibold">脚本摘要</h3>
        <p className="mb-0 mt-2 line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-ink-soft">
          {script ? cleanScriptContent(script.content) : "还没有脚本。先去「脚本」那一步写好。"}
        </p>
      </section>
      <ScriptQualityPanel claimsNeedingEvidence={script?.claims_needing_evidence} claimsUsed={script?.claims_used} quality={script?.quality} />
      {media ? (
        <section className="grid gap-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="m-0 text-sm font-semibold">当前视频</h3>
              {/* 文件名可能是一长串不可断行的导出编号，必须折行：nowrap 会把整列撑宽并顶破抽屉 */}
              <p className="mb-0 mt-1 break-all text-sm text-ink-soft">{media.file_name}</p>
            </div>
            <Badge tone="success">已上传</Badge>
          </div>
          <MediaPreview media={media} />
          <p className="m-0 text-xs text-ink-muted">
            {(media.size_bytes / 1024 / 1024).toFixed(1)} MB · {formatDate(media.created_at)}
          </p>
        </section>
      ) : (
        <InlineAlert title="还没有视频" tone="info">
          点上面的「上传视频」，把拍好的视频传上来。
        </InlineAlert>
      )}
    </div>
  );
}

function PublicationCard({ publication, workspace, onChanged }: { publication: Publication; workspace: Workspace; onChanged: () => Promise<void> }) {
  const account = workspace.accounts.find((item) => item.id === publication.account_id);
  const statusCopy = PUBLICATION_EVENT_COPY[publication.status].summary;
  return <article className="grid gap-3 rounded-md border border-border p-3"><div className="flex items-start gap-2"><div className="min-w-0 flex-1"><p className="m-0 text-sm font-semibold">{accountLabel(account)}</p><p className="mb-0 mt-1 text-xs text-ink-muted">{platformCopy(account?.platform)} · {formatDate(publication.scheduled_at ?? publication.published_at)}</p></div><Badge tone={publication.status.includes("succeeded") ? "success" : publication.status === "failed" || publication.status === "unknown" ? "danger" : "info"}>{statusCopy}</Badge></div>{publication.url ? <a className="text-sm text-brand hover:underline" href={publication.url} rel="noreferrer" target="_blank">查看平台视频</a> : null}{publication.error ? <InlineAlert title="没发出去的原因" tone="danger">{publicationMessage(publication.error)}</InlineAlert> : null}{publication.warnings.map((warning) => <InlineAlert key={warning} title="平台提示" tone="warning">{publicationMessage(warning)}</InlineAlert>)}<PublicationControl account={account} onCompleted={onChanged} publication={publication} /></article>;
}

function DataSection({ view, workspace }: { view: VideoView; workspace: Workspace }) {
  const published = view.video.publications.filter((item) => item.external_id);
  if (!published.length) {
    return (
      <InlineAlert title="还没有数据" tone="info">
        视频发出去以后，播放量、订单和评论会自动出现在这里。
      </InlineAlert>
    );
  }
  return (
    <div className="grid gap-3">
      {published.map((publication) => {
        const account = workspace.accounts.find((item) => item.id === publication.account_id);
        const metric = latestMetric(publication);
        const snapshots = [...publication.metrics].sort((a, b) =>
          a.captured_at.localeCompare(b.captured_at),
        );
        return (
          <article className="rounded-md border border-border p-3" key={publication.id}>
            <div className="mb-3 flex items-center justify-between gap-2">
              <p className="m-0 text-sm font-semibold">{accountLabel(account)}</p>
              {snapshots.length ? <Badge>{snapshots.length} 个时间点</Badge> : null}
            </div>
            {snapshots.length ? (
              <>
                <div className="grid grid-cols-3 gap-3">
                  <MetricValue label="播放" value={formatNumber(metric?.views ?? null)} />
                  <MetricValue label="订单" value={formatNumber(metric?.orders ?? null)} />
                  <MetricValue label="成交额" value={formatMoney(metric?.revenue ?? null)} />
                </div>
                <ol className="mb-0 mt-3 grid list-none gap-1 border-t border-border pt-3 pl-0">
                  {snapshots.map((snapshot) => (
                    <li className="flex items-center gap-2 text-xs text-ink-muted" key={snapshot.id}>
                      <time>{formatDate(snapshot.captured_at)}</time>
                      <span className="ml-auto tabular-nums">{formatNumber(snapshot.views)} 播放</span>
                      <span className="tabular-nums">{formatNumber(snapshot.orders)} 单</span>
                    </li>
                  ))}
                </ol>
              </>
            ) : (
              <p className="m-0 text-sm leading-6 text-ink-muted">已发布，还没拿到第一批数据。点「同步数据」可以马上查一次。</p>
            )}
            {publication.comments.slice(0, 3).map((comment) => (
              <blockquote
                className="mx-0 mb-0 mt-2 border-l-2 border-border pl-3 text-sm text-ink-soft"
                key={comment.id}
              >
                {comment.content}
                <footer className="mt-1 text-xs text-ink-muted">
                  {comment.author} · {comment.likes} 赞
                </footer>
              </blockquote>
            ))}
          </article>
        );
      })}
    </div>
  );
}

function MetricValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="m-0 text-xs text-ink-muted">{label}</p>
      <p className="mb-0 mt-1 font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function LineageSection({ view, workspace }: { view: VideoView; workspace: Workspace }) {
  const parent = workspace.videos.find((item) => item.video.id === view.video.parent_video_id);
  const children = workspace.videos.filter((item) => item.video.parent_video_id === view.video.id);
  return <div className="grid gap-3">{parent ? <div className="rounded-md border border-border p-3"><p className="m-0 text-xs font-semibold text-ink-muted">照着做的原视频</p><p className="mb-0 mt-1 text-sm font-semibold">{parent.video.title}</p><p className="mb-0 mt-1 text-sm text-ink-soft">这版改了什么：{view.video.variation_note}</p></div> : <InlineAlert title="这是第一版" tone="info">之前没照着别的视频改。想再做，点「再做一版」。</InlineAlert>}{children.map((child) => <div className="rounded-md border border-border p-3" key={child.video.id}><p className="m-0 text-xs font-semibold text-ink-muted">从这条改出来的新版</p><p className="mb-0 mt-1 text-sm font-semibold">{child.video.title}</p><p className="mb-0 mt-1 text-sm text-ink-soft">这版改了什么：{child.video.variation_note}</p></div>)}{!children.length ? <p className="m-0 text-sm text-ink-muted">还没有从这条改出来的新版。</p> : null}</div>;
}

type DrawerTab = Exclude<VideoDetailTab, "current">;
type DialogKey = "artifact" | "upload" | "publish" | "lineage";
type DrawerStageState = "done" | "active" | "pending" | "failed";

const DRAWER_PHASES = [
  { key: "script", label: "脚本", icon: FileText },
  { key: "media", label: "视频", icon: VideoIcon },
  { key: "publish", label: "发布", icon: Send },
] as const;

const STAGE_STEP: Record<VideoStage, number> = {
  needs_script: 0,
  needs_media: 1,
  ready_to_publish: 2,
  publishing: 2,
  scheduled: 2,
  publish_failed: 2,
  needs_reconciliation: 2,
  published: 2,
};

function currentTab(view: VideoView, requestedTab: VideoDetailTab): DrawerTab {
  if (requestedTab !== "current") return requestedTab;
  return DRAWER_PHASES[STAGE_STEP[view.stage.stage]].key;
}

function drawerStageState(view: VideoView, phase: DrawerTab): DrawerStageState {
  const completed = {
    script: view.video.scripts.length > 0 && view.video.storyboards.length > 0,
    media: view.video.media.length > 0,
    publish: view.video.publications.some((item) => ["succeeded", "succeeded_with_warnings"].includes(item.status)),
  };
  if (completed[phase]) return "done";
  if (phase === "publish" && ["publish_failed", "needs_reconciliation"].includes(view.stage.stage)) return "failed";
  return DRAWER_PHASES[STAGE_STEP[view.stage.stage]].key === phase ? "active" : "pending";
}

const DRAWER_STAGE_STYLE: Record<DrawerStageState, string> = {
  done: "border-success bg-success text-white",
  active: "border-brand bg-brand-soft text-brand",
  failed: "border-danger bg-danger text-white",
  pending: "border-border-strong bg-surface text-ink-muted",
};

const DRAWER_STAGE_COPY: Record<DrawerStageState, string> = {
  done: "已完成，可回看",
  active: "当前步骤",
  failed: "需要处理",
  pending: "未开始",
};

function StageTabs({ view }: { view: VideoView }) {
  return <TabsList aria-label="视频阶段" className="grid w-full grid-cols-3 gap-1"><>{DRAWER_PHASES.map((phase) => {
    const state = drawerStageState(view, phase.key);
    const Icon = state === "done" ? Check : phase.icon;
    return <TabsTrigger aria-description={DRAWER_STAGE_COPY[state]} aria-label={phase.label} className="min-h-11 gap-1.5 px-2 text-xs disabled:cursor-default disabled:opacity-55 sm:min-h-10 sm:text-sm" disabled={state === "pending"} key={phase.key} value={phase.key}><span className={cn("grid size-6 place-items-center rounded-full border", DRAWER_STAGE_STYLE[state])}><Icon aria-hidden="true" className="size-3.5" /></span><span>{phase.label}</span></TabsTrigger>;
  })}</></TabsList>;
}

interface DrawerAction { label: string; dialog?: DialogKey; target?: DrawerTab }

function actionForTab(view: VideoView, tab: DrawerTab): DrawerAction | null {
  if (tab === "script") return { label: view.video.scripts.length ? "编辑脚本" : "写脚本", dialog: "artifact" };
  if (tab === "media") return { label: view.video.media.length ? "替换视频" : "上传视频", dialog: "upload" };
  if (!view.video.media.length) return { label: "先上传视频", target: "media" };
  if (["publishing", "scheduled", "publish_failed", "needs_reconciliation"].includes(view.stage.stage)) return null;
  return { label: view.video.publications.length ? "安排新发布" : "安排发布", dialog: "publish" };
}

function MoreActions({ primary, onOpen }: { primary: DialogKey | null; onOpen: (dialog: DialogKey) => void }) {
  const actions = [
    { key: "artifact" as const, label: "编辑脚本", icon: FileEdit },
    { key: "upload" as const, label: "上传或替换视频", icon: Upload },
    { key: "publish" as const, label: "安排发布", icon: CalendarPlus },
    { key: "lineage" as const, label: "再做一版", icon: GitBranch },
  ].filter((action) => action.key !== primary);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button aria-label="更多操作" className="min-h-11 sm:min-h-9" size="sm" variant="secondary">
          <MoreHorizontal className="size-4" />更多
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {actions.map((action) => (
          <DropdownMenuItem className="min-h-11 sm:min-h-9" key={action.key} onSelect={() => onOpen(action.key)}>
            <action.icon className="size-4" />{action.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

interface Props { view: VideoView; workspace: Workspace; activeTab: VideoDetailTab; open: boolean; onOpenChange: (open: boolean) => void; onTabChange: (tab: VideoDetailTab) => void; onChanged: () => Promise<void> }

export function VideoDrawer({ view, workspace, activeTab, open, onOpenChange, onTabChange, onChanged }: Props) {
  const [dialog, setDialog] = useState<DialogKey | null>(null);
  const events = useMemo(() => runEvents(view), [view]);
  const selectedTab = currentTab(view, activeTab);
  const action = actionForTab(view, selectedTab);
  const chooseTab = (tab: DrawerTab) => onTabChange(tab);
  const runPrimary = () => {
    if (action?.dialog) setDialog(action.dialog);
    else if (action?.target) chooseTab(action.target);
  };
  return <><DetailDrawer description={drawerSubtitle(view)} onOpenChange={onOpenChange} open={open} title={view.video.title}><div className="grid gap-4"><Tabs onValueChange={(value) => chooseTab(value as DrawerTab)} value={selectedTab}><StageTabs view={view} /><div className="mt-3 flex items-center justify-end gap-2">{action ? <Button className="min-h-11 flex-1 sm:min-h-9 sm:flex-none" onClick={runPrimary} size="sm">{action.label}</Button> : null}<MoreActions onOpen={setDialog} primary={action?.dialog ?? null} /></div><TabsContent value="script"><ArtifactsSection onChanged={onChanged} view={view} /></TabsContent><TabsContent value="media"><MediaSection view={view} /></TabsContent><TabsContent value="publish"><div className="grid gap-5"><section><h3 className="mb-3 mt-0 text-sm font-semibold">发布记录</h3><div className="grid gap-3">{view.video.publications.map((publication) => <PublicationCard key={publication.id} onChanged={onChanged} publication={publication} workspace={workspace} />)}{!view.video.publications.length ? <InlineAlert title="还没有发布记录" tone="info">点上面的「安排发布」，把视频发出去。</InlineAlert> : null}</div></section><section className="border-t border-border pt-4"><h3 className="mb-3 mt-0 text-sm font-semibold">播放数据</h3><DataSection view={view} workspace={workspace} /></section></div></TabsContent></Tabs><details className="border-t border-border pt-2"><summary className="flex min-h-11 cursor-pointer items-center text-sm font-semibold text-ink-soft">更多信息</summary><div className="grid gap-5 pb-2 pt-3"><section><h3 className="mb-3 mt-0 text-sm font-semibold">目标与素材</h3><ContextSection view={view} /></section><section className="border-t border-border pt-4"><h3 className="mb-3 mt-0 text-sm font-semibold">视频关系</h3><LineageSection view={view} workspace={workspace} /></section><section className="border-t border-border pt-4"><h3 className="mb-3 mt-0 text-sm font-semibold">操作记录</h3><RunTimeline events={events} /></section></div></details></div></DetailDrawer><ArtifactDialog onCompleted={onChanged} onOpenChange={(value) => setDialog(value ? "artifact" : null)} open={dialog === "artifact"} producer={activeScriptProducer(workspace)} video={view.video} /><UploadDialog onCompleted={onChanged} onOpenChange={(value) => setDialog(value ? "upload" : null)} open={dialog === "upload"} video={view.video} /><PublishDialog onCompleted={onChanged} onOpenChange={(value) => setDialog(value ? "publish" : null)} open={dialog === "publish"} video={view.video} workspace={workspace} /><LineageDialog onCompleted={onChanged} onOpenChange={(value) => setDialog(value ? "lineage" : null)} open={dialog === "lineage"} performanceBrief={view.performance_brief} video={view.video} /></>;
}
