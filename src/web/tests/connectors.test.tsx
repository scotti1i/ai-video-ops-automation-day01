import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../app";
import type { Connectors, Workspace } from "../domain";
import { openPanel, WORKSPACE } from "./fixture";

// ============================================================
// 「连接与配置」：顶栏菜单进来的居中浮卡 + 生成调用不再硬编码。
// 三段内容来自 GET /api/connectors；写脚本用哪一路听 workspace 的
// active_script_producer，缺省才退回旧规则（演示=示例）。
// ============================================================

const CONNECTORS: Connectors = {
  script: {
    active: "mock",
    options: [
      { id: "mock", label: "内置示例模板", status: "active", detail: "零密钥可用，演示模式默认", how: null },
      { id: "openai", label: "OpenAI 兼容 API", status: "unconfigured", detail: "OPENAI_API_KEY 未设置", how: "export OPENAI_API_KEY=sk-...\nexport OPENAI_BASE_URL=https://... # 可选，兼容中继\nexport OPENAI_MODEL=gpt-... # 可选\nuv run video-ops run" },
      { id: "claude-cli", label: "Claude Code 命令行", status: "detected", detail: "检测到本机已安装 claude 命令", how: "export VIDEO_OPS_SCRIPT_PRODUCER=claude-cli\nuv run video-ops run" },
      { id: "codex-cli", label: "Codex 命令行", status: "missing", detail: "本机没装 codex 命令", how: "export VIDEO_OPS_SCRIPT_PRODUCER=codex-cli\nuv run video-ops run" },
    ],
  },
  publish: {
    platforms: [
      { id: "mock-social", label: "示例平台", status: "ready", detail: "内置，用来完整跑通流程", how: null },
      { id: "youtube", label: "YouTube", status: "unconfigured", detail: "未配置上传目录", how: "export YOUTUBE_UPLOAD_DIR=...\nexport YOUTUBE_EXPECTED_CHANNEL=...\nuv run video-ops run" },
      { id: "custom", label: "自定义平台", status: "contract", detail: "实现 5 个方法就能接入：查账号、发布、查任务、拉数据、拉评论", how: "见 README「其他平台与飞书」——按平台接口合同写一个适配器类" },
    ],
  },
  data: {
    items: [
      { id: "auto-sync", label: "自动拉数据", status: "ready", detail: "发布成功后，每 30 分钟自动拉一次播放、订单、评论", how: null },
      { id: "youtube-comments", label: "YouTube 评论", status: "unconfigured", detail: "要单独授权一次", how: "uv run video-ops youtube-comment-auth --uploader-dir ...\nexport YOUTUBE_COMMENT_TOKEN_PATH=.local/youtube-comment-token.json" },
    ],
  },
};

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

function serve(workspace: Workspace = WORKSPACE, connectors: Connectors = CONNECTORS) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === "/api/connectors") return json(connectors);
    return json(workspace);
  }));
}

async function openConnectors(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
  await waitFor(() => expect(screen.getByRole("button", { name: "更多操作" })).toBeInTheDocument());
  await user.click(screen.getByRole("button", { name: "更多操作" }));
  await user.click(screen.getByRole("menuitem", { name: "连接与配置" }));
  return screen.findByRole("dialog", { name: "连接与配置" });
}

