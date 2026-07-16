import { arrayMove, move } from "@dnd-kit/helpers";
import { Accessibility } from "@dnd-kit/dom";
import {
  DragDropProvider,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from "@dnd-kit/react";
import { useSortable } from "@dnd-kit/react/sortable";
import { cn, IconButton } from "@fifty/workbench-ui";
import { ArrowDown, ArrowUp, GripVertical, LockKeyhole } from "lucide-react";
import { useState } from "react";
import type { NarrativeBlock } from "../domain";

const blockCopy: Record<NarrativeBlock, { label: string; description: string }> = {
  problem: { label: "要解决的问题", description: "让观众一眼认出自己的问题" },
  proof: { label: "产品证明", description: "用能拍出来的画面，证明为什么值得买" },
  objection: { label: "打消顾虑", description: "回答下单前最可能犹豫的一件事" },
};

function blockLabel(id: unknown): string {
  return typeof id === "string" && id in blockCopy
    ? blockCopy[id as NarrativeBlock].label
    : "脚本环节";
}

const chineseAccessibility = Accessibility.configure({
  screenReaderInstructions: {
    draggable: "",
  },
  announcements: {
    dragstart: ({ operation: { source } }: DragStartEvent) => source
      ? `已拿起${blockLabel(source.id)}。`
      : undefined,
    dragover: ({ operation: { source, target } }: DragOverEvent) => {
      if (!source || source.id === target?.id) return undefined;
      return target
        ? `${blockLabel(source.id)}已移到${blockLabel(target.id)}的位置。`
        : `${blockLabel(source.id)}已离开可排序区域。`;
    },
    dragend: () => undefined,
  },
});

interface Props {
  value: NarrativeBlock[];
  onChange: (value: NarrativeBlock[]) => void;
}

function FixedNarrativeItem({ label, description }: { label: string; description: string }) {
  return <div className="flex min-h-14 items-center gap-3 rounded-md border border-border bg-surface-muted px-3"><LockKeyhole aria-hidden className="size-4 shrink-0 text-ink-muted" /><div className="min-w-0"><p className="m-0 text-sm font-semibold text-ink">{label}</p><p className="m-0 text-xs leading-5 text-ink-muted">{description}</p></div></div>;
}

interface SortableItemProps {
  block: NarrativeBlock;
  index: number;
  total: number;
  onMove: (from: number, to: number) => void;
}

function SortableNarrativeItem({ block, index, total, onMove }: SortableItemProps) {
  const { handleRef, isDragging, ref } = useSortable({ id: block, index, group: "narrative-middle", transition: { duration: 180 } });
  const copy = blockCopy[block];
  return <div className={cn("flex min-h-14 items-center gap-2 rounded-md border border-border-strong bg-surface px-1.5 py-1 transition-[border-color,box-shadow,opacity] duration-150", isDragging && "z-10 border-focus opacity-90 shadow-[var(--shadow-overlay)]")} data-narrative-block={block} ref={ref}><button aria-describedby="narrative-sort-instructions" aria-label={`拖动排序：${copy.label}`} aria-roledescription="可排序脚本环节" className="grid size-11 shrink-0 cursor-grab touch-none place-items-center rounded-md text-ink-muted outline-none hover:bg-surface-muted hover:text-ink active:cursor-grabbing focus-visible:ring-2 focus-visible:ring-focus" ref={handleRef} type="button"><GripVertical aria-hidden className="size-4" /></button><div className="min-w-0 flex-1"><p className="m-0 text-sm font-semibold text-ink">{copy.label}</p><p className="m-0 truncate text-xs leading-5 text-ink-muted">{copy.description}</p></div><div className="flex shrink-0"><IconButton aria-label={`上移 ${copy.label}`} className="size-11" disabled={index === 0} onClick={() => onMove(index, index - 1)} type="button"><ArrowUp aria-hidden className="size-4" /></IconButton><IconButton aria-label={`下移 ${copy.label}`} className="size-11" disabled={index === total - 1} onClick={() => onMove(index, index + 1)} type="button"><ArrowDown aria-hidden className="size-4" /></IconButton></div></div>;
}

export function SortableNarrativeList({ value, onChange }: Props) {
  const [announcement, setAnnouncement] = useState("");
  const reorder = (from: number, to: number) => {
    if (from === to || to < 0 || to >= value.length) return;
    const next = arrayMove(value, from, to);
    onChange(next);
    setAnnouncement(`${blockCopy[next[to]].label}已移到第 ${to + 1} 位`);
  };
  const onDragEnd = (event: DragEndEvent) => {
    if (event.canceled || !event.operation.source) return;
    const next = move(value, event);
    const moved = event.operation.source.id as NarrativeBlock;
    const to = next.indexOf(moved);
    if (next === value || to < 0) return;
    onChange(next);
    setAnnouncement(`${blockCopy[moved].label}已移到第 ${to + 1} 位`);
  };
  return <div className="grid gap-2"><p className="sr-only" id="narrative-sort-instructions">按空格拿起脚本环节，使用方向键移动，再按空格放下；按 Escape 取消。也可以使用上移和下移按钮。</p><p aria-atomic="true" aria-live="polite" className="sr-only">{announcement}</p><FixedNarrativeItem description="前 6 秒说清为什么值得继续看" label="开头抓住人" /><DragDropProvider onDragEnd={onDragEnd} plugins={(defaults) => defaults.map((plugin) => plugin === Accessibility ? chineseAccessibility : plugin)}>{value.map((block, index) => <SortableNarrativeItem block={block} index={index} key={block} onMove={reorder} total={value.length} />)}</DragDropProvider><FixedNarrativeItem description="告诉观众下一步怎么做，别编不存在的优惠" label="引导下单" /></div>;
}
