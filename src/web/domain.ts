export type Tone = "neutral" | "brand" | "success" | "warning" | "danger" | "info";

export type VideoStage =
  | "needs_script"
  | "needs_media"
  | "ready_to_publish"
  | "publishing"
  | "scheduled"
  | "publish_failed"
  | "needs_reconciliation"
  | "published";

export type VideoDetailTab = "current" | "script" | "media" | "publish";

export type PublicationStatus =
  | "draft"
  | "scheduled"
  | "publishing"
  | "succeeded"
  | "succeeded_with_warnings"
  | "failed"
  | "unknown";

export interface ContextSource {
  id: string;
  kind: string;
  label: string;
  content: string;
  href: string | null;
  file_name: string | null;
}

export interface ContextSnapshot {
  id: string;
  video_id: string;
  version: number;
  brief: string;
  sources: ContextSource[];
  created_at: string;
}

export interface ScriptArtifact {
  id: string;
  video_id: string;
  version: number;
  source: string;
  content: string;
  note: string;
  quality?: ScriptQuality;
  claims_used?: string[];
  claims_needing_evidence?: string[];
  created_at: string;
}

export interface StoryboardShot {
  order: number;
  role: string;
  duration_seconds: number;
  visual: string;
  voiceover: string;
  on_screen_text: string;
}

export interface StoryboardArtifact {
  id: string;
  video_id: string;
  version: number;
  source: string;
  shots: StoryboardShot[];
  note: string;
  created_at: string;
}

export interface MediaArtifact {
  id: string;
  video_id: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  checksum: string;
  storage_path: string;
  source: string;
  status: string;
  created_at: string;
}

export interface MetricSnapshot {
  id: string;
  publication_id: string;
  captured_at: string;
  views: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  orders: number | null;
  revenue: number | null;
}

export interface CommentSnapshot {
  id: string;
  publication_id: string;
  author: string;
  content: string;
  likes: number;
  commented_at: string;
}

export interface Publication {
  id: string;
  video_id: string;
  account_id: string;
  status: PublicationStatus;
  scheduled_at: string | null;
  published_at: string | null;
  external_id: string | null;
  url: string | null;
  error: string | null;
  warnings: string[];
  created_at: string;
  updated_at: string;
  metrics: MetricSnapshot[];
  comments: CommentSnapshot[];
}

export interface Video {
  id: string;
  code: string;
  external_video_id: string | null;
  title: string;
  goal: string;
  account_ids: string[];
  product_id: string | null;
  parent_video_id: string | null;
  variation_note: string | null;
  batch_id: string | null;
  created_at: string;
  updated_at: string;
  contexts: ContextSnapshot[];
  scripts: ScriptArtifact[];
  storyboards: StoryboardArtifact[];
  media: MediaArtifact[];
  publications: Publication[];
}

export interface VideoView {
  video: Video;
  stage: { stage: VideoStage; label: string; next_action: string; tone: Tone };
  performance: {
    label: string;
    tone: Tone;
    best_views: number | null;
    best_orders: number | null;
    best_revenue: number | null;
    source_publication_id: string | null;
  };
  /** 已发布且有指标快照时的中文表现提炼（后端规则生成），否则 null */
  performance_brief: string | null;
}

export interface AccountGroup {
  id: string;
  name: string;
  sort_order: number;
}

export interface Account {
  id: string;
  group_id: string;
  name: string;
  handle: string;
  platform: string;
  connection_status: "connected" | "needs_auth" | "mock" | "disconnected";
  context: string;
  connector_ref: string | null;
}

export interface Product {
  id: string;
  title: string;
  description: string;
  selling_points: string[];
  url: string | null;
  image_url: string | null;
}

export interface QualityCheck {
  key: string;
  label: string;
  passed: boolean;
  score: number;
  max_score: number;
  detail: string;
}

export interface ScriptQuality {
  status: "ready_to_test" | "needs_revision";
  score: number;
  checks: QualityCheck[];
  risks: string[];
}