describe("连接与配置", () => {
  beforeEach(() => {
    window.location.hash = "";
    window.localStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("从「更多操作」菜单打开，三段内容俱全", async () => {
    const user = userEvent.setup();
    serve();
    render(<App />);
    const panel = await openConnectors(user);

    const script = within(panel).getByRole("region", { name: "写脚本用什么" });
    expect(within(script).getByText("内置示例模板")).toBeInTheDocument();
    expect(within(script).getByText("OpenAI 兼容 API")).toBeInTheDocument();
    const publish = within(panel).getByRole("region", { name: "发布到哪" });
    expect(within(publish).getByText("YouTube")).toBeInTheDocument();
    const data = within(panel).getByRole("region", { name: "数据怎么拉" });
    expect(within(data).getByText("自动拉数据")).toBeInTheDocument();
  });

  it("六种状态全部映射成大白话标签，不直出英文码", async () => {
    const user = userEvent.setup();
    serve();
    render(<App />);
    const panel = await openConnectors(user);

    expect(within(panel).getByText("当前使用")).toBeInTheDocument();
    expect(within(panel).getAllByText("可用").length).toBeGreaterThan(0);
    expect(within(panel).getByText("已安装")).toBeInTheDocument();
    expect(within(panel).getAllByText("未配置").length).toBeGreaterThan(0);
    expect(within(panel).getByText("未安装")).toBeInTheDocument();
    expect(within(panel).getByText("按接口接入")).toBeInTheDocument();
    expect(panel).not.toHaveTextContent("unconfigured");
    expect(panel).not.toHaveTextContent("detected");
  });

  it("「怎么配」展开命令原文，复制按钮写进剪贴板", async () => {
    const user = userEvent.setup();
    serve();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<App />);
    const panel = await openConnectors(user);

    const row = within(panel).getByText("OpenAI 兼容 API").closest("li");
    expect(row).not.toHaveTextContent("OPENAI_BASE_URL");
    await user.click(within(row!).getByRole("button", { name: "怎么配" }));
    expect(row).toHaveTextContent("export OPENAI_API_KEY=sk-...");

    await user.click(within(row!).getByRole("button", { name: "复制「OpenAI 兼容 API」的配置命令" }));
    expect(writeText).toHaveBeenCalledWith(CONNECTORS.script.options[1].how);
    expect(await screen.findByText("已复制")).toBeInTheDocument();
  });

  it("不用配的行没有「怎么配」入口", async () => {
    const user = userEvent.setup();
    serve();
    render(<App />);
    const panel = await openConnectors(user);
    const row = within(panel).getByText("内置示例模板").closest("li");
    expect(within(row!).queryByRole("button", { name: "怎么配" })).not.toBeInTheDocument();
  });

  it("拉取失败给一句话空态，点重试恢复", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/connectors") {
        attempts += 1;
        if (attempts === 1) return json({ message: "网络暂不可用" }, 503);
        return json(CONNECTORS);
      }
      return json(WORKSPACE);
    }));
    render(<App />);
    const panel = await openConnectors(user);

    expect(await within(panel).findByRole("alert")).toHaveTextContent("网络暂不可用");
    await user.click(within(panel).getByRole("button", { name: "重试" }));
    expect(await within(panel).findByText("内置示例模板")).toBeInTheDocument();
  });

  it("生成脚本带上 workspace 指定的那一路，不再按模式硬编码", async () => {
    const user = userEvent.setup();
    const workspace = structuredClone(WORKSPACE);
    workspace.active_script_producer = "claude-cli";
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/batches/generate" && init?.method === "POST") {
        return json({ batch: { id: "batch-new", name: "新一批", product_id: null, brief: "", reference_url: null, video_ids: [], candidates: [], created_at: "2026-07-15T02:00:00Z" }, candidates: [] });
      }
      return json(workspace);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const panel = await openPanel(user, "这批想做什么");
    await user.click(within(panel).getByRole("button", { name: /^生成 \d+ 条脚本$/ }));

    const call = await waitFor(() => {
      const found = fetchMock.mock.calls.find(([path, init]) => String(path) === "/api/batches/generate" && init?.method === "POST");
      expect(found).toBeDefined();
      return found;
    });
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ producer: "claude-cli" });
  });

  it("旧后端没回传时退回老规则：演示工作区用示例那一路", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/batches/generate" && init?.method === "POST") {
        return json({ batch: { id: "batch-new", name: "新一批", product_id: null, brief: "", reference_url: null, video_ids: [], candidates: [], created_at: "2026-07-15T02:00:00Z" }, candidates: [] });
      }
      return json(WORKSPACE);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const panel = await openPanel(user, "这批想做什么");
    await user.click(within(panel).getByRole("button", { name: /^生成 \d+ 条脚本$/ }));

    const call = await waitFor(() => {
      const found = fetchMock.mock.calls.find(([path, init]) => String(path) === "/api/batches/generate" && init?.method === "POST");
      expect(found).toBeDefined();
      return found;
    });
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ producer: "mock" });
  });
});
