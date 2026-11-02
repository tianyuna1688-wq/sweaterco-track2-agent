import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import App from "./App";

const order = {
  order_id: "ORD-081",
  customer: "Harbor Knits",
  product: "crewneck sweaters",
  category: "TOPS",
  pieces: 1500,
  due_date: "2026-04-13",
  status: "IN_PROGRESS",
  current_stage: "KNITTING",
  order_date: "2026-03-20",
  last_activity_date: "2026-04-01",
};
const pending = {
  session_id: "session_test",
  request_id: "req_test",
  status: "clarification",
  message: "请补充截止日期。",
  parsed: {
    order_id: "ORD-081",
    pieces: 1500,
    due_date: null,
    excluded_workshops: [],
    preferred_workshop: null,
    constraints: [],
  },
  recommendation: null,
  clarification: { fields: ["due_date"], options: [] },
  trace: [],
  provider: "rules",
  created_at: "2026-10-28T01:00:00Z",
};
let chats: Record<string, unknown>[] = [];
let rejectChat = false;
beforeEach(() => {
  localStorage.clear();
  chats = [];
  rejectChat = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      let data: unknown;
      if (path === "/api/health")
        data = {
          status: "ok",
          mode: "rules",
          data: { orders: 1, workshops: 1, requests: 1 },
          reference_date: "2026-04-01",
          version: "1",
        };
      else if (path === "/api/orders") data = { items: [order] };
      else if (path === "/api/workshops")
        data = {
          items: [
            {
              workshop_id: "W2",
              name: "SteadyHands",
              makes: "TOPS+ACCESSORIES",
              status: "ACTIVE",
              capacity_pieces_per_day: 170,
              current_queue_days: 2.5,
              pickup_lead_days: 2,
              cost_per_piece: 1.3,
              defect_rate: 0.03,
              notes: "steady",
              max_batch_pieces: null,
            },
          ],
        };
      else if (path === "/api/requests")
        data = {
          items: [
            {
              id: "R21",
              time: "09:33",
              sender: "Chen",
              message: "ORD-081, 1500 pieces, due Apr 13.",
            },
          ],
        };
      else if (path === "/api/chat") {
        chats.push(JSON.parse(init?.body as string));
        if (rejectChat) throw new Error("网络连接失败");
        data = pending;
      } else data = { items: [] };
      return { ok: true, json: async () => data };
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("dispatch desk integration", () => {
  it("submits the selected original request with objective and stage settings", async () => {
    render(<App />);
    await screen.findByRole("button", { name: /Chen 09:33/ });
    fireEvent.click(screen.getByRole("button", { name: /Chen 09:33/ }));
    fireEvent.change(screen.getByLabelText("分配目标"), {
      target: { value: "quality" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "分析请求" }));
    await waitFor(() => expect(chats).toHaveLength(1));
    expect(chats[0]).toMatchObject({
      message: "Chen: ORD-081, 1500 pieces, due Apr 13.",
      objective: "quality",
      stages: true,
    });
    await screen.findByText("请补充截止日期。");
  });
  it("resumes clarification in the same session", async () => {
    render(<App />);
    await screen.findByRole("button", { name: /Chen 09:33/ });
    fireEvent.change(screen.getByLabelText("调度请求"), {
      target: { value: "ORD-081 新日期待确认" },
    });
    fireEvent.click(screen.getByRole("button", { name: "分析请求" }));
    await screen.findByText("请补充截止日期。");
    fireEvent.change(screen.getByLabelText("调度请求"), {
      target: { value: "4月15日" },
    });
    fireEvent.click(screen.getByRole("button", { name: "继续分析" }));
    await waitFor(() => expect(chats).toHaveLength(2));
    expect(chats[1].session_id).toBe("session_test");
  });
  it("preserves the unsent draft on network failure and prevents an empty submission", async () => {
    render(<App />);
    await screen.findByRole("button", { name: /Chen 09:33/ });
    expect(screen.getByRole("button", { name: "分析请求" })).toBeDisabled();
    rejectChat = true;
    fireEvent.change(screen.getByLabelText("调度请求"), {
      target: { value: "不要 BudgetWorks" },
    });
    fireEvent.click(screen.getByRole("button", { name: "分析请求" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("调度请求")).toHaveValue("不要 BudgetWorks");
    expect(localStorage.getItem("dispatch-draft")).toBe("不要 BudgetWorks");
  });
  it("starts a fresh session without carrying the prior task into a new request", async () => {
    render(<App />);
    await screen.findByRole("button", { name: /Chen 09:33/ });
    fireEvent.change(screen.getByLabelText("调度请求"), {
      target: { value: "ORD-081" },
    });
    fireEvent.click(screen.getByRole("button", { name: "分析请求" }));
    await screen.findByText("请补充截止日期。");
    fireEvent.click(screen.getByRole("button", { name: "新建调度" }));
    fireEvent.change(screen.getByLabelText("调度请求"), {
      target: { value: "ORD-096" },
    });
    fireEvent.click(screen.getByRole("button", { name: "分析请求" }));
    await waitFor(() => expect(chats).toHaveLength(2));
    expect(chats[1].session_id).toBeUndefined();
  });
  it("uses real order rows to prefill a new dispatch request", async () => {
    render(<App />);
    await screen.findByRole("button", { name: /Chen 09:33/ });
    fireEvent.click(screen.getByRole("button", { name: "订单中心" }));
    fireEvent.click(await screen.findByRole("button", { name: "分析" }));
    expect(screen.getByLabelText("调度请求")).toHaveValue(
      "ORD-081，1500 件，截止 2026-04-13，请推荐合适工坊。",
    );
  });
});
