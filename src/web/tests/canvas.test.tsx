import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../app";
import type { Batch, ScriptCandidate, VideoView, Workspace } from "../domain";
import { openPanel, WORKSPACE } from "./fixture";

// ============================================================
// 画布合同（design-v7-canvas.md）
// 一屏 = 一个环：八个节点、固定顺序、点节点开面板、键盘可达。
// 判断在面板里——画布只回答「现在该干什么」。
// ============================================================

/** 流程顺序 = 节点 DOM 顺序 = Tab 顺序，三者是同一条 */
const PIPELINE = ["这批想做什么", "生成脚本", "选稿", "成片", "发布", "数据", "谁赢了", "再做一版"];

function json(value: unknown): Response {
  return new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });
}

function serve(workspace: Workspace) {
  vi.stubGlobal("fetch", vi.fn(async () => json(workspace)));
}

function candidate(id: string, selectedVideoId: string | null = null): ScriptCandidate {
  return {
    id, batch_id: "batch-1", position: 1, title: `待选脚本 ${id}`, angle: "痛点开场",
    hypothesis: "只换开头，验证留人。", script: "你还在墙上打孔吗？", shots: [],
    provider: "mock", claims_used: [], claims_needing_evidence: [],
    quality: { status: "ready_to_test", score: 80, checks: [], risks: [] },
    selected_video_id: selectedVideoId, created_at: "2026-07-15T02:00:00Z", updated_at: "2026-07-15T02:00:00Z",
  };
}

function batch(candidates: ScriptCandidate[], videoIds: string[] = []): Batch {
  return {
    id: "batch-1", name: "通勤场景第一批", product_id: "product-1", brief: "给赶时间的上班族",
    reference_url: null, video_ids: videoIds, candidates, created_at: "2026-07-15T00:00:00Z",
  };
}

function videoAt(id: string, stage: VideoView["stage"]["stage"], label: string): VideoView {
  const view = structuredClone(WORKSPACE.videos[0]);
  view.video.id = id;
  view.video.code = id.toUpperCase();
  view.video.title = `视频 ${id}`;
  view.stage = { ...view.stage, stage, label };
  return view;
}

/** 节点的无障碍名把状态和计数都说清楚——状态不能只靠颜色表达 */
function nodeNamed(label: string): HTMLElement {
  return screen.getByRole("button", { name: new RegExp(`^${label}：`) });
}

