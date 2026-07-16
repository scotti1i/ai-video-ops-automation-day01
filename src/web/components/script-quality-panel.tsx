import { Badge, cn } from "@fifty/workbench-ui";
import { AlertTriangle, Check } from "lucide-react";
import type { ScriptQuality } from "../domain";

interface Props {
  quality?: ScriptQuality;
  claimsUsed?: string[];
  claimsNeedingEvidence?: string[];
}

export function ScriptQualityPanel({ quality, claimsUsed = [], claimsNeedingEvidence = [] }: Props) {
  if (!quality) return null;
  const passed = quality.checks.filter((check) => check.passed).length;
  const failed = quality.checks.filter((check) => !check.passed);
  const ready = quality.status === "ready_to_test";
  const Icon = ready ? Check : AlertTriangle;
  return <details className={cn("rounded-md border", ready ? "border-success/30 bg-success-soft" : "border-warning bg-warning-soft")} open={!ready}>
    <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm marker:hidden">
      <Icon aria-hidden className={cn("size-4 shrink-0", ready ? "text-success" : "text-warning")} />
      <Badge tone={ready ? "success" : "warning"}>{ready ? "可以拍了" : "还差证据"}</Badge>
      <span className="min-w-0 flex-1 truncate text-xs text-ink-soft">{ready ? "值得进入发布测试，不代表真实转化" : quality.risks[0] || "进入成片前仍有风险"}</span>
      <span className="shrink-0 text-xs font-semibold tabular-nums text-ink-muted">{passed}/{quality.checks.length} 项</span>
    </summary>
    <div className="grid gap-3 border-t border-current/10 px-3 pb-3 pt-2 text-xs leading-5 text-ink-soft">
      {failed.length ? <ul className="m-0 grid list-none gap-1 p-0">{failed.map((check) => <li className="flex gap-2" key={check.key}><AlertTriangle aria-hidden className="mt-1 size-3 shrink-0 text-warning" /><span><span className="font-semibold text-ink">{check.label}：</span>{check.detail}</span></li>)}</ul> : <p className="m-0">当前结构检查全部通过；是否有效仍以发布后的留存、点击和成交为准。</p>}
      {(claimsUsed.length || claimsNeedingEvidence.length) ? <div className="grid gap-1 border-t border-current/10 pt-2 sm:grid-cols-2"><p className="m-0"><span className="font-semibold text-ink">使用的商品事实：</span>{claimsUsed.length ? claimsUsed.join("、") : "未申报"}</p><p className="m-0"><span className="font-semibold text-ink">待补证据：</span>{claimsNeedingEvidence.length ? claimsNeedingEvidence.join("、") : "无"}</p></div> : null}
    </div>
  </details>;
}
