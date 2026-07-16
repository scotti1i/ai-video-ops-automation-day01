import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";

describe("API 错误合同", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("展示后端结构化错误而不是通用文案", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      error: { code: "confirmation_required", message: "请先确认真实发布。" },
    }), { status: 409, headers: { "Content-Type": "application/json" } })));

    await expect(api.workspace()).rejects.toMatchObject({
      code: "confirmation_required",
      message: "请先确认真实发布。",
      status: 409,
    });
  });

  it("使用标题 PATCH 与独立批次生成合同", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await api.updateVideoTitle("video-1", "新的内容标题");
    await api.generateBatch({
      product_id: null,
      brief: "通勤场景",
      reference_url: null,
      count: 10,
      producer: "mock",
      script_settings: {
        language: null,
        writing_tone: "natural",
        duration_seconds: 25,
        narrative_blocks: ["problem", "proof", "objection"],
      },
    });

    const [titlePath, titleInit] = fetchMock.mock.calls[0];
    const [batchPath, batchInit] = fetchMock.mock.calls[1];
    expect(titlePath).toBe("/api/videos/video-1");
    expect(titleInit).toMatchObject({ method: "PATCH" });
    expect(JSON.parse(String(titleInit?.body))).toEqual({
      title: "新的内容标题",
    });
    expect(batchPath).toBe("/api/batches/generate");
    expect(JSON.parse(String(batchInit?.body))).toMatchObject({
      brief: "通勤场景",
      count: 10,
      producer: "mock",
      script_settings: expect.objectContaining({
        language: null,
        writing_tone: "natural",
        duration_seconds: 25,
      }),
    });
  });
});
