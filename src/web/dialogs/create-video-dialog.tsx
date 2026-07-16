import {
  Button,
  Dialog,
  DialogContent,
  Field,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from "@fifty/workbench-ui";
import { FormEvent, useState } from "react";
import { api, ApiError } from "../api";
import type { Video, Workspace } from "../domain";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspace: Workspace;
  onCreated: (video: Video) => Promise<void>;
  onCompleted: (videoId: string) => Promise<void>;
}

interface FormProps extends Omit<Props, "open" | "onOpenChange"> {
  onClose: () => void;
}

function ImportScriptForm({ workspace, onCreated, onCompleted, onClose }: FormProps) {
  const [title, setTitle] = useState("");
  const [productId, setProductId] = useState("none");
  const [script, setScript] = useState("");
  const [referenceUrl, setReferenceUrl] = useState("");
  const [createdVideoId, setCreatedVideoId] = useState<string>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();

  const createRecord = async () => {
    const video = await api.createVideo({
      title,
      goal: "把已有脚本做成视频并发布",
      account_ids: [],
      product_id: productId === "none" ? null : productId,
      brief: "导入已有脚本",
      sources: referenceUrl.trim()
        ? [{ kind: "video", label: "参考视频", content: "", href: referenceUrl.trim() }]
        : [],
    });
    setCreatedVideoId(video.id);
    await onCreated(video);
    return video.id;
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setPending(true);
    setError(undefined);
    let videoId = createdVideoId;
    try {
      videoId = videoId ?? await createRecord();
      await api.importArtifacts(videoId, script);
      onClose();
      await onCompleted(videoId);
    } catch (cause) {
      const reason = cause instanceof ApiError ? cause.message : "请稍后重试。";
      setError(videoId
        ? `视频已建立，但脚本没有导入：${reason} 再次提交不会重复建视频。`
        : `脚本没有导入：${reason}`);
    } finally {
      setPending(false);
    }
  };

  return <form className="grid gap-5" onSubmit={(event) => void submit(event)}><Field htmlFor="import-video-title" label="视频标题" required><Input autoFocus id="import-video-title" maxLength={100} onChange={(event) => setTitle(event.target.value)} placeholder="例：租房浴室别再打孔了" required value={title} /></Field><Field htmlFor="import-product" label="商品" hint="可不选"><Select onValueChange={setProductId} value={productId}><SelectTrigger id="import-product"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">不选商品</SelectItem>{workspace.products.map((product) => <SelectItem key={product.id} value={product.id}>{product.title}</SelectItem>)}</SelectContent></Select></Field><Field htmlFor="import-script" label="脚本正文" required><Textarea className="min-h-48" id="import-script" onChange={(event) => setScript(event.target.value)} placeholder="把写好的脚本粘贴进来…" required value={script} /></Field><Field htmlFor="import-reference" label="参考视频" hint="可选"><Input id="import-reference" onChange={(event) => setReferenceUrl(event.target.value)} placeholder="贴一条参考视频的链接" type="url" value={referenceUrl} /></Field>{error ? <p className="m-0 text-sm leading-5 text-danger" role="alert">{error}</p> : null}<div className="flex justify-end gap-2"><Button onClick={onClose} type="button" variant="secondary">{createdVideoId ? "关闭" : "取消"}</Button><Button loading={pending} loadingLabel={createdVideoId ? "正在重试" : "正在导入"} type="submit">{createdVideoId ? "重试导入" : "导入并进入成片"}</Button></div></form>;
}

export function CreateVideoDialog({ open, onOpenChange, workspace, onCreated, onCompleted }: Props) {
  return <Dialog onOpenChange={onOpenChange} open={open}><DialogContent className="w-[min(640px,calc(100vw-32px))]" description="脚本已经写好了，直接拿来做视频，不用再填风格要求和账号。" title="导入已有脚本">{open ? <ImportScriptForm onClose={() => onOpenChange(false)} onCompleted={onCompleted} onCreated={onCreated} workspace={workspace} /> : null}</DialogContent></Dialog>;
}
