import { Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger, InlineAlert, Skeleton, Toaster, toast } from "@fifty/workbench-ui";
import { Download, FileInput, MoreHorizontal, Plug, RefreshCw, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "./api";
import { ConnectorsPanel } from "./canvas/panels/connectors-panel";
import { PipelineCanvas } from "./canvas/pipeline-canvas";
import { VideoDrawer } from "./components/video-drawer";
import { CreateVideoDialog } from "./dialogs/create-video-dialog";
import { WorkspaceImportDialog } from "./dialogs/workspace-import-dialog";
import type { Video, VideoDetailTab, Workspace } from "./domain";

// ============================================================
// 首页 = 画布（design-v7-canvas.md：画布即产品，画布即导航）
//
// 没有侧栏、没有四个一级入口：账号 / 商品 / 发布日历都并进了对应节点的面板，
// 视频清单由画布徽章 + 各面板的「看这一条」代替。顶栏只剩产品身份与低频操作。
// ============================================================

/**
 * 唯一的深链：#video/<id> 直接打开单条详情（用于飞书里贴一条视频）。
 * 画布自己没有 hash——它就是首页，没有第二个地方可去。
 */
const VIDEO_HASH = /^#video\/(.+)$/;

function videoIdFromHash(): string | undefined {
  const match = VIDEO_HASH.exec(window.location.hash);
  return match ? decodeURIComponent(match[1]) : undefined;
}

function useWorkspaceState() {
  const [workspace, setWorkspace] = useState<Workspace>();
  const [error, setError] = useState<string>();
  const [refreshing, setRefreshing] = useState(false);
  const reload = useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true);
    try { setWorkspace(await api.workspace()); setError(undefined); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "无法连接工作台服务。"); }
    finally { if (!silent) setRefreshing(false); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => {
    const publishing = workspace?.videos.some((item) => item.video.publications.some((publication) => publication.status === "publishing"));
    if (!publishing) return undefined;
    const timer = window.setInterval(() => { void reload(true); }, 2_500);
    return () => window.clearInterval(timer);
  }, [reload, workspace]);
  return { workspace, error, refreshing, reload };
}

function LoadingView() {
  return <div className="grid gap-3 p-4 sm:p-6"><Skeleton className="h-24 w-full" /><Skeleton className="h-80 w-full" /></div>;
}

interface ProductHeaderProps {
  ready: boolean;
  refreshing: boolean;
  onConnectors: () => void;
  onCreate: () => void;
  onImport: () => void;
  onRefresh: () => void;
}

function ProductHeader({ ready, refreshing, onConnectors, onCreate, onImport, onRefresh }: ProductHeaderProps) {
  return <div className="flex min-h-16 items-center gap-3 px-4 sm:px-5"><div className="min-w-0 flex-1"><h1 className="m-0 truncate text-[15px] font-semibold tracking-[-0.01em] text-ink sm:text-base">视频闭环生产平台</h1><p className="mb-0 mt-0.5 text-xs font-medium text-ink-muted">零密钥样例工作台</p></div><DropdownMenu><DropdownMenuTrigger asChild><Button aria-label="更多操作" className="size-11 shrink-0 px-0 sm:size-10" variant="quiet"><MoreHorizontal aria-hidden="true" className="size-5" /></Button></DropdownMenuTrigger><DropdownMenuContent align="end" className="w-60"><DropdownMenuItem onSelect={onConnectors}><Plug aria-hidden="true" className="size-4 text-ink-muted" />连接与配置</DropdownMenuItem><DropdownMenuSeparator /><DropdownMenuItem disabled={!ready} onSelect={onCreate}><FileInput aria-hidden="true" className="size-4 text-ink-muted" />导入已有脚本</DropdownMenuItem><DropdownMenuItem disabled={!ready} onSelect={onImport}><Upload aria-hidden="true" className="size-4 text-ink-muted" />批量导入视频</DropdownMenuItem><DropdownMenuSeparator /><DropdownMenuItem asChild><a download href="/api/exports/videos.json"><Download aria-hidden="true" className="size-4 text-ink-muted" />导出视频数据（JSON）</a></DropdownMenuItem><DropdownMenuItem asChild><a download href="/api/exports/videos.csv"><Download aria-hidden="true" className="size-4 text-ink-muted" />导出视频表格（CSV）</a></DropdownMenuItem><DropdownMenuItem asChild><a download href="/api/exports/workspace.json"><Download aria-hidden="true" className="size-4 text-ink-muted" />导出全部备份</a></DropdownMenuItem><DropdownMenuSeparator /><DropdownMenuItem disabled={refreshing} onSelect={onRefresh}><RefreshCw aria-hidden="true" className={refreshing ? "size-4 animate-spin" : "size-4 text-ink-muted"} />{refreshing ? "正在刷新" : "刷新数据"}</DropdownMenuItem></DropdownMenuContent></DropdownMenu></div>;
}

