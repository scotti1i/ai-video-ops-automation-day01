import type {
  NarrativeBlock,
  ScriptDuration,
  ScriptLanguage,
  ScriptSettings,
  ScriptSettingsInput,
  ScriptWritingTone,
} from "./domain";

export const DEFAULT_NARRATIVE_BLOCKS: NarrativeBlock[] = ["problem", "proof", "objection"];

export const LANGUAGE_OPTIONS: { label: string; value: "auto" | Exclude<ScriptLanguage, null> }[] = [
  { label: "语言自动", value: "auto" },
  { label: "简体中文", value: "zh-CN" },
  { label: "美式英文", value: "en-US" },
];

export const WRITING_TONE_OPTIONS: { label: string; value: ScriptWritingTone }[] = [
  { label: "自然可信", value: "natural" },
  { label: "直接利落", value: "direct" },
  { label: "轻松生活", value: "warm" },
  { label: "专业讲解", value: "expert" },
];

export const DURATION_OPTIONS: Exclude<ScriptDuration, null>[] = [20, 25, 30];

const languageLabels: Record<Exclude<ScriptLanguage, null>, string> = {
  "zh-CN": "简体中文",
  "en-US": "美式英文",
};

const toneLabels = Object.fromEntries(
  WRITING_TONE_OPTIONS.map(({ label, value }) => [value, label]),
) as Record<ScriptWritingTone, string>;

export function isDefaultNarrative(blocks: NarrativeBlock[]): boolean {
  return blocks.length === DEFAULT_NARRATIVE_BLOCKS.length
    && blocks.every((block, index) => block === DEFAULT_NARRATIVE_BLOCKS[index]);
}

export function scriptSettingsSummary(settings?: ScriptSettings | ScriptSettingsInput | null): string {
  if (!settings) return "用上次的设置";
  const language = settings.language ? languageLabels[settings.language] : "语言自动";
  const duration = settings.duration_seconds ? `${settings.duration_seconds} 秒` : "时长自动";
  const structure = isDefaultNarrative(settings.narrative_blocks) ? "常规写法" : "改过顺序";
  return `${language} · ${toneLabels[settings.writing_tone]} · ${duration} · ${structure}`;
}