describe("画布：一屏一个环", () => {
  beforeEach(() => {
    window.location.hash = "";
    window.localStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("首页就是画布：八个节点按流程顺序排列，没有侧栏导航", async () => {
    serve(structuredClone(WORKSPACE));
    render(<App />);

    await waitFor(() => expect(nodeNamed("这批想做什么")).toBeInTheDocument());
    const labels = screen.getAllByRole("button")
      .map((button) => button.getAttribute("aria-label") ?? "")
      .filter((label) => PIPELINE.some((item) => label.startsWith(`${item}：`)))
      .map((label) => label.split("：")[0]);
    expect(labels).toEqual(PIPELINE);
    // 侧栏四入口已经砍掉：画布即导航
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "视频" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "发布日历" })).not.toBeInTheDocument();
  });

  it("徽章数字与状态来自真实数据：等你的节点唯一高亮，其余安静", async () => {
    const workspace = structuredClone(WORKSPACE);
    workspace.batches = [batch([candidate("c-1"), candidate("c-2")])];
    workspace.videos = [videoAt("video-1", "needs_media", "待成片")];
    serve(workspace);
    render(<App />);

    // 选稿：2 条待选脚本、要人拍板 → 等你
    await waitFor(() => expect(nodeNamed("选稿")).toHaveAccessibleName("选稿：等你，2 条脚本要挑"));
    expect(within(nodeNamed("选稿")).getByText("2")).toBeInTheDocument();
    // 成片：1 条待成片，也要人拍板
    expect(nodeNamed("成片")).toHaveAccessibleName("成片：等你，1 条要拍");
    // 发布：0 条 → 静默为灰、不出徽章
    expect(nodeNamed("发布")).toHaveAccessibleName("发布：这步不用管，暂无待办");
    expect(within(nodeNamed("发布")).queryByText("0")).not.toBeInTheDocument();
  });

  it("发布失败只在发布节点报「出问题」，红徽章只数出问题的那几条", async () => {
    const workspace = structuredClone(WORKSPACE);
    workspace.videos = [
      videoAt("video-1", "publish_failed", "发布失败"),
      videoAt("video-2", "scheduled", "已排期"),
    ];
    serve(workspace);
    render(<App />);

    await waitFor(() => expect(nodeNamed("发布")).toHaveAccessibleName("发布：出问题，1 条出问题"));
    expect(within(nodeNamed("发布")).getByText("1")).toBeInTheDocument();
  });

  it("12 条和 500 条视频，画布长得一样——只有徽章数字变", async () => {
    const workspace = structuredClone(WORKSPACE);
    workspace.videos = Array.from({ length: 500 }, (_, index) => videoAt(`video-${index}`, "needs_media", "待成片"));
    serve(workspace);
    render(<App />);

    await waitFor(() => expect(nodeNamed("成片")).toHaveAccessibleName("成片：等你，500 条要拍"));
    const nodes = screen.getAllByRole("button")
      .filter((button) => PIPELINE.some((item) => (button.getAttribute("aria-label") ?? "").startsWith(`${item}：`)));
    expect(nodes).toHaveLength(8);
  });

  it("点每个节点都开对应面板，八个节点七个面板（谁赢了与再做一版共用）", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    workspace.batches = [batch([candidate("c-1")])];
    serve(workspace);
    render(<App />);
    await waitFor(() => expect(nodeNamed("这批想做什么")).toBeInTheDocument());

    for (const label of PIPELINE) {
      const drawer = await openPanel(user, label);
      expect(drawer).toBeInTheDocument();
      await user.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("dialog", { name: label })).not.toBeInTheDocument());
    }
  });

  it("谁赢了和再做一版共用同一个面板，标题告诉你从哪个门进来的", async () => {
    const user = userEvent.setup();
    serve(structuredClone(WORKSPACE));
    render(<App />);
    await waitFor(() => expect(nodeNamed("谁赢了")).toBeInTheDocument());

    const distill = await openPanel(user, "谁赢了");
    expect(within(distill).getByText(WORKSPACE.videos[0].performance_brief!)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "谁赢了" })).not.toBeInTheDocument());

    const spawn = await openPanel(user, "再做一版");
    expect(within(spawn).getByText(WORKSPACE.videos[0].performance_brief!)).toBeInTheDocument();
  });

  it("键盘可达：Tab 走到节点、Enter 开面板、Esc 关面板并把焦点还回节点", async () => {
    const user = userEvent.setup();
    serve(structuredClone(WORKSPACE));
    render(<App />);
    const node = await screen.findByRole("button", { name: /^这批想做什么：/ });

    node.focus();
    expect(node).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("dialog", { name: "这批想做什么" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "这批想做什么" })).not.toBeInTheDocument());
    // 抽屉是受控的、没有 trigger，焦点必须手动还回去，否则 Tab 会从文档头重来
    await waitFor(() => expect(screen.getByRole("button", { name: /^这批想做什么：/ })).toHaveFocus());
  });

  it("节点显示标题当内容锚点，但不 dump 口播正文：读稿是面板的事", async () => {
    const workspace = structuredClone(WORKSPACE);
    workspace.batches = [batch([candidate("c-1")])];
    serve(workspace);
    render(<App />);

    await waitFor(() => expect(nodeNamed("选稿")).toBeInTheDocument());
    // 节点里放真内容（可拍/差证据的聚合分布），不是"自动/等你"标签，也不拿一条冒充全部
    expect(nodeNamed("选稿")).toHaveTextContent(/条能拍/);
    // 但口播正文绝不上画布：读稿、判断内容是面板的事
    expect(screen.queryByText(/你还在墙上打孔吗/)).not.toBeInTheDocument();
  });
});
