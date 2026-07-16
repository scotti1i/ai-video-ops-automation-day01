import { Badge, Button, Dialog, DialogContent, FileDropzone, InlineAlert, toast } from "@fifty/workbench-ui";
import { FileText } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "../api";
import type { ImportFormat, ImportPreview, ImportPreviewRow } from "../domain";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCompleted: () => Promise<void>;
}

function readTextFile(file: File): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

function PreviewSummary({ preview }: { preview: ImportPreview }) {
  const { summary } = preview;
  return <section aria-label="导入预览汇总" className="grid gap-3 rounded-md border border-border bg-surface-muted p-3"><div className="flex flex-wrap gap-2"><Badge>{summary.total} 条视频</Badge><Badge tone="success">{summary.ready} 条可导入</Badge><Badge tone="warning">{summary.conflict} 条已存在</Badge><Badge tone={summary.invalid ? "danger" : "neutral"}>{summary.invalid} 条需修正</Badge></div>{summary.missing_references ? <p className="m-0 text-xs text-danger">{summary.missing_references} 行用到的账号、商品或原视频找不到，请先补齐再导入。</p> : null}<RowReports rows={preview.rows} /></section>;
}

function RowReports({ rows }: { rows: ImportPreviewRow[] }) {
  const reported = rows.filter((row) => row.status !== "ready").slice(0, 6);
  if (!reported.length) return <p className="m-0 text-xs text-ink-muted">检查通过，导入后只会新增视频，不会改动已有的。</p>;
  return <ul className="m-0 grid max-h-44 gap-2 overflow-auto p-0" aria-label="有问题的行"><>{reported.map((row) => <li className="list-none rounded-md border border-border bg-surface px-3 py-2 text-xs" key={row.row_number}><div className="flex items-center justify-between gap-3"><span className="truncate font-semibold text-ink">第 {row.row_number} 行 · {row.normalized.title || "未命名"}</span><Badge tone={row.status === "invalid" ? "danger" : "warning"}>{row.status === "invalid" ? "需修正" : "已存在"}</Badge></div><p className="mb-0 mt-1 text-ink-muted">{[...row.conflicts, ...row.errors].join("；")}</p></li>)}</></ul>;
}

function ImportForm({ onClose, onCompleted }: { onClose: () => void; onCompleted: () => Promise<void> }) {
  const [fileName, setFileName] = useState("");
  const [format, setFormat] = useState<ImportFormat>("json");
  const [payload, setPayload] = useState("");
  const [preview, setPreview] = useState<ImportPreview>();
  const [pending, setPending] = useState<"preview" | "commit">();
  const [error, setError] = useState<string>();

  const read = async (files: File[]) => {
    const file = files[0];
    if (!file) return;
    if (file.size > 5_000_000) { setError("文件超过 5 MB，请拆分后再导入。"); return; }
    try {
      setPayload(await readTextFile(file));
      setFileName(file.name);
      setFormat(file.name.toLowerCase().endsWith(".csv") ? "csv" : "json");
      setPreview(undefined); setError(undefined);
    } catch { setError("文件读取失败，请重新选择。"); }
  };

  const inspect = async () => {
    setPending("preview"); setError(undefined);
    try { setPreview(await api.previewImport(format, payload)); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "无法预览这个文件。"); }
    finally { setPending(undefined); }
  };

  const commit = async () => {
    setPending("commit"); setError(undefined);
    try {
      const result = await api.commitImport(format, payload);
      await onCompleted(); onClose();
      toast.success(`已导入 ${result.created.length} 条视频，${result.skipped.length} 条保持不变`);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "导入未完成。"); }
    finally { setPending(undefined); }
  };

  return <div className="grid gap-4"><FileDropzone accept=".json,.csv,application/json,text/csv" disabled={Boolean(pending)} onFiles={(files) => void read(files)} />{fileName ? <div className="flex items-center gap-2 rounded-md border border-border bg-surface-muted px-3 py-2 text-sm"><FileText className="size-4 text-brand" /><span className="min-w-0 truncate font-semibold">{fileName}</span><Badge>{format.toUpperCase()}</Badge></div> : null}<p className="m-0 text-xs leading-5 text-ink-muted">只接受从本平台导出的视频文件（JSON 或 CSV）。导入前会自动查重，并提示找不到的账号、商品或原视频；重复导入不会覆盖已有的脚本、镜头和发布记录。</p>{preview ? <PreviewSummary preview={preview} /> : null}{error ? <InlineAlert title="文件没通过检查" tone="danger">{error}</InlineAlert> : null}<div className="flex justify-end gap-2"><Button onClick={onClose} type="button" variant="secondary">取消</Button><Button disabled={!payload} loading={pending === "preview"} loadingLabel="检查中" onClick={() => void inspect()} type="button" variant="secondary">预览</Button><Button disabled={!preview?.summary.ready} loading={pending === "commit"} loadingLabel="导入中" onClick={() => void commit()} type="button">导入 {preview?.summary.ready ?? 0} 条</Button></div></div>;
}

export function WorkspaceImportDialog({ open, onOpenChange, onCompleted }: Props) {
  return <Dialog onOpenChange={onOpenChange} open={open}><DialogContent description="先自动检查一遍，确认没问题，再把视频导入进来。" title="批量导入视频">{open ? <ImportForm onClose={() => onOpenChange(false)} onCompleted={onCompleted} /> : null}</DialogContent></Dialog>;
}
