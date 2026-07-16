import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../app";
import type { Batch, ScriptCandidate, VideoView, Workspace } from "../domain";
import { openPanel, WORKSPACE } from "./fixture";

// ============================================================
// 选稿主流程（design-v7-canvas.md 面板表第三行 · v5 内容合同）
// 默认零勾选 · 「只选可以拍的」是快捷动作 · 0 选中时主按钮禁用并提示。
// 候选先于产能：先比较脚本和证据，再消耗演员、剪辑和发布成本。
// ============================================================

function candidate(overrides: Partial<ScriptCandidate> & Pick<ScriptCandidate, "id" | "position" | "title" | "angle">): ScriptCandidate {
  const passed = overrides.quality?.status !== "needs_revision";
  return {
    batch_id: "batch-candidates",
    hypothesis: "只替换这个测试角度，验证开头是否更能留人。",
    script: "早上只剩五分钟，你还会拿出一整套榨汁机吗？\n杯子里加好水果，盖上就能直接打。\n看这杯现场打出来的状态，想早上少一道流程，可以点进商品页看详情。",
    shots: [
      { order: 1, role: "hook", duration_seconds: 3, visual: "时钟和桌上大榨汁机同框", voiceover: "早上只剩五分钟，你还会拿出一整套榨汁机吗？", on_screen_text: "只剩 5 分钟" },
      { order: 2, role: "proof", duration_seconds: 7, visual: "将切好的水果放入便携杯并现场打制", voiceover: "杯子里加好水果，盖上就能直接打。", on_screen_text: "现场打给你看" },
      { order: 3, role: "cta", duration_seconds: 5, visual: "展示杯中完成品和商品页入口", voiceover: "想早上少一道流程，可以点进商品页看详情。", on_screen_text: "点进商品页看详情" },
    ],
    provider: "mock",
    claims_used: ["杯子形态", "可直接打制"],
    claims_needing_evidence: passed ? [] : ["需补充连续打制画面"],
    quality: overrides.quality ?? {
      status: "ready_to_test",
      score: 86,
      checks: [
        { key: "hook", label: "3 秒钩子", passed: true, score: 15, max_score: 15, detail: "开头有明确时间冲突" },
        { key: "proof", label: "画面证明", passed, score: passed ? 20 : 5, max_score: 20, detail: passed ? "已安排现场打制" : "缺少现场打制画面" },
      ],
      risks: passed ? [] : ["上线前补拍产品打制过程"],
    },
    selected_video_id: null,
    created_at: "2026-07-15T02:00:00Z",
    updated_at: "2026-07-15T02:00:00Z",
    ...overrides,
  };
}

function draftBatch(candidates: ScriptCandidate[], overrides: Partial<Batch> = {}): Batch {
  return {
    id: "batch-candidates",
    name: "便携榨汁杯通勤测试",
    product_id: "product-1",
    brief: "给赶时间的上班族，只讲早上少一道流程",
    reference_url: "https://example.com/reference",
    video_ids: [],
    candidates,
    created_at: "2026-07-15T02:00:00Z",
    ...overrides,
  };
}

function json(value: unknown): Response {
  return new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });
}

function candidateWorkspace(batch?: Batch): Workspace {
  const workspace = structuredClone(WORKSPACE);
  workspace.products[0].title = "便携榨汁杯";
  workspace.batches = batch ? [batch] : [];
  workspace.videos = [];
  return workspace;
}

