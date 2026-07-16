import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { PublicationControl } from "../dialogs/publish-dialog";
import type { Publication } from "../domain";
import { WORKSPACE } from "./fixture";

const SCHEDULED_PUBLICATION: Publication = {
  ...WORKSPACE.videos[0].video.publications[0],
  id: "publication-scheduled",
  status: "scheduled",
  scheduled_at: "2026-07-16T04:00:00Z",
  published_at: null,
  external_id: null,
  url: null,
  metrics: [],
  comments: [],
};

afterEach(() => vi.restoreAllMocks());

describe("YouTube 排期确认", () => {
  it("排期任务仍提供明确的人工确认入口", async () => {
    const user = userEvent.setup();
    render(
      <PublicationControl
        account={WORKSPACE.accounts[0]}
        onCompleted={async () => undefined}
        publication={SCHEDULED_PUBLICATION}
      />,
    );

    await user.click(screen.getByRole("button", { name: "确认排期上传" }));
    expect(screen.getByText("需要人工确认")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认上传到 YouTube" })).toBeInTheDocument();
  });

  it("未知结果提供人工核对入口", async () => {
    const user = userEvent.setup();
    render(
      <PublicationControl
        account={WORKSPACE.accounts[0]}
        onCompleted={async () => undefined}
        publication={{ ...SCHEDULED_PUBLICATION, status: "unknown", scheduled_at: null }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "核对平台结果" }));
    expect(screen.getByLabelText(/平台视频编号/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存核对结果" })).toBeInTheDocument();
  });

  it("确认平台未创建时要求说明和显式勾选", async () => {
    const user = userEvent.setup();
    const confirmAbsent = vi.spyOn(api, "confirmAbsent").mockResolvedValue({});
    const onCompleted = vi.fn().mockResolvedValue(undefined);
    render(
      <PublicationControl
        account={WORKSPACE.accounts[0]}
        onCompleted={onCompleted}
        publication={{ ...SCHEDULED_PUBLICATION, status: "unknown", scheduled_at: null }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "核对平台结果" }));
    const reset = screen.getByRole("button", { name: "确认未创建，允许重试" });
    expect(reset).toBeDisabled();
    await user.type(screen.getByLabelText(/核对说明/), "频道后台和定时列表均无记录");
    await user.click(screen.getByRole("checkbox"));
    await user.click(reset);

    expect(confirmAbsent).toHaveBeenCalledWith(
      "publication-scheduled",
      "频道后台和定时列表均无记录",
    );
    expect(onCompleted).toHaveBeenCalledOnce();
  });
});
