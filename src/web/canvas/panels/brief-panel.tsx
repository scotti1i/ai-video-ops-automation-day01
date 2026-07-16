import {
  Badge,
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
  toast,
} from "@fifty/workbench-ui";
import { ChevronDown, Link2, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { ApiError, api } from "../../api";
import { SortableNarrativeList } from "../../components/sortable-narrative-list";
import { ProductDialog } from "../../dialogs/resource-dialogs";
import { activeScriptProducer, type ScriptSettingsInput, type Workspace } from "../../domain";
import {
  DEFAULT_NARRATIVE_BLOCKS,
  DURATION_OPTIONS,
  LANGUAGE_OPTIONS,
  WRITING_TONE_OPTIONS,
  scriptSettingsSummary,
} from "../../script-settings";
import type { PanelProps } from "./types";

/** 动作栏 portal 到抽屉底部后会脱离 <form>，提交按钮靠这个 id 关联回来 */
const FORM_ID = "brief-panel-form";

// ============================================================
// 起点面板：这批想做什么（design-v7-canvas.md 面板表第一行）
//
// 吃掉两个旧界面：「开始一批视频」弹窗 + 侧栏「商品」页。
// 商品资料是这一批的依据，不值得一个一级页面，但也不能只能去别处维护——
// 所以它是选择器旁边的二级弹层，用完就回来。
// 提交 = 生成候选 + 跳到「选稿」：这一步的下一步是挑稿，不是回画布发呆。
// ============================================================

/** 手机 44 触达，桌面回到 v6 的 40 */
const CONTROL = "h-11 sm:h-10";

const DEFAULT_SETTINGS: ScriptSettingsInput = {
  language: null,
  writing_tone: "natural",
  duration_seconds: null,
  narrative_blocks: DEFAULT_NARRATIVE_BLOCKS,
};

// ============================================================
// 创作设定：默认收起，展开才是整批口径
// ============================================================

interface SettingsProps {
  settings: ScriptSettingsInput;
  onChange: (settings: ScriptSettingsInput) => void;
}

function ExpressionSettings({ settings, onChange }: SettingsProps) {
  return <div className="grid gap-3 sm:grid-cols-3">
    <Field htmlFor="brief-language" label="语言">
      <Select
        onValueChange={(value) => onChange({ ...settings, language: value === "auto" ? null : value as ScriptSettingsInput["language"] })}
        value={settings.language ?? "auto"}
      >
        <SelectTrigger className={CONTROL} id="brief-language"><SelectValue /></SelectTrigger>
        <SelectContent>
          {LANGUAGE_OPTIONS.map((option) => <SelectItem className="min-h-11" key={option.value} value={option.value}>{option.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </Field>
    <Field htmlFor="brief-tone" label="表达方式">
      <Select onValueChange={(value) => onChange({ ...settings, writing_tone: value as ScriptSettingsInput["writing_tone"] })} value={settings.writing_tone}>
        <SelectTrigger className={CONTROL} id="brief-tone"><SelectValue /></SelectTrigger>
        <SelectContent>
          {WRITING_TONE_OPTIONS.map((option) => <SelectItem className="min-h-11" key={option.value} value={option.value}>{option.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </Field>
    <Field htmlFor="brief-duration" label="时长">
      <Select
        onValueChange={(value) => onChange({ ...settings, duration_seconds: value === "auto" ? null : Number(value) as ScriptSettingsInput["duration_seconds"] })}
        value={settings.duration_seconds === null ? "auto" : String(settings.duration_seconds)}
      >
        <SelectTrigger className={CONTROL} id="brief-duration"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem className="min-h-11" value="auto">时长自动</SelectItem>
          {DURATION_OPTIONS.map((duration) => <SelectItem className="min-h-11" key={duration} value={String(duration)}>{duration} 秒</SelectItem>)}
        </SelectContent>
      </Select>
    </Field>
  </div>;
}

function CreativeSettings({ settings, onChange }: SettingsProps) {
  const [expanded, setExpanded] = useState(false);
  const controlsId = "brief-creative-settings";
  return <section className="min-w-0">
    <button
      aria-controls={controlsId}
      aria-expanded={expanded}
      className={`flex min-h-12 w-full items-center gap-3 border border-border-strong bg-surface px-3 text-left outline-none transition-colors hover:bg-surface-muted focus-visible:ring-2 focus-visible:ring-focus ${expanded ? "rounded-t-md" : "rounded-md"}`}
      onClick={() => setExpanded((value) => !value)}
      type="button"
    >
      <span className="shrink-0 text-sm font-semibold text-ink">脚本怎么写（可不填）</span>
      <span className="min-w-0 flex-1 truncate text-[13px] text-ink-soft">{scriptSettingsSummary(settings)}</span>
      <span className="hidden shrink-0 text-[13px] font-semibold text-brand sm:inline">{expanded ? "收起" : "调整"}</span>
      <ChevronDown aria-hidden="true" className={`size-4 shrink-0 text-ink-muted transition-transform duration-150 ${expanded ? "rotate-180" : ""}`} />
    </button>
    {expanded ? <div className="grid gap-4 rounded-b-md border-x border-b border-border px-3 py-4" id={controlsId}>
      <ExpressionSettings onChange={onChange} settings={settings} />
      <div>
        <div className="mb-2 flex items-end justify-between gap-3">
          <div>
            <p className="m-0 text-sm font-semibold text-ink">内容顺序（先讲什么后讲什么）</p>
            <p className="mb-0 mt-0.5 text-[13px] text-ink-muted">拖动中间环节调整顺序，开头和结尾固定。</p>
          </div>
          <span className="shrink-0 text-[13px] text-ink-muted">这批视频都按这个顺序</span>
        </div>
        <SortableNarrativeList onChange={(narrative_blocks) => onChange({ ...settings, narrative_blocks })} value={settings.narrative_blocks} />
      </div>
    </div> : null}
  </section>;
}

// ============================================================
// 商品：原「商品」页搬进二级弹层
// ============================================================

interface ProductLibraryProps {
  workspace: Workspace;
  open: boolean;
  selectedId: string;
  onOpenChange: (open: boolean) => void;
  onChanged: () => Promise<void>;
  onPick: (productId: string) => void;
}

function ProductLibrary({ workspace, open, selectedId, onOpenChange, onChanged, onPick }: ProductLibraryProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const inUse = workspace.videos.filter((view) => view.video.product_id).length;
  return <>
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent description="填一次商品信息，这批视频写脚本时都能用上它的真实卖点。" title="商品">
        <div className="grid gap-4">
          <div className="flex items-center gap-3">
            <p className="m-0 min-w-0 flex-1 text-[13px] text-ink-soft">{workspace.products.length} 个商品 · {inUse} 条视频正在使用</p>
            <Button className="shrink-0" onClick={() => setCreateOpen(true)} size="sm" variant="secondary">
              <Plus aria-hidden="true" className="size-4" />新增商品
            </Button>
          </div>
          {workspace.products.length
            ? <ul className="m-0 grid list-none divide-y divide-border rounded-[10px] border border-border p-0">
              {workspace.products.map((product) => <li className="grid gap-2 p-3 sm:grid-cols-[1fr_auto] sm:items-start" key={product.id}>
                <div className="min-w-0">
                  <p className="m-0 text-sm font-semibold text-ink">{product.title}</p>
                  <p className="mb-0 mt-0.5 text-[13px] leading-5 text-ink-soft">{product.description}</p>
                  {product.selling_points.length
                    ? <p className="mb-0 mt-1 text-[13px] leading-5 text-ink-muted">{product.selling_points.join(" · ")}</p>
                    : null}
                  {product.url
                    ? <a className="mt-1 inline-flex items-center gap-1 break-all text-[13px] text-brand hover:underline" href={product.url} rel="noreferrer" target="_blank">
                      <Link2 aria-hidden="true" className="size-3.5 shrink-0" />商品链接
                    </a>
                    : null}
                </div>
                {product.id === selectedId
                  ? <Badge className="justify-self-start sm:justify-self-end" tone="brand">这批在用</Badge>
                  : <Button
                    aria-label={`这批用「${product.title}」`}
                    className="justify-self-start sm:justify-self-end"
                    onClick={() => { onPick(product.id); onOpenChange(false); }}
                    size="sm"
                    variant="secondary"
                  >用这个</Button>}
              </li>)}
            </ul>
            : <p className="m-0 text-[13px] leading-5 text-ink-soft">还没有商品。不选商品也能写脚本，但只能写笼统的话、用不上真实卖点。点「新增商品」加一个再回来。</p>}
        </div>
      </DialogContent>
    </Dialog>
    <ProductDialog onCompleted={onChanged} onOpenChange={setCreateOpen} open={createOpen} />
  </>;
}

// ============================================================
// 面板正文（抽屉标题栏、Esc、关闭按钮由 panel-host 接管）
// ============================================================

/**
 * 跳到「选稿」面板。PanelProps 目前没有跨面板导航，而画布节点本身就是打开面板的
 * 唯一入口——data-pipeline-node 是宿主已有的寻址方式（panel-host 关面板时也靠它
 * 还焦点），点它一下走的就是同一条真实路径，不多一套状态。
 * 节点不在（如单测里单挂面板）就退回关面板：候选已生成，画布徽章上看得见。
 */
function openPickPanel(fallback: () => void) {
  const node = document.querySelector<HTMLElement>('[data-pipeline-node="pick"]');
  if (node) node.click();
  else fallback();
}

export function BriefPanel({ workspace, onChanged, onClose, footerSlot }: PanelProps) {
  const [productId, setProductId] = useState("none");
  const [intent, setIntent] = useState("");
  const [referenceUrl, setReferenceUrl] = useState("");
  const [count, setCount] = useState(10);
  const [settings, setSettings] = useState<ScriptSettingsInput>({ ...DEFAULT_SETTINGS, narrative_blocks: [...DEFAULT_NARRATIVE_BLOCKS] });
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const validCount = count >= 1 && count <= 10;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!validCount) return;
    setPending(true);
    setError(undefined);
    try {
      const result = await api.generateBatch({
        product_id: productId === "none" ? null : productId,
        brief: intent.trim(),
        reference_url: referenceUrl.trim() || null,
        count,
        producer: activeScriptProducer(workspace),
        script_settings: settings,
      });
      await onChanged();
      toast.success(`${result.candidates.length} 条脚本写好了，挑出你要拍的。`);
      openPickPanel(onClose);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "这批脚本没有生成，请再试一次。");
    } finally {
      setPending(false);
    }
  };

  // ProductLibrary 必须留在 form 外：它的「新增商品」弹层自带 form，
  // portal 里的 submit 会顺着 React 树冒泡到这里，把新增商品变成开一批视频。
  return <>
    <form className="grid gap-4" id={FORM_ID} onSubmit={(event) => void submit(event)}>
      <div className="grid gap-4 sm:grid-cols-[1fr_128px]">
        <Field htmlFor="brief-product" label="商品">
          <div className="flex min-w-0 gap-2">
            <Select onValueChange={setProductId} value={productId}>
              <SelectTrigger className={`min-w-0 flex-1 ${CONTROL}`} id="brief-product"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem className="min-h-11" value="none">不选商品</SelectItem>
                {workspace.products.map((product) => <SelectItem className="min-h-11" key={product.id} value={product.id}>{product.title}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button className={`shrink-0 ${CONTROL}`} onClick={() => setLibraryOpen(true)} type="button" variant="secondary">管理商品</Button>
          </div>
        </Field>
        <Field error={validCount ? undefined : "填 1—10 之间的数字"} hint="1—10 条" htmlFor="brief-count" label="脚本数量">
          <Input
            aria-invalid={!validCount || undefined}
            className={CONTROL}
            id="brief-count"
            max={10}
            min={1}
            onChange={(event) => setCount(Number(event.target.value))}
            type="number"
            value={count}
          />
        </Field>
      </div>
      <Field htmlFor="brief-intent" label="想拍的方向">
        <Textarea
          className="min-h-24"
          id="brief-intent"
          onChange={(event) => setIntent(event.target.value)}
          placeholder="例：为租房人群做浴室收纳视频，重点讲免打孔"
          value={intent}
        />
      </Field>
      <Field htmlFor="brief-reference" label="参考视频">
        <Input
          className={CONTROL}
          id="brief-reference"
          onChange={(event) => setReferenceUrl(event.target.value)}
          placeholder="贴一条你想参考的视频链接"
          type="url"
          value={referenceUrl}
        />
      </Field>
      <CreativeSettings onChange={setSettings} settings={settings} />
      {error ? <p className="m-0 text-sm text-danger" role="alert">{error}</p> : null}
    </form>
    {/* 主动作常驻：展开创作设定后正文会滚，按钮不许跟着滚走。
        走 footerSlot 会 portal 出 <form>，所以提交按钮用 form 属性显式关联回去。 */}
    {footerSlot ? createPortal(
      <div className="flex gap-2 border-t border-border bg-surface px-6 py-4 sm:justify-end">
        <Button className="min-h-11 flex-1 sm:min-h-10 sm:flex-none" onClick={onClose} type="button" variant="secondary">取消</Button>
        <Button className="min-h-11 flex-[2] sm:min-h-10 sm:flex-none" disabled={!validCount} form={FORM_ID} loading={pending} loadingLabel="正在生成" type="submit">
          生成 {validCount ? count : 0} 条脚本
        </Button>
      </div>, footerSlot) : null}
    <ProductLibrary
      onChanged={onChanged}
      onOpenChange={setLibraryOpen}
      onPick={setProductId}
      open={libraryOpen}
      selectedId={productId}
      workspace={workspace}
    />
  </>;
}