describe("选稿主流程", () => {
  beforeEach(() => {
    window.location.hash = "";
    window.localStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("默认零勾选：0 选中时主按钮禁用并提示，「只选可以拍的」才是快捷动作", async () => {
    const user = userEvent.setup();
    const ready = candidate({ id: "candidate-ready", position: 1, title: "通勤鲜榨：早上少一道流程", angle: "痛点开场" });
    const needsWork = candidate({
      id: "candidate-risk", position: 2, title: "直接展示杯中成品", angle: "结果先行",
      quality: { status: "needs_revision", score: 64, checks: [{ key: "proof", label: "画面证明", passed: false, score: 5, max_score: 20, detail: "缺少现场打制画面" }], risks: ["上线前补拍打制过程"] },
    });
    vi.stubGlobal("fetch", vi.fn(async () => json(candidateWorkspace(draftBatch([ready, needsWork])))));

    render(<App />);
    const panel = await openPanel(user, "选稿");
    expect(within(panel).getByText("痛点开场")).toBeInTheDocument();
    expect(within(panel).getByText("结果先行")).toBeInTheDocument();
    expect(within(panel).getByText("缺少现场打制画面")).toBeInTheDocument();
    // 不许出现营销口径：质量诚实只说结构
    expect(panel).not.toHaveTextContent("高转化");
    expect(panel).not.toHaveTextContent("爆款");

    const readyBox = within(panel).getByRole("checkbox", { name: "选择脚本：通勤鲜榨：早上少一道流程" });
    const riskBox = within(panel).getByRole("checkbox", { name: "选择脚本：直接展示杯中成品" });
    expect(readyBox).not.toBeChecked();
    expect(riskBox).not.toBeChecked();
    expect(within(panel).getByRole("button", { name: "选好 0 条，拿去拍" })).toBeDisabled();
    expect(within(panel).getByText("先勾选要拍的脚本")).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: "只选可以拍的" }));
    expect(readyBox).toBeChecked();
    expect(riskBox).not.toBeChecked();
    await user.click(within(panel).getByRole("button", { name: "清空" }));
    expect(readyBox).not.toBeChecked();
  });

  it("整条支持键盘展开，勾选不误触展开", async () => {
    const user = userEvent.setup();
    const ready = candidate({ id: "candidate-ready", position: 1, title: "通勤鲜榨：早上少一道流程", angle: "痛点开场" });
    vi.stubGlobal("fetch", vi.fn(async () => json(candidateWorkspace(draftBatch([ready])))));

    render(<App />);
    const panel = await openPanel(user, "选稿");
    const row = within(panel).getByRole("button", { name: /通勤鲜榨/ });
    expect(row).toHaveAttribute("aria-expanded", "false");

    await user.click(within(panel).getByRole("checkbox", { name: /通勤鲜榨/ }));
    expect(row).toHaveAttribute("aria-expanded", "false");

    row.focus();
    await user.keyboard("{Enter}");
    // Enter→click→React 重渲染在满载测试下偶发晚一拍，等它落定（不改验的行为）
    await waitFor(() => expect(row).toHaveAttribute("aria-expanded", "true"));
    expect(within(panel).getByRole("region", { name: "完整台词" })).toHaveTextContent("早上只剩五分钟");
    expect(within(panel).getByRole("region", { name: "镜头清单" })).toHaveTextContent("钩子");
    expect(within(panel).getByRole("region", { name: "商品卖点" })).toHaveTextContent("杯子形态");
    expect(within(panel).getByRole("region", { name: "脚本写全了吗" })).toHaveTextContent("2 / 2 项达标");
  });

  it("可编辑脚本分镜并只重写当前待选脚本", async () => {
    const user = userEvent.setup();
    let item = candidate({ id: "candidate-ready", position: 1, title: "通勤鲜榨", angle: "现场演示" });
    let workspace = candidateWorkspace(draftBatch([item]));
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/regenerate")) {
        item = { ...item, title: "重写后：现场打一杯" };
        workspace = candidateWorkspace(draftBatch([item]));
        return json(item);
      }
      if (init?.method === "PATCH") {
        const body = JSON.parse(String(init.body)) as { title: string; script: string };
        item = { ...item, ...body };
        workspace = candidateWorkspace(draftBatch([item]));
        return json(item);
      }
      return json(workspace);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const panel = await openPanel(user, "选稿");
    await user.click(within(panel).getByRole("button", { name: /通勤鲜榨/ }));
    await user.click(within(panel).getByRole("button", { name: "编辑脚本" }));

    const title = await within(panel).findByLabelText(/内容标题/);
    await user.clear(title);
    await user.type(title, "办公室下午现榨");
    await user.click(within(panel).getByRole("button", { name: "保存并重新检查" }));
    expect(await within(panel).findByText("办公室下午现榨")).toBeInTheDocument();

    const patchCall = fetchMock.mock.calls.find(([path, init]) => String(path).includes("candidate-ready") && init?.method === "PATCH");
    expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({
      title: "办公室下午现榨",
      shots: expect.arrayContaining([expect.objectContaining({ role: "hook" })]),
    });

    // 保存后这条仍是展开的：重写按钮就在原地，不用再点开一次
    await user.click(within(panel).getByRole("button", { name: "重写这一条" }));
    expect(await within(panel).findByText("重写后：现场打一杯")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([path]) => String(path).endsWith("candidate-ready/regenerate"))).toBe(true);
  });

  it("已选进成片的不再占用选稿面板，还差证据的仍可显式选入", async () => {
    const user = userEvent.setup();
    const selected = candidate({ id: "candidate-selected", position: 1, title: "已选的脚本", angle: "痛点", selected_video_id: "video-selected" });
    const risky = candidate({ id: "candidate-risk", position: 2, title: "待补画面证据", angle: "现场证明", quality: { status: "needs_revision", score: 62, checks: [{ key: "proof", label: "画面证明", passed: false, score: 4, max_score: 20, detail: "缺少完整打制过程" }], risks: ["发布前补拍"] } });
    const batch = draftBatch([selected, risky]);
    let workspace = candidateWorkspace(batch);
    const formal = structuredClone(WORKSPACE.videos[0]) as VideoView;
    formal.video.id = "video-risk";
    formal.video.code = "VID-099";
    formal.video.title = risky.title;
    formal.video.batch_id = batch.id;
    formal.video.media = [];
    formal.video.publications = [];
    formal.stage = { stage: "needs_media", label: "待成片", next_action: "上传成片", tone: "warning" };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/select") && init?.method === "POST") {
        risky.selected_video_id = formal.video.id;
        workspace = { ...workspace, batches: [{ ...batch, candidates: [selected, risky], video_ids: ["video-selected", formal.video.id] }], videos: [formal] };
        return json({ videos: [formal.video] });
      }
      return json(workspace);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const panel = await openPanel(user, "选稿");
    // 已选进成片的不在待选里：同一条稿子不该被挑第二次
    expect(within(panel).queryByText("已选的脚本")).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: /全选/ })).not.toBeInTheDocument();

    const checkbox = within(panel).getByRole("checkbox", { name: "选择脚本：待补画面证据" });
    expect(checkbox).not.toBeChecked();
    await user.click(checkbox);
    await user.click(within(panel).getByRole("button", { name: "选好 1 条，拿去拍" }));

    const selectCall = await waitFor(() => {
      const call = fetchMock.mock.calls.find(([path]) => String(path).endsWith("/select"));
      expect(call).toBeDefined();
      return call;
    });
    expect(JSON.parse(String(selectCall?.[1]?.body))).toEqual({ candidate_ids: ["candidate-risk"] });
    // 这批挑完就空了，面板当场诚实交代，不假装还有稿
    expect(await within(panel).findByText("脚本都挑完了")).toBeInTheDocument();

    // 回到画布看徽章：选稿归零、成片接手——画布不是死图。
    // 抽屉开着时背景整块 aria-hidden，必须先关掉才谈得上「看画布」。
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "选稿" })).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: /^选稿：/ })).toHaveAccessibleName("选稿：这步不用管，暂无待办"));
    expect(screen.getByRole("button", { name: /^成片：/ })).toHaveAccessibleName("成片：等你，1 条要拍");
  });

  it("多批待选脚本可在面板里切批次", async () => {
    const user = userEvent.setup();
    const first = draftBatch([candidate({ id: "candidate-first", position: 1, title: "第一批脚本", angle: "痛点" })], { id: "batch-first", name: "第一批", created_at: "2026-07-15T01:00:00Z" });
    first.candidates[0].batch_id = first.id;
    const second = draftBatch([candidate({ id: "candidate-second", position: 1, title: "第二批脚本", angle: "结果" })], { id: "batch-second", name: "第二批", created_at: "2026-07-15T02:00:00Z" });
    second.candidates[0].batch_id = second.id;
    const workspace = candidateWorkspace();
    workspace.batches = [first, second];
    vi.stubGlobal("fetch", vi.fn(async () => json(workspace)));

    render(<App />);
    const panel = await openPanel(user, "选稿");
    expect(within(panel).getByText("第二批脚本")).toBeInTheDocument();
    await user.click(within(panel).getByRole("combobox", { name: "切换这批视频" }));
    await user.click(await screen.findByRole("option", { name: /第一批/ }));
    expect(within(panel).getByText("第一批脚本")).toBeInTheDocument();
    expect(within(panel).getAllByRole("checkbox")[0]).toHaveAccessibleName("选择脚本：第一批脚本");
  });

  it("待选脚本挑完时空态说清下一步，不写「暂无数据」", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => json(candidateWorkspace())));

    render(<App />);
    const panel = await openPanel(user, "选稿");
    expect(within(panel).getByText("还没有脚本")).toBeInTheDocument();
    expect(panel).toHaveTextContent("回流程图点「这批想做什么」");
    expect(panel).not.toHaveTextContent("暂无数据");
  });
});
