import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../app";
import type { Workspace } from "../domain";
import { openPanel, WORKSPACE } from "./fixture";

// ============================================================
// 外壳合同：顶栏（产品身份 + 低频操作）、视频详情抽屉、深链、失败恢复。
// 视频详情从面板里进——画布即导航，没有清单页可点。
// ============================================================

function json(value: unknown): Response {
  return new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });
}

function serve(workspace: Workspace) {
  vi.stubGlobal("fetch", vi.fn(async () => json(workspace)));
}

/** 已发布的那条：从「数据」面板点标题进详情 */
async function openVideoFromMetrics(user: ReturnType<typeof userEvent.setup>, title = "30 秒免打孔安装") {
  const panel = await openPanel(user, "数据");
  await user.click(within(panel).getByRole("button", { name: title }));
  return screen.findByRole("dialog", { name: title });
}

describe("Day1 视频闭环生产平台", () => {
  beforeEach(() => {
    window.location.hash = "";
    window.localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const body = init?.method === "POST" && path === "/api/videos" ? WORKSPACE.videos[0].video : WORKSPACE;
      return json(body);
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("页头只保留产品身份和低频操作：一级入口全在画布上", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "视频闭环生产平台" })).toBeInTheDocument());
    expect(screen.getByText("零密钥样例工作台")).toBeInTheDocument();
    // 「开始一批视频」不再蹲在顶栏：它就是画布第一个节点，没有第二个点击目标
    expect(screen.queryByRole("button", { name: "开始一批视频" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "更多操作" }));
    expect(screen.getByRole("menuitem", { name: "导入已有脚本" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "批量导入视频" })).toBeInTheDocument();
  });

  it("低频菜单可导出可回灌清单和完整备份", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "更多操作" })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "更多操作" }));
    expect(screen.getByRole("menuitem", { name: "导出视频数据（JSON）" })).toHaveAttribute("href", "/api/exports/videos.json");
    expect(screen.getByRole("menuitem", { name: "导出视频表格（CSV）" })).toHaveAttribute("href", "/api/exports/videos.csv");
    expect(screen.getByRole("menuitem", { name: "导出全部备份" })).toHaveAttribute("href", "/api/exports/workspace.json");
  });

  it("从面板打开视频详情，三个阶段页签俱全", async () => {
    const user = userEvent.setup();
    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    expect(within(drawer).getAllByRole("tab")).toHaveLength(3);
    expect(within(drawer).getByRole("tab", { name: "脚本" })).toBeInTheDocument();
    expect(within(drawer).getByRole("tab", { name: "视频" })).toBeInTheDocument();
    expect(within(drawer).getByRole("tab", { name: "发布" })).toBeInTheDocument();
    await user.click(within(drawer).getByText("更多信息"));
    expect(within(drawer).getByText("目标与素材")).toBeInTheDocument();
    expect(within(drawer).getByText("视频关系")).toBeInTheDocument();
    expect(within(drawer).getByText("操作记录")).toBeInTheDocument();
  });

  it("#video/<id> 深链直接打开单条详情，关掉就回画布", async () => {
    const user = userEvent.setup();
    window.location.hash = "#video/video-1";
    render(<App />);

    const drawer = await screen.findByRole("dialog", { name: "30 秒免打孔安装" });
    expect(drawer).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "30 秒免打孔安装" })).not.toBeInTheDocument());
    await waitFor(() => expect(window.location.hash).toBe(""));
    expect(await screen.findByRole("button", { name: /^选稿：/ })).toBeInTheDocument();
  });

  it("浏览器后退可以从详情退回画布", async () => {
    const user = userEvent.setup();
    render(<App />);
    await openVideoFromMetrics(user);
    await waitFor(() => expect(window.location.hash).toBe("#video/video-1"));

    window.location.hash = "";
    fireEvent(window, new HashChangeEvent("hashchange"));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "30 秒免打孔安装" })).not.toBeInTheDocument());
  });

  it("详情抽屉不直出后端的「待观察」，说人话", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    workspace.videos[0].performance = { label: "待观察", tone: "neutral", best_views: 1_200, best_orders: 0, best_revenue: 0, source_publication_id: "publication-1" };
    serve(workspace);

    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    expect(drawer).toHaveTextContent("数据还没起来");
    expect(drawer).not.toHaveTextContent("待观察");
  });

  it("选入成片的还差证据脚本仍显示风险和商品声明", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    workspace.videos[0].stage = { stage: "needs_media", label: "待成片", next_action: "上传成片", tone: "warning" };
    workspace.videos[0].video.media = [];
    workspace.videos[0].video.publications = [];
    workspace.videos[0].video.scripts[0] = {
      ...workspace.videos[0].video.scripts[0],
      quality: {
        status: "needs_revision",
        score: 85,
        checks: [{ key: "claims", label: "商品声明可追溯", passed: false, score: 0, max_score: 15, detail: "自由文本尚未完成独立商品声明审计" }],
        risks: ["自由文本尚未完成独立商品声明审计"],
      },
      claims_used: ["免工具"],
      claims_needing_evidence: ["30 秒安装"],
    };
    serve(workspace);

    render(<App />);
    const panel = await openPanel(user, "成片");
    await user.click(within(panel).getByRole("button", { name: "打开视频：30 秒免打孔安装" }));
    const drawer = await screen.findByRole("dialog", { name: "30 秒免打孔安装" });

    expect(within(drawer).getByRole("tab", { name: "视频" })).toHaveAttribute("aria-selected", "true");
    // 「需修改」是旧说法，v7 术语表改成「还差证据」
    expect(within(drawer).getByText("还差证据")).toBeInTheDocument();
    expect(drawer).not.toHaveTextContent("需修改");
    expect(within(drawer).getAllByText("自由文本尚未完成独立商品声明审计").length).toBeGreaterThan(0);
    expect(drawer).toHaveTextContent("使用的商品事实：免工具");
    expect(drawer).toHaveTextContent("待补证据：30 秒安装");
  });

  it("面板送来的页签就是这条现在的阶段", async () => {
    const user = userEvent.setup();
    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    expect(within(drawer).getByRole("tab", { name: "发布" })).toHaveAttribute("aria-selected", "true");
  });

  it("无脚本时抽屉只显示脚本待生成单一空态", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    workspace.videos[0].video.scripts = [];
    workspace.videos[0].video.storyboards = [];
    workspace.videos[0].video.media = [];
    workspace.videos[0].video.publications = [];
    workspace.videos[0].stage = { stage: "needs_script", label: "待脚本", next_action: "生成脚本", tone: "warning" };
    workspace.videos[0].performance_brief = null;
    serve(workspace);

    render(<App />);
    const panel = await openPanel(user, "生成脚本");
    await user.click(within(panel).getByRole("button", { name: /30 秒免打孔安装/ }));
    const drawer = await screen.findByRole("dialog", { name: "30 秒免打孔安装" });
    expect(within(drawer).getByText("这条还没有脚本，点上面的「写脚本」开始。")).toBeInTheDocument();
    expect(within(drawer).queryByText("还没拆镜头")).not.toBeInTheDocument();
  });

  it("有脚本但缺分镜时才提示分镜待补齐", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    workspace.videos[0].video.storyboards = [];
    workspace.videos[0].video.media = [];
    workspace.videos[0].video.publications = [];
    workspace.videos[0].stage = { stage: "needs_script", label: "待脚本", next_action: "生成脚本", tone: "warning" };
    serve(workspace);

    render(<App />);
    const panel = await openPanel(user, "生成脚本");
    await user.click(within(panel).getByRole("button", { name: /30 秒免打孔安装/ }));
    const drawer = await screen.findByRole("dialog", { name: "30 秒免打孔安装" });
    expect(within(drawer).getByText("还没拆镜头")).toBeInTheDocument();
  });

  it("再做一版弹窗顶部展示父视频表现提炼", async () => {
    const user = userEvent.setup();
    render(<App />);
    const panel = await openPanel(user, "再做一版");
    await user.click(within(panel).getByRole("button", { name: "再做一版" }));
    const dialog = await screen.findByRole("dialog", { name: "30 秒免打孔安装 · 再做一版" });
    expect(within(dialog).getByText("这条视频的表现")).toBeInTheDocument();
    expect(within(dialog).getByText(WORKSPACE.videos[0].performance_brief!)).toBeInTheDocument();
  });

  it("高表现视频可以带着赢家基因开下一批", async () => {
    const user = userEvent.setup();
    render(<App />);
    const panel = await openPanel(user, "再做一版");
    await user.click(within(panel).getByRole("button", { name: "再做一版" }));
    const dialog = await screen.findByRole("dialog", { name: "30 秒免打孔安装 · 再做一版" });
    expect(within(dialog).getByRole("tab", { name: "做一条" })).toHaveAttribute("aria-selected", "true");
    await user.type(within(dialog).getAllByRole("textbox")[0], "换成评论问答开场");
    await user.click(within(dialog).getByRole("checkbox", { name: /租房墙面也能用吗/ }));
    await user.click(within(dialog).getByRole("button", { name: "创建这一条" }));

    const call = await waitFor(() => {
      const found = vi.mocked(fetch).mock.calls.find(([path, init]) => String(path) === "/api/videos/video-1/branch" && init?.method === "POST");
      expect(found).toBeDefined();
      return found;
    });
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ variation: "换成评论问答开场", comment_ids: ["comment-1"] });
  });

  it("成片详情不把样例占位伪装成可播放文件", async () => {
    const user = userEvent.setup();
    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    await user.click(within(drawer).getByRole("tab", { name: "视频" }));
    expect(within(drawer).getByText("示例视频不能播放")).toBeInTheDocument();
    expect(within(drawer).queryByLabelText("视频预览：install-v2.mp4")).not.toBeInTheDocument();
  });

  it("真实成片可从成片阶段直接播放", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    workspace.videos[0].video.media[0].storage_path = "/private/uploads/video-1/install-v2.mp4";
    serve(workspace);

    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    await user.click(within(drawer).getByRole("tab", { name: "视频" }));
    const player = within(drawer).getByLabelText("视频预览：install-v2.mp4");
    expect(player).toHaveAttribute("src", "/api/media/media-1/content");
    expect(player).toHaveAttribute("controls");
  });

  it("视频详情不直出 mock 平台枚举", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    workspace.accounts[0].platform = "mock-social";
    serve(workspace);

    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    expect(within(drawer).getByText(/示例平台/)).toBeInTheDocument();
    expect(drawer).not.toHaveTextContent("mock-social");
  });

  it("发布卡片把成功状态显示为中文", async () => {
    const user = userEvent.setup();
    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    const card = within(drawer).getByRole("link", { name: "查看平台视频" }).closest("article");
    expect(within(card!).getByText("发布成功")).toBeInTheDocument();
    expect(within(card!).queryByText("succeeded", { exact: true })).not.toBeInTheDocument();
  });

  it("发布时间线不把待执行、已排期和待核对写成已完成", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    const base = workspace.videos[0].video.publications[0];
    // 评论 id 逐条唯一：真实数据里 comment 挂在各自的发布任务下，不会跨任务同 id
    const clone = (id: string, status: typeof base.status, updated: string) => ({
      ...base, id, status, updated_at: updated,
      comments: base.comments.map((comment) => ({ ...comment, id: `${comment.id}-${id}`, publication_id: id })),
    });
    workspace.videos[0].video.publications = [
      clone("publication-draft", "draft", "2026-07-14T02:01:00Z"),
      clone("publication-scheduled", "scheduled", "2026-07-14T02:02:00Z"),
      clone("publication-unknown", "unknown", "2026-07-14T02:03:00Z"),
    ];
    serve(workspace);

    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    await user.click(within(drawer).getByText("更多信息"));

    const timeline = within(drawer).getByRole("heading", { name: "操作记录" }).closest("section");
    expect(within(within(timeline!).getByText("等待发布").closest("li")!).getByRole("status")).toHaveAccessibleName("运行状态：未开始");
    expect(within(within(timeline!).getByText("已排期").closest("li")!).getByRole("status")).toHaveAccessibleName("运行状态：排队中");
    expect(within(within(timeline!).getByText("结果待确认").closest("li")!).getByRole("status")).toHaveAccessibleName("运行状态：等待确认");
    expect(within(drawer).queryByText("draft", { exact: true })).not.toBeInTheDocument();
    expect(within(drawer).queryByText("scheduled", { exact: true })).not.toBeInTheDocument();
  });

  it("详情内可查看版本并继续 AI 对话", async () => {
    const user = userEvent.setup();
    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    await user.click(within(drawer).getByRole("tab", { name: "脚本" }));
    expect(within(drawer).getByRole("combobox", { name: "查看脚本版本" })).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "编辑脚本" }));
    const editor = await screen.findByRole("dialog", { name: "编辑脚本和镜头" });
    expect(editor).not.toHaveTextContent("VID-001");
    await user.click(await within(editor).findByRole("tab", { name: "AI 对话" }));
    const versions = within(editor).getByRole("log", { name: "脚本版本记录" });
    expect(versions).toHaveTextContent("示例生成 · 未调用真实模型");
    expect(versions).toHaveTextContent("示例工作区自带");
    expect(versions).not.toHaveTextContent("样例生成");
  });

  it("旧脚本与分镜可恢复为新版本而不覆盖历史", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    const video = workspace.videos[0].video;
    video.scripts.unshift({ ...video.scripts[0], id: "script-v1", version: 1, content: "旧版脚本", note: "第一版" });
    video.storyboards.unshift({
      ...video.storyboards[0], id: "board-v1", version: 1, note: "第一版",
      shots: [{ order: 1, role: "hook", duration_seconds: 5, visual: "旧版画面", voiceover: "旧版口播", on_screen_text: "旧版" }],
    });
    serve(workspace);

    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    await user.click(within(drawer).getByRole("tab", { name: "脚本" }));
    await user.click(within(drawer).getByRole("combobox", { name: "查看脚本版本" }));
    await user.click(await screen.findByRole("option", { name: "第 1 版" }));

    expect(within(drawer).getByText("旧版脚本")).toBeInTheDocument();
    expect(within(drawer).getByText("旧版画面")).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "切回这个版本" }));

    const call = await waitFor(() => {
      const found = vi.mocked(fetch).mock.calls.find(([path, init]) => String(path) === "/api/videos/video-1/script" && init?.method === "POST");
      expect(found).toBeDefined();
      return found;
    });
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      content: "旧版脚本",
      note: "切回第 1 版",
      shots: [expect.objectContaining({ visual: "旧版画面", voiceover: "旧版口播" })],
    });
  });

  it("脚本详情只展示可用内容，演示来源只说明一次", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    workspace.videos[0].video.scripts[0].content = "【样例生成，不代表真实模型输出】\n# 已有脚本样例\n这是可直接使用的口播。";
    workspace.videos[0].video.scripts[0].note = "保留问题钩子 · 由 mock 生成";
    serve(workspace);

    render(<App />);
    const drawer = await openVideoFromMetrics(user);
    await user.click(within(drawer).getByRole("tab", { name: "脚本" }));
    expect(within(drawer).getByText("这是可直接使用的口播。")).toBeInTheDocument();
    expect(within(drawer).getAllByText(/示例生成 · 未调用真实模型/)).toHaveLength(1);
    expect(drawer).not.toHaveTextContent("已有脚本样例");
    expect(drawer).not.toHaveTextContent("mock");
  });

  it("导入视频清单会先展示预览与冲突再提交", async () => {
    const user = userEvent.setup();
    const preview = {
      schema: "video-ops.video-list/v1", format: "json",
      summary: { total: 2, ready: 1, conflict: 1, invalid: 0, missing_references: 0 },
      rows: [{
        row_number: 1, status: "conflict",
        normalized: { external_video_id: "video-1", code: "VID-001", title: "已存在", goal: "验证", brief: "", account_refs: [], product_ref: "", parent_external_video_id: "", variation_note: "" },
        missing_references: { account_refs: [], product_ref: "", parent_external_video_id: "" },
        errors: [], conflicts: ["该外部视频 ID 已导入"],
      }],
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/import/preview") return json(preview);
      if (path === "/api/import/commit") return json({ created: [WORKSPACE.videos[0].video], skipped: preview.rows, summary: { ...preview.summary, created: 1, skipped: 1 } });
      return json(WORKSPACE);
    }));

    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "更多操作" })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "更多操作" }));
    await user.click(screen.getByRole("menuitem", { name: "批量导入视频" }));
    await user.upload(screen.getByLabelText(/拖入文件/), new File([JSON.stringify({ videos: [] })], "videos.json", { type: "application/json" }));
    await user.click(screen.getByRole("button", { name: "预览" }));

    expect(await screen.findByRole("region", { name: "导入预览汇总" })).toHaveTextContent("1 条可导入");
    expect(screen.getByRole("list", { name: "有问题的行" })).toHaveTextContent("该外部视频 ID 已导入");
    await user.click(screen.getByRole("button", { name: "导入 1 条" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "批量导入视频" })).not.toBeInTheDocument());
    expect(vi.mocked(fetch).mock.calls.some(([path]) => String(path) === "/api/import/commit")).toBe(true);
  });

  it("工作台网络失败后可重试恢复", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      attempts += 1;
      if (attempts === 1) return new Response(JSON.stringify({ message: "网络暂不可用" }), { status: 503, headers: { "Content-Type": "application/json" } });
      return json(WORKSPACE);
    }));

    render(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("网络暂不可用");
    await user.click(within(alert).getByRole("button", { name: "重试" }));
    expect(await screen.findByRole("button", { name: /^选稿：/ })).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it("空工作区也是同一条流水线：八个节点静默待命", async () => {
    serve({ ...structuredClone(WORKSPACE), videos: [], batches: [] });
    render(<App />);
    expect(await screen.findByRole("button", { name: "这批想做什么：这步不用管，暂无待办" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选稿：这步不用管，暂无待办" })).toBeInTheDocument();
  });
});