export function App() {
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [connectorsOpen, setConnectorsOpen] = useState(false);
  const [selectedVideoId, setSelectedVideoId] = useState<string | undefined>(videoIdFromHash);
  const [selectedVideoTab, setSelectedVideoTab] = useState<VideoDetailTab>("current");
  const { workspace, error, refreshing, reload } = useWorkspaceState();

  useEffect(() => {
    const next = selectedVideoId ? `#video/${encodeURIComponent(selectedVideoId)}` : "";
    if (window.location.hash !== next) window.location.hash = next;
  }, [selectedVideoId]);
  useEffect(() => {
    // 浏览器前进/后退：hash 变了就把详情状态同步回来。
    // 页签不在 hash 里，所以只在「退回画布」时才复位，免得覆盖 openVideo 指定的页签。
    const sync = () => {
      const next = videoIdFromHash();
      setSelectedVideoId(next);
      if (!next) setSelectedVideoTab("current");
    };
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  const closeVideo = () => { setSelectedVideoId(undefined); setSelectedVideoTab("current"); };
  const openVideo = (id: string, tab: VideoDetailTab = "current") => { setSelectedVideoId(id); setSelectedVideoTab(tab); };
  const refreshCreatedVideo = async (_video: Video) => { await reload(); };
  const completeCreatedVideo = async (videoId: string) => { await reload(); openVideo(videoId); toast.success("视频已加入工作台"); };
  const selected = workspace?.videos.find((item) => item.video.id === selectedVideoId);

  // 这里不用 AppShell：它的形状是「顶栏 + 侧栏 + 内容」，而 v7 把侧栏整个砍了。
  // 传个空侧栏只会剩一条 240px 白边和手机底部导航的占位。
  return <>
    <div className="min-h-svh bg-canvas text-ink">
      <header className="sticky top-0 z-30 border-b border-border bg-surface">
        <ProductHeader onConnectors={() => setConnectorsOpen(true)} onCreate={() => setCreateOpen(true)} onImport={() => setImportOpen(true)} onRefresh={() => void reload()} ready={Boolean(workspace)} refreshing={refreshing} />
      </header>
      <main>
        {error ? <div className="p-4 sm:p-6"><InlineAlert title="工作台暂不可用" tone="danger"><p className="m-0">{error}</p><Button className="mt-3" onClick={() => void reload()} size="sm" variant="secondary">重试</Button></InlineAlert></div> : null}
        {!workspace && !error ? <LoadingView /> : null}
        {workspace ? <PipelineCanvas onChanged={reload} onOpenVideo={openVideo} workspace={workspace} /> : null}
      </main>
    </div>
    <ConnectorsPanel onClose={() => setConnectorsOpen(false)} open={connectorsOpen} />
    {workspace ? <CreateVideoDialog onCompleted={completeCreatedVideo} onCreated={refreshCreatedVideo} onOpenChange={setCreateOpen} open={createOpen} workspace={workspace} /> : null}
    {workspace ? <WorkspaceImportDialog onCompleted={reload} onOpenChange={setImportOpen} open={importOpen} /> : null}
    {workspace && selected ? <VideoDrawer activeTab={selectedVideoTab} onChanged={reload} onOpenChange={(open) => { if (!open) closeVideo(); }} onTabChange={setSelectedVideoTab} open view={selected} workspace={workspace} /> : null}
    <Toaster position="top-right" richColors /></>;
}