export interface ScriptCandidate {
  id: string;
  batch_id: string;
  position: number;
  title: string;
  angle: string;
  hypothesis: string;
  script: string;
  shots: StoryboardShot[];
  provider: string;
  claims_used: string[];
  claims_needing_evidence: string[];
  quality: ScriptQuality;
  selected_video_id: string | null;
  created_at: string;
  updated_at: string;
}

export type ScriptLanguage = "zh-CN" | "en-US" | null;
export type ScriptWritingTone = "natural" | "direct" | "warm" | "expert";
export type ScriptDuration = 20 | 25 | 30 | null;
export type NarrativeBlock = "problem" | "proof" | "objection";

export interface ScriptSettings {
  language: ScriptLanguage;
  writing_tone: ScriptWritingTone;
  duration_seconds: number;
  narrative_blocks: NarrativeBlock[];
}

export interface ScriptSettingsInput extends Omit<ScriptSettings, "duration_seconds"> {
  duration_seconds: ScriptDuration;
}

export interface Batch {
  id: string;
  name: string;
  product_id: string | null;
  brief: string;
  note?: string;
  reference_url: string | null;
  video_ids: string[];
  candidates: ScriptCandidate[];
  script_settings?: ScriptSettings | null;
  created_at: string;
}

export interface GenerateBatchInput {
  product_id: string | null;
  brief: string;
  reference_url: string | null;
  count: number;
  producer: string;
  script_settings: ScriptSettingsInput;
}

export interface GenerateBatchResult {
  batch: Batch;
  candidates: ScriptCandidate[];
}

export interface Workspace {
  id: string;
  name: string;
  mode: string;
  /** 当前写脚本用的那一路（后端算好回传；演示工作区 = "mock"），旧后端可能没有 */
  active_script_producer?: string;
  traffic_threshold: number;
  order_threshold: number;
  account_groups: AccountGroup[];
  accounts: Account[];
  products: Product[];
  batches: Batch[];
  videos: VideoView[];
}

/** 写脚本的调用统一从这里取；旧后端没回传时退回老规则（演示=示例，其余=OpenAI 兼容） */
export function activeScriptProducer(workspace: Workspace): string {
  return workspace.active_script_producer ?? (workspace.mode === "demo" ? "mock" : "openai");
}

// ============================================================
// 连接与配置（GET /api/connectors）：写脚本 / 发布 / 拉数据各接的是什么
// ============================================================

export type ConnectorStatus = "active" | "ready" | "detected" | "unconfigured" | "missing" | "contract";

export interface ConnectorItem {
  id: string;
  label: string;
  status: ConnectorStatus;
  /** 给第一次用的人看的大白话说明 */
  detail: string;
  /** 怎么配的命令原文；null = 不用配 */
  how: string | null;
}

export interface Connectors {
  script: { active: string; options: ConnectorItem[] };
  publish: { platforms: ConnectorItem[] };
  data: { items: ConnectorItem[] };
}

export type ImportFormat = "json" | "csv";

export interface ImportPreviewRow {
  row_number: number;
  status: "ready" | "conflict" | "invalid";
  normalized: {
    external_video_id: string;
    code: string;
    title: string;
    goal: string;
    brief: string;
    account_refs: string[];
    product_ref: string;
    parent_external_video_id: string;
    variation_note: string;
  };
  missing_references: {
    account_refs: string[];
    product_ref: string;
    parent_external_video_id: string;
  };
  errors: string[];
  conflicts: string[];
}

export interface ImportSummary {
  total: number;
  ready: number;
  conflict: number;
  invalid: number;
  missing_references: number;
  created?: number;
  skipped?: number;
}

export interface ImportPreview {
  schema: string;
  format: ImportFormat;
  rows: ImportPreviewRow[];
  summary: ImportSummary;
}

export interface ImportCommitResult {
  created: Video[];
  skipped: ImportPreviewRow[];
  summary: ImportSummary;
}
