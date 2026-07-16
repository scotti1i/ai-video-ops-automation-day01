import { screen } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import type { Workspace } from "../domain";

/**
 * 画布节点是打开面板的唯一入口，测试也走用户那条真实路径。
 * 节点的无障碍名是「<节点名>：<状态>，<计数>」，所以按前缀匹配；
 * 抽屉标题就是节点名（panel-host 用同一份模型渲染）。
 */
export async function openPanel(user: UserEvent, label: string): Promise<HTMLElement> {
  await user.click(await screen.findByRole("button", { name: new RegExp(`^${label}：`) }));
  return screen.findByRole("dialog", { name: label });
}

export const WORKSPACE: Workspace = {
  id: "workspace-demo",
  name: "美区内容组",
  mode: "demo",
  traffic_threshold: 10_000,
  order_threshold: 5,
  account_groups: [{ id: "group-1", name: "美区主账号", sort_order: 1 }],
  accounts: [{ id: "account-1", group_id: "group-1", name: "Home Lab", handle: "@homelab", platform: "youtube", connection_status: "mock", context: "真实体验、语速快、不夸大。", connector_ref: null }],
  products: [{ id: "product-1", title: "免打孔置物架", description: "租房浴室收纳", selling_points: ["免工具", "30 秒安装"], url: "https://example.com/product", image_url: null }],
  batches: [],
  videos: [{
    stage: { stage: "published", label: "已发布", next_action: "同步数据", tone: "success" },
    performance: { label: "流量成交双高", tone: "success", best_views: 58_200, best_orders: 21, best_revenue: 429, source_publication_id: "publication-1" },
    performance_brief: "播放 5.82 万，为同批中位数的 3.2 倍；成交 21 单；高赞评论集中在“租房墙面能不能用”。",
    video: {
      id: "video-1", code: "VID-001", external_video_id: "video-1", title: "30 秒免打孔安装", goal: "用失败对比开场，强调租房可用", account_ids: ["account-1"], product_id: "product-1", parent_video_id: null, variation_note: null, batch_id: null, created_at: "2026-07-14T01:00:00Z", updated_at: "2026-07-14T02:00:00Z",
      contexts: [{ id: "context-1", video_id: "video-1", version: 1, brief: "美区租房人群、30 秒、真人口播", sources: [{ id: "source-1", kind: "url", label: "对标视频", content: "从失败结果开场", href: "https://example.com/video", file_name: null }], created_at: "2026-07-14T01:00:00Z" }],
      scripts: [{ id: "script-1", video_id: "video-1", version: 2, source: "mock", content: "你还在墙上打孔吗？这个置物架 30 秒就能装好。", note: "样例生成", created_at: "2026-07-14T01:10:00Z" }],
      storyboards: [{ id: "board-1", video_id: "video-1", version: 2, source: "mock", note: "样例生成", created_at: "2026-07-14T01:10:00Z", shots: [{ order: 1, role: "hook", duration_seconds: 6, visual: "墙面打孔失败特写", voiceover: "你还在墙上打孔吗？", on_screen_text: "别再打孔" }] }],
      media: [{ id: "media-1", video_id: "video-1", file_name: "install-v2.mp4", mime_type: "video/mp4", size_bytes: 12_000_000, checksum: "abc", storage_path: "sample://install-v2.mp4", source: "external", status: "ready", created_at: "2026-07-14T01:30:00Z" }],
      publications: [{ id: "publication-1", video_id: "video-1", account_id: "account-1", status: "succeeded", scheduled_at: null, published_at: "2026-07-14T02:00:00Z", external_id: "yt-demo", url: "https://youtu.be/demo", error: null, warnings: [], created_at: "2026-07-14T01:45:00Z", updated_at: "2026-07-14T02:00:00Z", metrics: [{ id: "metric-1", publication_id: "publication-1", captured_at: "2026-07-14T03:00:00Z", views: 58_200, likes: 1800, comments: 92, shares: 110, orders: 21, revenue: 429 }], comments: [{ id: "comment-1", publication_id: "publication-1", author: "Mia", content: "租房墙面也能用吗？", likes: 14, commented_at: "2026-07-14T02:30:00Z" }] }],
    },
  }],
};
