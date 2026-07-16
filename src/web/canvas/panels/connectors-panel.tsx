import { Badge, Button, Skeleton, toast } from "@fifty/workbench-ui";
import { Copy, Plug } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../../api";
import type { ConnectorItem, Connectors, ConnectorStatus, Tone } from "../../domain";
import { NodePanel } from "../node-panel";

// ============================================================
// 「连接与配置」：写脚本、发布、拉数据现在各接的是什么、怎么换。
// 从顶栏「更多操作」进来，不挂画布节点——NodePanel 无锚点时居中浮卡。
// 数据来自 GET /api/connectors，打开时现拉；失败给一句话 + 重试。
// ============================================================

const STATUS_PILL: Record<ConnectorStatus, { label: string; tone: Tone }> = {
  active: { label: "当前使用", tone: "brand" },
  ready: { label: "可用", tone: "success" },
  detected: { label: "已安装", tone: "success" },
  unconfigured: { label: "未配置", tone: "neutral" },
  missing: { label: "未安装", tone: "neutral" },
  contract: { label: "按接口接入", tone: "neutral" },
};

function copyHow(how: string) {
  navigator.clipboard?.writeText(how).then(
    () => toast.success("已复制"),
    () => toast.error("没复制上，手动选中命令再复制。"),
  );
}

/** 「怎么配」用按钮展开而不是 details/summary：命令是等宽原文，旁边给复制按钮 */
function HowToConfigure({ how, label }: { how: string; label: string }) {
  const [expanded, setExpanded] = useState(false);
  return <div className="grid gap-2">
    <button
      aria-expanded={expanded}
      className="justify-self-start rounded-sm text-[13px] font-medium text-brand outline-none hover:underline focus-visible:ring-2 focus-visible:ring-focus"
      onClick={() => setExpanded((value) => !value)}
      type="button"
    >{expanded ? "收起" : "怎么配"}</button>
    {expanded ? <>
      <pre className="m-0 overflow-x-auto rounded-md bg-surface-muted p-3 font-mono text-xs leading-5 text-ink">{how}</pre>
      <Button aria-label={`复制「${label}」的配置命令`} className="justify-self-start" onClick={() => copyHow(how)} size="sm" variant="secondary">
        <Copy aria-hidden="true" className="size-3.5" />复制
      </Button>
    </> : null}
  </div>;
}

function ConnectorRow({ item }: { item: ConnectorItem }) {
  const pill = STATUS_PILL[item.status];
  return <li className="grid gap-1.5 p-3">
    <div className="flex items-center gap-2">
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{item.label}</span>
      <Badge className="shrink-0" tone={pill.tone}>{pill.label}</Badge>
    </div>
    <p className="m-0 text-[13px] leading-5 text-ink-soft">{item.detail}</p>
    {item.how ? <HowToConfigure how={item.how} label={item.label} /> : null}
  </li>;
}

function ConnectorSection({ title, items }: { title: string; items: ConnectorItem[] }) {
  return <section aria-label={title} className="grid gap-2">
    <h3 className="m-0 text-[13px] font-semibold text-ink">{title}</h3>
    {items.length
      ? <ul className="m-0 grid list-none divide-y divide-border rounded-[10px] border border-border p-0">
        {items.map((item) => <ConnectorRow item={item} key={item.id} />)}
      </ul>
      : <p className="m-0 text-[13px] leading-5 text-ink-soft">这里还没有可以接的。</p>}
  </section>;
}

export interface ConnectorsPanelProps {
  open: boolean;
  onClose: () => void;
}

export function ConnectorsPanel({ open, onClose }: ConnectorsPanelProps) {
  const [connectors, setConnectors] = useState<Connectors>();
  const [error, setError] = useState<string>();
  const load = useCallback(async () => {
    setError(undefined);
    try { setConnectors(await api.fetchConnectors()); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "没拿到配置信息，请再试一次。"); }
  }, []);
  useEffect(() => { if (open) void load(); }, [open, load]);

  return <NodePanel
    description="写脚本、发布、拉数据都能换成你自己的——这里看现在接的是什么、怎么换"
    icon={Plug}
    onClose={onClose}
    open={open}
    title="连接与配置"
  >
    {error
      ? <div className="grid justify-items-start gap-3">
        <p className="m-0 text-[13px] leading-5 text-ink-soft" role="alert">{error}</p>
        <Button onClick={() => void load()} size="sm" variant="secondary">重试</Button>
      </div>
      : connectors
        ? <div className="grid gap-5">
          <ConnectorSection items={connectors.script.options} title="写脚本用什么" />
          <ConnectorSection items={connectors.publish.platforms} title="发布到哪" />
          <ConnectorSection items={connectors.data.items} title="数据怎么拉" />
        </div>
        : <div className="grid gap-3"><Skeleton className="h-20 w-full" /><Skeleton className="h-20 w-full" /><Skeleton className="h-20 w-full" /></div>}
  </NodePanel>;
}
