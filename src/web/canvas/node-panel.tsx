import { IconButton } from "@fifty/workbench-ui";
import { X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

// ============================================================
// 节点就地展开卡片（对标 ComfyUI/liblib/TapNow 的"点开节点"，不是盖顶模态）
//
// 关键：卡片跟随画布——每帧读被点节点的实时屏幕位置，平移/缩放画布时卡片跟着走。
// 没有压暗遮罩（不"盖在最上面"），画布始终可见；按实测尺寸夹进视口，底部动作栏不被截断。
// 我们的面板重（选稿要读 10 条脚本），装不进节点体，所以卡片停在节点旁、锚定它、跟着它动。
// ============================================================

export interface NodePanelProps {
  open: boolean;
  onClose: () => void;
  /** 从哪个节点长出来：用它的实时屏幕位置做锚点，卡片一直跟着它 */
  anchorId?: string;
  icon?: LucideIcon;
  title: string;
  description?: string;
  /** 主动作栏槽位（常驻卡片底部、不随正文滚动） */
  footer?: ReactNode;
  children: ReactNode;
}

const MARGIN = 16;
const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), Math.max(min, max));

/** 节点在画布上可能有桌面+手机两份 DOM，取真正可见（有宽度）的那个 */
function anchorRect(anchorId?: string): DOMRect | null {
  if (!anchorId) return null;
  const nodes = document.querySelectorAll<HTMLElement>(`[data-pipeline-node="${anchorId}"]`);
  for (const node of nodes) {
    const rect = node.getBoundingClientRect();
    if (rect.width > 0) return rect;
  }
  return null;
}

export function NodePanel({ open, onClose, anchorId, icon: Icon, title, description, footer, children }: NodePanelProps) {
  const followRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const originSet = useRef(false);
  const [entered, setEntered] = useState(false);

  // 每帧跟随：读节点实时屏幕位置，把卡片夹进视口后贴上去。平移画布→卡片跟着走。
  useEffect(() => {
    if (!open) { setEntered(false); originSet.current = false; return undefined; }
    let raf = 0;
    const tick = () => {
      const follow = followRef.current;
      const card = cardRef.current;
      if (follow && card) {
        const w = card.offsetWidth;
        const h = card.offsetHeight;
        const anchor = anchorRect(anchorId);
        let left = anchor ? anchor.left - 8 : (window.innerWidth - w) / 2;
        let top = anchor ? anchor.top - 8 : (window.innerHeight - h) / 2;
        left = clamp(left, MARGIN, window.innerWidth - w - MARGIN);
        top = clamp(top, MARGIN, window.innerHeight - h - MARGIN);
        follow.style.transform = `translate3d(${left}px, ${top}px, 0)`;
        // 动效原点指向节点中心，只定一次——放大从节点长出来
        if (!originSet.current && anchor) {
          card.style.transformOrigin = `${clamp(anchor.left + anchor.width / 2 - left, 0, w)}px ${clamp(anchor.top + anchor.height / 2 - top, 0, h)}px`;
          originSet.current = true;
        }
      }
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    // 位置在首帧已定，下一帧再入场，避免左上角闪一下
    const enter = window.requestAnimationFrame(() => window.requestAnimationFrame(() => setEntered(true)));
    return () => { window.cancelAnimationFrame(raf); window.cancelAnimationFrame(enter); };
  }, [open, anchorId]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => { if (entered) cardRef.current?.focus(); }, [entered]);

  if (!open) return null;
  return createPortal(
    // 容器 pointer-events-none：画布始终可交互（可平移可缩放），弹窗只是浮在上面跟着节点走。
    // 不盖顶、不压暗、不拦点击——关闭靠 X 或 Esc，不靠点外面（点外面是在操作画布）。
    <div className="pointer-events-none fixed inset-0 z-40">
      {/* 外层：rAF 每帧 translate，跟随节点 */}
      <div className="absolute left-0 top-0 will-change-transform" ref={followRef}>
        <div
          aria-label={title}
          aria-modal="false"
          className="pointer-events-auto flex max-h-[86vh] w-[min(92vw,720px)] flex-col overflow-hidden rounded-[16px] border border-border bg-surface shadow-[var(--shadow-overlay)] outline-none"
          ref={cardRef}
          role="dialog"
          style={{
            transform: entered ? "scale(1)" : "scale(0.94)",
            opacity: entered ? 1 : 0,
            transition: "transform 180ms var(--ease-out), opacity 150ms var(--ease-out)",
          }}
          tabIndex={-1}
        >
          <header className="flex shrink-0 items-start gap-2.5 border-b border-border px-5 py-4">
            {Icon ? <span className="grid size-7 shrink-0 place-items-center rounded-[8px] bg-surface-muted text-ink-soft"><Icon aria-hidden="true" className="size-4" /></span> : null}
            <div className="min-w-0 flex-1">
              <h2 className="m-0 text-base font-semibold leading-6 text-ink">{title}</h2>
              {description ? <p className="mb-0 mt-0.5 text-[13px] leading-5 text-ink-soft">{description}</p> : null}
            </div>
            <IconButton aria-label="关闭" className="-mr-1 shrink-0" onClick={onClose}><X className="size-4" /></IconButton>
          </header>
          <div className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-5">{children}</div>
          {footer ? <div className="shrink-0">{footer}</div> : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}
