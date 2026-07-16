import { Button, EmptyState } from "@fifty/workbench-ui";
import { Clapperboard } from "lucide-react";
import { useState } from "react";
import { UploadDialog } from "../../dialogs/media/upload-dialog";
import type { ScriptArtifact, Video, Workspace } from "../../domain";
import { buildPipelineNodes } from "../pipeline-model";
import type { PanelProps } from "./types";

// ============================================================
// 「成片」面板：待成片清单，一行一条——标题、脚本首句、一个动作。
//
// 待成片 = 脚本分镜齐了、还没有成片（口径在后端 domain/states.py，界面不维护第二套）。
// 上传成功后这条转入「待发布」，自己从清单里消失。
// 读全文、看竖屏预览是详情抽屉的事：这里只回答「该拍哪条」。
// ============================================================

function latestScript(video: Video): ScriptArtifact | undefined {
  return video.scripts.reduce<ScriptArtifact | undefined>((latest, item) => !latest || item.version > latest.version ? item : latest, undefined);
}

/** 脚本首句：跳过 markdown 标题与「【样例生成】」这类标注，取正文第一句 */
function firstSentence(content: string): string {
  const line = content.split(/\r?\n/)
    .map((item) => item.trim())
    .find((item) => item && !/^#{1,6}\s+/.test(item) && !/^【(?:样例生成|模拟输出)[^】]*】$/.test(item));
  const body = (line ?? "").replace(/^#{1,6}\s+/, "").replace(/\s+/g, " ");
  const end = body.search(/[。！？!?]/);
  return end === -1 ? body : body.slice(0, end + 1);
}

/** 空态说清为什么空、下一步在哪个节点——不写「暂无数据」 */
function emptyCopy(workspace: Workspace): { title: string; description: string } {
  // 上游还有多少条待选脚本：复用画布的计数，不在这儿算第二遍
  const waiting = buildPipelineNodes(workspace).find((node) => node.id === "pick")?.count ?? 0;
  if (waiting > 0) return {
    title: "还没有要拍的视频",
    description: `还有 ${waiting} 条脚本在「选稿」等你挑，挑中的会排到这里等着拍。`,
  };
  const shot = workspace.videos.filter((view) => view.video.media.length > 0).length;
  if (shot > 0) return {
    title: "视频都上齐了",
    description: `${shot} 条视频都传好了，接着去「发布」安排发布时间。`,
  };
  return {
    title: "还没开始做视频",
    description: "先从「这批想做什么」开始，经过「生成脚本」「选稿」，要拍的视频就会排到这里。",
  };
}

interface RowProps {
  video: Video;
  onOpen: () => void;
  onUpload: () => void;
}

function MediaRow({ video, onOpen, onUpload }: RowProps) {
  const preview = firstSentence(latestScript(video)?.content ?? "");
  return <li className="flex items-center gap-3 py-3 pl-4 pr-3">
    <div className="min-w-0 flex-1">
      <button
        aria-label={`打开视频：${video.title}`}
        className="block min-h-11 w-full cursor-pointer truncate rounded-sm text-left text-sm font-semibold leading-5 text-ink outline-none transition-colors hover:text-brand focus-visible:ring-2 focus-visible:ring-focus sm:min-h-5"
        onClick={onOpen}
        title={video.title}
        type="button"
      >
        <span>{video.title}</span>
      </button>
      <p className="mb-0 mt-0.5 line-clamp-1 break-all text-[13px] leading-5 text-ink-soft" title={preview || undefined}>
        {preview || "这条还没写正文，点标题去看详情。"}
      </p>
    </div>
    <Button aria-label={`上传视频：${video.title}`} className="shrink-0" onClick={onUpload} size="sm" variant="secondary">上传视频</Button>
  </li>;
}

export function MediaPanel({ workspace, onChanged, onOpenVideo, onClose }: PanelProps) {
  const [target, setTarget] = useState<Video>();
  const pending = workspace.videos.filter((view) => view.stage.stage === "needs_media").map((view) => view.video);

  if (!pending.length) {
    const copy = emptyCopy(workspace);
    return <EmptyState action={{ label: "回到流程图", onClick: onClose }} description={copy.description} icon={Clapperboard} title={copy.title} />;
  }

  return <div className="grid gap-4">
    <p className="m-0 text-[13px] leading-5 text-ink-soft">{pending.length} 条脚本都写好了，就等你上传视频。上传后这条就去排发布。</p>
    <ul className="m-0 grid list-none divide-y divide-border rounded-[14px] border border-border bg-surface p-0">
      {pending.map((video) => <MediaRow
        key={video.id}
        onOpen={() => onOpenVideo(video.id, "media")}
        onUpload={() => setTarget(video)}
        video={video}
      />)}
    </ul>
    {target ? <UploadDialog
      key={target.id}
      onCompleted={onChanged}
      onOpenChange={(next) => { if (!next) setTarget(undefined); }}
      open
      video={target}
    /> : null}
  </div>;
}
