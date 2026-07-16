import { Button, Dialog, DialogContent, FileDropzone, InlineAlert } from "@fifty/workbench-ui";
import { FileVideo2 } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "../../api";
import type { Video } from "../../domain";

export function UploadDialog({ video, open, onOpenChange, onCompleted }: { video: Video; open: boolean; onOpenChange: (open: boolean) => void; onCompleted: () => Promise<void> }) {
  const [file, setFile] = useState<File>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();

  const upload = async () => {
    if (!file) return;
    setPending(true); setError(undefined);
    try { await api.uploadMedia(video.id, file); await onCompleted(); onOpenChange(false); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "上传失败，请重试。"); }
    finally { setPending(false); }
  };

  return <Dialog onOpenChange={onOpenChange} open={open}><DialogContent description="这条视频不管是商家给的、剪辑做的，还是 AI 生成的，做好后都传到这里。" title={`${video.title} · 上传视频`}><div className="grid gap-4"><FileDropzone accept="video/*" disabled={pending} onFiles={(files) => setFile(files[0])} />{file ? <div className="flex items-center gap-3 rounded-md border border-border bg-surface-muted p-3"><FileVideo2 className="size-5 text-brand" /><div className="min-w-0"><p className="m-0 truncate text-sm font-semibold text-ink">{file.name}</p><p className="mb-0 mt-0.5 text-xs text-ink-muted">{(file.size / 1024 / 1024).toFixed(1)} MB · {file.type || "video"}</p></div></div> : null}{error ? <InlineAlert title="上传未完成" tone="danger">{error}</InlineAlert> : null}<div className="flex justify-end gap-2"><Button onClick={() => onOpenChange(false)} variant="secondary">取消</Button><Button disabled={!file} loading={pending} loadingLabel="上传中" onClick={() => void upload()}>确认上传</Button></div></div></DialogContent></Dialog>;
}
