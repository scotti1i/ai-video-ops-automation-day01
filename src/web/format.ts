import type { Account, Publication } from "./domain";

export function formatDate(value: string | null, withTime = true): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

export function formatNumber(value: number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("zh-CN", { notation: value > 9999 ? "compact" : "standard" }).format(value);
}

export function formatMoney(value: number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

export function latestMetric(publication: Publication) {
  return [...publication.metrics].sort((a, b) => b.captured_at.localeCompare(a.captured_at))[0];
}

export function accountLabel(account: Account | undefined): string {
  return account ? `${account.name} ${account.handle}` : "未知账号";
}

/**
 * 表现文案的人话映射（design-v7-canvas.md 术语表）。
 * 「待观察」是后端 performance.label 的原文，不改后端：口径是后端的，说法是界面的。
 */
const PERFORMANCE_COPY: Record<string, string> = { 待观察: "数据还没起来" };

export function performanceLabel(label: string): string {
  return PERFORMANCE_COPY[label] ?? label;
}

export function toLocalDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}
