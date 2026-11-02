import { useEffect, useState, type FormEvent } from "react";
import {
  LayoutDashboard,
  Package,
  Factory,
  History,
  ChartNoAxesCombined,
  Settings,
  ArrowUpRight,
  ArrowRight,
  ArrowDownToLine,
  Plus,
  Search,
  Command,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  Clock3,
  ShieldCheck,
  Sparkles,
  Send,
  SlidersHorizontal,
  PanelLeftClose,
  RefreshCw,
  X,
  AlertTriangle,
  LoaderCircle,
  Layers3,
  Network,
  ExternalLink,
} from "lucide-react";
import {
  api,
  type Page,
  type Objective,
  type Order,
  type Workshop,
  type DispatchRequest,
  type Candidate,
  type ChatResult,
  type Health,
} from "./types";

const objectives: Record<Objective, string> = {
  lateness: "交期优先",
  quality: "品质优先",
  fairness: "均衡分配",
  robustness: "抗风险",
  hybrid: "综合平衡",
};
const stateLabels: Record<string, string> = {
  recommended: "已生成建议",
  clarification: "待补充信息",
  infeasible: "交期不可行",
  refused: "指定工坊不可用",
  unanswerable: "数据无法回答",
};
const stages: Record<string, string> = {
  KNITTING: "针织",
  ASSEMBLY: "缝合",
  WASHING: "洗整",
  PACKING: "包装",
  COMPLETE: "已完成",
};
const navItems = [
  { id: "desk", name: "调度工作台", icon: LayoutDashboard },
  { id: "orders", name: "订单中心", icon: Package },
  { id: "workshops", name: "合作工坊", icon: Factory },
  { id: "history", name: "决策记录", icon: History },
  { id: "evaluation", name: "评估实验室", icon: ChartNoAxesCombined },
] as const;
const n = (value: number | undefined, digits = 0) =>
  value === undefined
    ? "—"
    : value.toLocaleString("zh-CN", { maximumFractionDigits: digits });
const shortDate = (value: string | null | undefined) =>
  value ? value.slice(5).replace("-", " / ") : "—";
function exportJSON(value: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
function Badge({
  status,
  children,
}: {
  status?: string;
  children?: React.ReactNode;
}) {
  return (
    <span className={"badge " + (status ?? "neutral")}>
      {children ?? stateLabels[status ?? ""] ?? status}
    </span>
  );
}
function Empty({ title, description }: { title: string; description: string }) {
  return (
    <div className="empty-state">
      <Network size={38} strokeWidth={1.2} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
function CandidateTable({
  candidates,
  recommended,
}: {
  candidates: Candidate[];
  recommended: string | undefined;
}) {
  return (
    <div className="table-scroll">
      <table className="candidate-table">
        <thead>
          <tr>
            <th>候选工坊</th>
            <th>期望交付</th>
            <th>成本¹</th>
            <th>缺陷概率</th>
            <th>资格与交期</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c) => (
            <tr
              key={c.workshop_id}
              className={c.workshop_id === recommended ? "selected-row" : ""}
            >
              <td>
                <span className="workshop-id">{c.workshop_id}</span>
                <strong>{c.name}</strong>
                {c.workshop_id === recommended && <Check size={14} />}
              </td>
              <td>{shortDate(c.expected_date)}</td>
              <td>{n(c.cost, 2)}</td>
              <td>{n(c.defect_rate * 100, 1)}%</td>
              <td>
                {!c.eligible ? (
                  <span className="reason-text">{c.reasons.join("；")}</span>
                ) : (
                  <Badge status={c.on_time ? "recommended" : "infeasible"}>
                    {c.on_time ? "期望按时" : "预计延迟"}
                  </Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function ResultPanel({
  result,
  onClarify,
}: {
  result: ChatResult | null;
  onClarify: (text: string) => void;
}) {
  if (!result)
    return (
      <div className="result-placeholder">
        <div className="orbit">
          <div />
          <Network size={37} strokeWidth={1.2} />
        </div>
        <span className="eyebrow">A DECISION YOU CAN TRACE</span>
        <h2>让数据，给出下一步。</h2>
        <p>
          选择一条调度请求，或描述你的需求。
          <br />
          逐一核对资格、队列与交期，再给出建议。
        </p>
        <div className="steps">
          <span>
            <ShieldCheck size={17} />
            核对硬约束
          </span>
          <span>
            <Clock3 size={17} />
            计算交期
          </span>
          <span>
            <Layers3 size={17} />
            比较方案
          </span>
        </div>
        <div className="source-note">
          <i />
          已连接官方 Track 2 数据 · 120 个订单 / 8 家工坊
        </div>
      </div>
    );
  const rec = result.recommendation;
  const chosen = rec?.recommended;
  return (
    <div className="result-body" aria-live="polite">
      <div className="result-heading">
        <span className="eyebrow">DECISION BRIEF</span>
        <Badge status={result.status} />
      </div>
      <h2>
        {chosen
          ? chosen.name
          : result.status === "clarification"
            ? "再确认一点，就能继续。"
            : result.status === "infeasible"
              ? "这个交期，当前无法满足。"
              : result.status === "unanswerable"
                ? "当前数据无法支持这个判断。"
                : "需要调整指定工坊。"}
      </h2>
      <p className="answer-text">{result.message}</p>
      {result.provider_warning && (
        <div className="warning-box">
          <AlertTriangle size={17} />
          <span>{result.provider_warning}</span>
        </div>
      )}
      {chosen && (
        <>
          <div className="recommendation-summary">
            <div>
              <span>期望交付日</span>
              <strong>
                {shortDate(chosen.expected_date)}
                <small>2026</small>
              </strong>
              <span className="positive">
                {chosen.on_time ? "在请求交期内" : "存在延期风险"}
              </span>
            </div>
            <div>
              <span>预计加工成本¹</span>
              <strong>
                {n(chosen.cost, 2)}
                <small>成本单位</small>
              </strong>
              <span>来自工坊单价 × 批量</span>
            </div>
            <div>
              <span>批次缺陷概率</span>
              <strong>
                {n(chosen.defect_rate * 100, 1)}
                <small>%</small>
              </strong>
              <span>返工情景另行展示</span>
            </div>
          </div>
          <div className="delivery-strip">
            <span>
              <i className="dot" />
              无缺陷 {shortDate(chosen.optimistic_date)}
            </span>
            <span>
              <i className="dot orange" />
              期望 {shortDate(chosen.expected_date)}
            </span>
            <span>
              <i className="dot red" />
              若返工 {shortDate(chosen.rework_date)}
            </span>
          </div>
        </>
      )}
      {result.status === "clarification" && (
        <div className="clarify-box">
          <CircleHelp size={19} />
          <div>
            <strong>补充信息后在下方继续回复</strong>
            <p>本次任务的已知字段和约束会保留。</p>
            {result.clarification?.options?.slice(0, 8).map((v, i) => {
              const option = v as {
                order_id?: string;
                customer?: string;
                pieces?: number;
                due_date?: string;
              };
              const text =
                typeof v === "string"
                  ? v
                  : (option.order_id ?? JSON.stringify(v));
              const label =
                typeof v === "string"
                  ? v
                  : `${option.order_id} · ${option.customer} · ${option.pieces} 件`;
              return (
                <button key={i} onClick={() => onClarify(text)}>
                  {label}
                  <ArrowUpRight size={13} />
                </button>
              );
            })}
          </div>
        </div>
      )}
      {rec?.earliest_date && !chosen && (
        <div className="warning-box">
          <Clock3 size={20} />
          <span>
            最早无缺陷交付日期 <strong>{rec.earliest_date}</strong> ·
            估计值，不是承诺
          </span>
        </div>
      )}
      {rec && (
        <>
          <div className="section-line">
            <h3>
              候选对比 <span>{rec.candidates.length}</span>
            </h3>
            <small>所有数字由规则引擎计算</small>
          </div>
          <CandidateTable
            candidates={rec.candidates}
            recommended={chosen?.workshop_id}
          />
          <p className="footnote">
            ¹
            原始数据未定义币种；按统一成本单位展示。不合格工坊的数值仅供情景比较，不表示可以接单。
          </p>
          {rec.options.length > 0 && (
            <div className="options-box">
              <h4>下一步选项</h4>
              {rec.options.map((v, i) => (
                <p key={i}>
                  <ArrowRight size={13} />
                  {v}
                </p>
              ))}
            </div>
          )}
          {rec.split_plan != null && (
            <details className="detail-row">
              <summary>查看拆单提案 · 仅供讨论</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>工坊</th>
                      <th>批量</th>
                      <th>期望交付</th>
                      <th>成本</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rec.split_plan.parts.map((part) => (
                      <tr key={part.workshop_id}>
                        <td>{part.name}</td>
                        <td>{n(part.pieces)} 件</td>
                        <td>{part.expected_date}</td>
                        <td>{n(part.cost, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p>
                整批期望完成：{rec.split_plan.expected_date} · 总成本{" "}
                {n(rec.split_plan.cost, 2)}
              </p>
              <p>{rec.split_plan.note}</p>
            </details>
          )}
          <details className="detail-row">
            <summary>计算依据与风险假设</summary>
            <p>{rec.ranking_explanation}</p>
            {rec.assumptions.map((v, i) => (
              <p key={i}>{v}</p>
            ))}
            <p>期望时间 = 队列 + 件数 ÷ 日产能 × (1 + 0.5 × 缺陷率) + 运输。</p>
          </details>
        </>
      )}
      <details className="detail-row">
        <summary>解析字段与约束来源</summary>
        <p>
          订单：{result.parsed.order_id ?? "待明确"} · 批量：
          {n(result.parsed.pieces ?? undefined)} · 交期：
          {result.parsed.due_date ?? "待明确"}
        </p>
        <p>
          实际策略：
          {(
            {
              ...objectives,
              fastest: "最快周转",
              cheapest_on_time: "按时前提下最低成本",
            } as Record<string, string>
          )[result.parsed.objective ?? "lateness"] ?? result.parsed.objective}
        </p>
        {result.parsed.constraints.length ? (
          result.parsed.constraints.map((c, i) => (
            <p key={i}>
              {(
                {
                  exclude: "排除工坊",
                  prefer: "指定工坊",
                  objective: "目标偏好",
                  allow_split: "允许拆单",
                } as Record<string, string>
              )[c.type] ?? c.type}
              ：{String(c.value)} · 提出者：{c.source} · 仅本次任务
            </p>
          ))
        ) : (
          <p>没有额外的任务约束。</p>
        )}
      </details>
      <details className="detail-row">
        <summary>
          工具执行轨迹 <span>{result.trace.length} 步</span>
        </summary>
        <div className="trace-list">
          {result.trace.map((t, i) => (
            <div key={i}>
              <CheckCheck size={15} />
              <strong>{t.step}</strong>
              <span>{t.detail}</span>
              <small>
                {t.duration_ms !== undefined ? t.duration_ms + " ms" : ""}
              </small>
            </div>
          ))}
        </div>
      </details>
      <div className="result-footer">
        <ShieldCheck size={13} />
        建议已留存审计 · {result.provider === "rules" ? "规则解析" : "模型解析"}
        <button onClick={() => exportJSON(result, `${result.request_id}.json`)}>
          <ArrowDownToLine size={14} />
          导出决策
        </button>
      </div>
    </div>
  );
}
export default function App() {
  const [page, setPage] = useState<Page>("desk");
  const [orders, setOrders] = useState<Order[]>([]);
  const [workshops, setWorkshops] = useState<Workshop[]>([]);
  const [requests, setRequests] = useState<DispatchRequest[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState(
    () => localStorage.getItem("dispatch-draft") ?? "",
  );
  const [objective, setObjective] = useState<Objective>("lateness");
  const [useStages, setUseStages] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [result, setResult] = useState<ChatResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [requestFilter, setRequestFilter] = useState("all");
  const [responses, setResponses] = useState<Record<string, ChatResult>>({});
  const [history, setHistory] = useState<ChatResult[]>([]);
  const [sidebar, setSidebar] = useState(false);
  const [orderFilter, setOrderFilter] = useState("all");
  const [orderSort, setOrderSort] = useState("due_date");
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  // Independent reads fail visibly; keep the draft intact for retries.
  async function load() {
    setError("");
    try {
      const [h, o, w, r, a] = await Promise.all([
        api<Health>("/health"),
        api<{ items: Order[] }>("/orders"),
        api<{ items: Workshop[] }>("/workshops"),
        api<{ items: DispatchRequest[] }>("/requests"),
        api<{ items: ChatResult[] }>("/history?limit=500"),
      ]);
      const restored: Record<string, ChatResult> = {};
      for (const req of r.items) {
        const old = a.items.find(
          (v) => v.input === `${req.sender}: ${req.message}`,
        );
        if (old)
          restored[req.id] =
            a.items.find((v) => v.session_id === old.session_id) ?? old;
      }
      setResponses(restored);
      setHealth(h);
      setOrders(o.items);
      setWorkshops(w.items);
      setRequests(r.items);
      setReady(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  useEffect(() => {
    localStorage.setItem("dispatch-draft", draft);
  }, [draft]);
  useEffect(() => {
    setSearch("");
    setSidebar(false);
    if (page === "history")
      api<{ items: ChatResult[] }>("/history")
        .then((v) => setHistory(v.items))
        .catch((e) => setError(e.message));
    if (page === "settings")
      api<Record<string, unknown>>("/settings")
        .then(setSettings)
        .catch((e) => setError(e.message));
  }, [page]);
  function newRequest() {
    setSelected(null);
    setSessionId(undefined);
    setResult(null);
    setDraft("");
    setError("");
    setPage("desk");
  }
  function choose(r: DispatchRequest) {
    setSelected(r.id);
    setSessionId(responses[r.id]?.session_id);
    setResult(responses[r.id] ?? null);
    setDraft(`${r.sender}: ${r.message}`);
    setError("");
  }
  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!draft.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await api<ChatResult>("/chat", {
        method: "POST",
        body: JSON.stringify({
          message: draft,
          session_id: sessionId,
          objective,
          stages: useStages,
        }),
      });
      setResult(response);
      setSessionId(response.session_id);
      if (selected) setResponses((v) => ({ ...v, [selected]: response }));
      setDraft("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const active = workshops.filter((w) => w.status === "ACTIVE");
  const selectedOrder = orders.find(
    (o) => o.order_id === result?.parsed.order_id,
  );
  const currentRequest = requests.find((r) => r.id === selected);
  const filteredRequests = requests.filter(
    (r) =>
      (requestFilter === "all" ||
        (requestFilter === "done" ? !!responses[r.id] : !responses[r.id])) &&
      `${r.id} ${r.message} ${r.sender}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <div className="app-shell">
      <aside className={"sidebar " + (sidebar ? "open" : "")}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("desk");
          }}
        >
          <div className="brand-mark">
            <span />
            <span />
            <span />
            <span />
          </div>
          <div>
            <strong>
              SweaterCo<span>®</span>
            </strong>
            <small>OPERATIONS STUDIO</small>
          </div>
        </a>
        <div className="workspace-switch">
          <span className="workspace-logo">S</span>
          <div>
            <strong>外包调度中心</strong>
            <small>Track 2 · 工作空间</small>
          </div>
          <ChevronRight size={14} />
        </div>
        <p className="nav-caption">工作空间</p>
        <nav>
          {navItems.map((item) => (
            <button
              key={item.id}
              className={page === item.id ? "active" : ""}
              onClick={() => setPage(item.id)}
            >
              <item.icon size={18} />
              {item.name}
              {item.id === "desk" && (
                <span className="nav-count">{requests.length || "—"}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="data-status">
            <span className="status-led" />
            <strong>官方数据 · v3</strong>
            <p>真实规则，可溯源的每一次决策。</p>
            <small>业务参考日 2026.04.01</small>
          </div>
          <button
            className={"settings-link " + (page === "settings" ? "active" : "")}
            onClick={() => setPage("settings")}
          >
            <Settings size={18} />
            系统与设置
            <ArrowUpRight size={14} />
          </button>
          <div className="user">
            <span>调</span>
            <div>
              <strong>本地调度员</strong>
              <small>单用户工作空间</small>
            </div>
            <ShieldCheck size={17} />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="mobile-menu icon-button"
              aria-label="打开导航"
              onClick={() => setSidebar(!sidebar)}
            >
              <PanelLeftClose size={19} />
            </button>
            <span className="breadcrumb">工作空间</span>
            <ChevronRight size={13} />
            <strong>
              {page === "settings"
                ? "系统与设置"
                : navItems.find((v) => v.id === page)?.name}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="environment-label">
              <span className={health ? "status-led" : "status-led offline"} />
              {health ? "本地服务已连接" : "正在连接服务"}
            </span>
            <span className="date-label">
              2026 年 4 月 1 日 <small>数据参考日</small>
            </span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                SWEATERCO /{" "}
                {page === "desk" ? "DISPATCH INTELLIGENCE" : page.toUpperCase()}
              </div>
              <h1>
                {page === "desk"
                  ? "每一次分配，都有据可依。"
                  : page === "orders"
                    ? "订单全貌，一目了然。"
                    : page === "workshops"
                      ? "找到合适的生产伙伴。"
                      : page === "history"
                        ? "决策有记录，依据可回溯。"
                        : page === "evaluation"
                          ? "用真实结果，检验每个策略。"
                          : "连接、规则与运行状态。"}
              </h1>
              <p>
                {page === "desk"
                  ? "从一条群聊消息，到一个可信的调度建议。"
                  : page === "orders"
                    ? "120 个原始订单 · 厂内状态与外包回放分别理解"
                    : page === "workshops"
                      ? "8 家工坊的产能、队列、质量与资格，直接来自官方档案。"
                      : page === "history"
                        ? "查看原始请求、解析字段、工具轨迹与每次建议。"
                        : page === "evaluation"
                          ? "官方 30 条请求 + 120 单回放 · 同一数据，同一模拟器。"
                          : "可配置的模型理解，确定性的业务规则。"}
              </p>
            </div>
            {page === "desk" ? (
              <button className="primary" disabled={busy} onClick={newRequest}>
                <Plus size={17} />
                新建调度
              </button>
            ) : (
              <button
                className="button"
                onClick={() => {
                  setPage("desk");
                }}
              >
                <ArrowUpRight size={16} />
                返回工作台
              </button>
            )}
          </div>
          {error && (
            <div className="error-banner" role="alert">
              <AlertTriangle size={18} />
              <span>{error}</span>
              {!ready && <button onClick={() => void load()}>重新连接</button>}
              <button aria-label="关闭错误提示" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {!ready && !error ? (
            <div className="loading">
              <LoaderCircle className="spin" />
              正在读取真实业务数据…
            </div>
          ) : (
            <>
              {page === "desk" && (
                <>
                  <div className="stats-grid">
                    <Stat
                      label="今日调度收件箱"
                      value={requests.length}
                      unit="条"
                      icon={<Command />}
                      note="官方群聊 · 待逐条处理"
                    />
                    <Stat
                      label="在册订单"
                      value={orders.length}
                      unit="个"
                      icon={<Package />}
                      note={`${orders.filter((o) => o.status === "IN_PROGRESS").length} 个订单仍在生产中`}
                    />
                    <Stat
                      label="可合作工坊"
                      value={active.length}
                      unit={`/ ${workshops.length}`}
                      icon={<Factory />}
                      note="1 家暂停 · 1 家有批量限制"
                    />
                    <Stat
                      label="决策方式"
                      text={health?.mode === "rules" ? "规则模式" : "模型辅助"}
                      icon={<ShieldCheck />}
                      note="资格、交期和成本由代码核算"
                    />
                  </div>
                  <div className="desk-layout">
                    <section className="inbox panel">
                      <div className="panel-heading">
                        <div>
                          <h2>
                            调度收件箱 <span>{requests.length}</span>
                          </h2>
                          <p>4 月 1 日 · 群聊请求</p>
                        </div>
                        <span className="tiny-dot" />
                      </div>
                      <div className="searchbox">
                        <Search size={15} />
                        <input
                          aria-label="搜索调度请求"
                          placeholder="搜索订单、客户或请求…"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </div>
                      <div className="segmented">
                        {[
                          ["all", "全部"],
                          ["pending", "未分析"],
                          ["done", "已分析"],
                        ].map(([id, label]) => (
                          <button
                            className={requestFilter === id ? "active" : ""}
                            key={id}
                            onClick={() => setRequestFilter(id)}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                      <div className="inbox-list">
                        {filteredRequests.length ? (
                          filteredRequests.map((r) => (
                            <button
                              className={
                                "request-item " +
                                (selected === r.id ? "selected" : "")
                              }
                              key={r.id}
                              disabled={busy}
                              onClick={() => choose(r)}
                            >
                              <div className="request-top">
                                <span
                                  className={
                                    "avatar avatar-" + (r.sender.length % 4)
                                  }
                                >
                                  {r.sender[0]}
                                </span>
                                <strong>{r.sender}</strong>
                                <small>{r.time}</small>
                              </div>
                              <p>{r.message}</p>
                              <div className="request-bottom">
                                <span>
                                  {r.id} <span>·</span>{" "}
                                  {
                                    (r.message.match(/ORD-\d+/) || [
                                      "待明确订单",
                                    ])[0]
                                  }
                                </span>
                                {responses[r.id] ? (
                                  <Badge status={responses[r.id].status} />
                                ) : (
                                  <span className="unread-label">
                                    <i />
                                    待分析
                                  </span>
                                )}
                              </div>
                            </button>
                          ))
                        ) : (
                          <Empty
                            title="没有匹配的请求"
                            description="换一个关键词，或切换筛选条件。"
                          />
                        )}
                      </div>
                      <div className="inbox-foot">
                        <ShieldCheck size={13} />
                        原始请求只读 · 不自动下单
                      </div>
                    </section>
                    <section className="decision panel">
                      <div className="decision-toolbar">
                        <div className="assistant-icon">
                          <Sparkles size={19} />
                        </div>
                        <div>
                          <strong>
                            调度助手 <span>AGENT</span>
                          </strong>
                          <small>
                            {currentRequest
                              ? `${currentRequest.id} · ${currentRequest.sender} 的请求`
                              : "准备好处理下一条请求"}
                          </small>
                        </div>
                        <div className="toolbar-right">
                          <span className="small-label">策略</span>
                          <select
                            aria-label="分配目标"
                            disabled={busy}
                            value={objective}
                            onChange={(e) =>
                              setObjective(e.target.value as Objective)
                            }
                          >
                            {Object.entries(objectives).map(([v, label]) => (
                              <option key={v} value={v}>
                                {label}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                      {result?.parsed.order_id && (
                        <div className="order-context">
                          <span className="context-id">
                            <Package size={14} />
                            {result.parsed.order_id}
                          </span>
                          <span>{selectedOrder?.customer ?? "订单信息"}</span>
                          <span>{n(result.parsed.pieces ?? undefined)} 件</span>
                          <span>截止 {shortDate(result.parsed.due_date)}</span>
                          {result.parsed.excluded_workshops?.length > 0 && (
                            <Badge status="refused">
                              排除 {result.parsed.excluded_workshops.join("、")}
                            </Badge>
                          )}
                        </div>
                      )}
                      <div className="decision-scroll">
                        <ResultPanel result={result} onClarify={setDraft} />
                      </div>
                      <form className="composer" onSubmit={submit}>
                        <div className="composer-box">
                          <textarea
                            aria-label="调度请求"
                            value={draft}
                            placeholder={
                              result?.status === "clarification"
                                ? "补充订单编号、件数或截止日期，继续本次分析…"
                                : "例如：ORD-081，1500 件，4 月 13 日前交货，选能按时的最便宜工坊。"
                            }
                            onChange={(e) => setDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (
                                e.key === "Enter" &&
                                (e.metaKey || e.ctrlKey)
                              ) {
                                e.preventDefault();
                                void submit();
                              }
                            }}
                            maxLength={8000}
                          />
                          <div className="composer-actions">
                            <label className="stage-toggle">
                              <input
                                type="checkbox"
                                disabled={busy}
                                checked={useStages}
                                onChange={(e) => setUseStages(e.target.checked)}
                              />
                              <Layers3 size={14} />
                              工序约束 <small>可选扩展</small>
                            </label>
                            <button
                              className="primary send-button"
                              type="submit"
                              disabled={busy || !draft.trim()}
                            >
                              {busy ? (
                                <LoaderCircle className="spin" size={16} />
                              ) : (
                                <Send size={16} />
                              )}
                              <span>
                                {busy
                                  ? "正在分析…"
                                  : result?.status === "clarification"
                                    ? "继续分析"
                                    : "分析请求"}
                              </span>
                            </button>
                          </div>
                        </div>
                        <div className="composer-hint">
                          <span>建议模式 · 所有结论可追溯</span>
                          <span>⌘ / Ctrl + Enter 发送</span>
                        </div>
                      </form>
                    </section>
                  </div>
                  <div className="desk-footnote">
                    <ShieldCheck size={14} />
                    <span>
                      资格先行，数据为据。系统只生成建议和审计记录，实际派单由调度员决定。
                    </span>
                    <button onClick={() => setPage("evaluation")}>
                      查看评估依据
                      <ArrowUpRight size={14} />
                    </button>
                  </div>
                </>
              )}
              {page === "orders" && (
                <section className="panel data-panel">
                  <div className="list-toolbar">
                    <div className="searchbox">
                      <Search size={16} />
                      <input
                        aria-label="搜索订单"
                        placeholder="搜索订单编号、客户、产品…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </div>
                    <select
                      aria-label="订单状态"
                      value={orderFilter}
                      onChange={(e) => setOrderFilter(e.target.value)}
                    >
                      <option value="all">全部状态</option>
                      <option value="IN_PROGRESS">生产中</option>
                      <option value="COMPLETE">已完成</option>
                    </select>
                    <select
                      aria-label="订单排序"
                      value={orderSort}
                      onChange={(e) => setOrderSort(e.target.value)}
                    >
                      <option value="due_date">按截止日期</option>
                      <option value="order_id">按订单编号</option>
                      <option value="pieces">按批量降序</option>
                    </select>
                    <button
                      className="button"
                      onClick={() => exportJSON(orders, "orders.json")}
                    >
                      <ArrowDownToLine size={15} />
                      导出数据
                    </button>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>订单编号</th>
                          <th>客户 / 产品</th>
                          <th>批量</th>
                          <th>交付日期</th>
                          <th>当前工序</th>
                          <th>厂内状态</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {orders
                          .filter(
                            (o) =>
                              (orderFilter === "all" ||
                                o.status === orderFilter) &&
                              `${o.order_id} ${o.customer} ${o.product}`
                                .toLowerCase()
                                .includes(search.toLowerCase()),
                          )
                          .sort((a, b) =>
                            orderSort === "pieces"
                              ? b.pieces - a.pieces
                              : String(
                                  a[orderSort as keyof Order],
                                ).localeCompare(
                                  String(b[orderSort as keyof Order]),
                                ),
                          )
                          .map((o) => (
                            <tr key={o.order_id}>
                              <td className="mono">{o.order_id}</td>
                              <td>
                                <strong>{o.customer}</strong>
                                <small className="table-sub">{o.product}</small>
                              </td>
                              <td>
                                {n(o.pieces)} <small>件</small>
                              </td>
                              <td>{o.due_date}</td>
                              <td>{stages[o.current_stage]}</td>
                              <td>
                                <Badge
                                  status={
                                    o.status === "COMPLETE"
                                      ? "neutral"
                                      : "recommended"
                                  }
                                >
                                  {o.status === "COMPLETE"
                                    ? "已完成"
                                    : "生产中"}
                                </Badge>
                              </td>
                              <td>
                                <button
                                  className="text-button"
                                  disabled={o.status === "COMPLETE"}
                                  onClick={() => {
                                    newRequest();
                                    setDraft(
                                      `${o.order_id}，${o.pieces} 件，截止 ${o.due_date}，请推荐合适工坊。`,
                                    );
                                  }}
                                >
                                  分析
                                  <ArrowUpRight size={14} />
                                </button>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="table-footer">
                    来源：orders.csv · 120 条原始记录 · 已完成订单仅供查询与回放
                  </p>
                </section>
              )}
              {page === "workshops" && (
                <>
                  <div className="workshop-intro">
                    <ShieldCheck size={19} />
                    <p>
                      资格判断同时检查产品类别、ACTIVE
                      状态和单批上限。开启工序扩展后，还检查全部剩余工序。
                    </p>
                  </div>
                  <div className="workshop-grid">
                    {workshops.map((w) => (
                      <article
                        className={
                          "panel workshop-card " +
                          (w.status === "SUSPENDED" ? "suspended" : "")
                        }
                        key={w.workshop_id}
                      >
                        <div className="workshop-card-top">
                          <span className="factory-icon">
                            <Factory size={24} />
                          </span>
                          <Badge
                            status={
                              w.status === "ACTIVE"
                                ? "recommended"
                                : "infeasible"
                            }
                          >
                            {w.status === "ACTIVE" ? "可接单" : "已暂停"}
                          </Badge>
                        </div>
                        <div className="workshop-title">
                          <span>{w.workshop_id}</span>
                          <h2>{w.name}</h2>
                        </div>
                        <p className="workshop-notes">{w.notes}</p>
                        <div className="capability-tags">
                          {w.makes.split("+").map((s) => (
                            <span key={s}>
                              {s === "TOPS" ? "针织上装" : "配饰"}
                            </span>
                          ))}
                          {w.max_batch_pieces && (
                            <span>≤ {w.max_batch_pieces} 件 / 批</span>
                          )}
                        </div>
                        <div className="workshop-metrics">
                          <div>
                            <small>日产能</small>
                            <strong>
                              {w.capacity_pieces_per_day}
                              <span> 件</span>
                            </strong>
                          </div>
                          <div>
                            <small>当前队列</small>
                            <strong>
                              {w.current_queue_days}
                              <span> 天</span>
                            </strong>
                          </div>
                          <div>
                            <small>缺陷概率</small>
                            <strong>
                              {n(w.defect_rate * 100, 1)}
                              <span> %</span>
                            </strong>
                          </div>
                        </div>
                        <div className="queue-bar">
                          <span
                            style={{
                              width:
                                Math.min(
                                  (w.current_queue_days / 5) * 100,
                                  100,
                                ) + "%",
                            }}
                          />
                        </div>
                        <div className="workshop-bottom">
                          <span>
                            单件成本 <b>{w.cost_per_piece}</b>
                          </span>
                          <span>
                            运输 <b>{w.pickup_lead_days} 天</b>
                          </span>
                        </div>
                      </article>
                    ))}
                  </div>
                  <p className="footnote">
                    来源：workshops.csv · 队列以 2026-04-01 早晨解释 ·
                    原始数据不含币种，价格按统一成本单位展示。
                  </p>
                </>
              )}
              {page === "history" && (
                <section className="panel history-panel">
                  <div className="panel-heading">
                    <h2>
                      审计时间线 <span>{history.length}</span>
                    </h2>
                    <button
                      className="button"
                      onClick={() =>
                        exportJSON(history, "dispatch-history.json")
                      }
                    >
                      <ArrowDownToLine size={15} />
                      导出记录
                    </button>
                  </div>
                  {history.length ? (
                    history.map((h) => (
                      <details className="history-item" key={h.request_id}>
                        <summary>
                          <span className="history-icon">
                            <History size={17} />
                          </span>
                          <div>
                            <strong>
                              {h.parsed.order_id ?? "待明确订单"}{" "}
                              <small>{h.request_id.slice(0, 16)}</small>
                            </strong>
                            <p>{h.input ?? h.message}</p>
                          </div>
                          <Badge status={h.status} />
                          <time>
                            {new Date(h.created_at).toLocaleString("zh-CN")}
                          </time>
                          <ChevronRight size={16} />
                        </summary>
                        {h.status === "clarification" && (
                          <button
                            className="button history-resume"
                            onClick={() => {
                              setPage("desk");
                              setResult(h);
                              setSelected(null);
                              setSessionId(h.session_id);
                              setDraft("");
                            }}
                          >
                            <ArrowRight size={14} />
                            继续补充此请求
                          </button>
                        )}
                        <ResultPanel
                          result={h}
                          onClarify={(text) => {
                            setPage("desk");
                            setResult(h);
                            setSessionId(h.session_id);
                            setDraft(text);
                          }}
                        />
                      </details>
                    ))
                  ) : (
                    <Empty
                      title="每一次建议，都会留下依据。"
                      description="在工作台分析第一条请求后，可在这里查看完整审计记录。"
                    />
                  )}
                </section>
              )}
              {page === "evaluation" && <Evaluation onError={setError} />}
              {page === "settings" && (
                <div className="settings-grid">
                  <section className="panel settings-card">
                    <div className="section-line">
                      <h2>运行环境</h2>
                      <Badge status="recommended">本地完整平台</Badge>
                    </div>
                    {[
                      ["API 服务", health?.status === "ok" ? "健康" : "待检查"],
                      ["业务参考日期", "2026-04-01"],
                      [
                        "语言理解",
                        settings.mode === "rules"
                          ? "规则模式 · 无需 API Key"
                          : "模型辅助模式",
                      ],
                      ["模型配置", settings.configured ? "已配置" : "未配置"],
                      ["执行权限", "建议与审计 · 不下发订单"],
                      ["会话保留", "澄清状态 24 小时"],
                      ["工作流", "有界状态机"],
                      [
                        "身份模式",
                        settings.auth_mode === "token"
                          ? "受访问令牌保护"
                          : "本地单用户",
                      ],
                    ].map(([key, value]) => (
                      <div className="setting-row" key={String(key)}>
                        <span>{String(key)}</span>
                        <strong>{String(value)}</strong>
                      </div>
                    ))}
                  </section>
                  <section className="panel settings-card">
                    <span className="eyebrow">MODEL CONNECTION</span>
                    <h2>按需接入你的模型。</h2>
                    <p>
                      当前规则模式可直接处理官方请求。接入兼容模型服务后，模型负责结构化理解，所有业务规则仍由后端验证。
                    </p>
                    <div className="code-block">
                      LLM_PROVIDER=openai_compatible
                      <br />
                      LLM_BASE_URL=你的服务地址
                      <br />
                      LLM_MODEL=你的模型名称
                      <br />
                      LLM_API_KEY=仅在服务端填写
                    </div>
                    <p className="footnote">
                      将配置写入项目根目录的
                      .env，然后重启服务。密钥不会发送到浏览器。模型异常会明确回退到规则模式。
                    </p>
                    <a
                      className="button"
                      href="/docs"
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看 API 文档
                      <ExternalLink size={14} />
                    </a>
                  </section>
                  <section className="panel settings-card integrity-card">
                    <ShieldCheck size={24} />
                    <div>
                      <h2>官方数据完整性</h2>
                      <p>
                        源数据与模拟器的 SHA-256 哈希会在后端校验。聊天使用 4 月
                        1 日队列；历史回放从 1 月 1 日开始。两种时间口径独立。
                      </p>
                    </div>
                    <Badge
                      status={
                        health?.status === "ok" ? "recommended" : "infeasible"
                      }
                    >
                      {health?.status === "ok" ? "已校验" : "需检查"}
                    </Badge>
                  </section>
                </div>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              SWEATERCO <b>OPERATIONS STUDIO</b>
            </span>
            <span>Track 2 / Quick-Response Subcontracting Desk</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
function Stat({
  label,
  value,
  unit,
  text,
  icon,
  note,
}: {
  label: string;
  value?: number;
  unit?: string;
  text?: string;
  icon: React.ReactNode;
  note: string;
}) {
  return (
    <div className="stat">
      <div className="stat-top">
        <span>{label}</span>
        {icon}
      </div>
      <div className={"stat-value " + (text ? "stat-text" : "")}>
        {text ?? n(value)}
        <small>{unit}</small>
      </div>
      <div className="stat-note">{note}</div>
    </div>
  );
}
interface EvalRow {
  policy: string;
  label: string;
  metrics: Record<string, number>;
}
interface EvalCase {
  id: string;
  label: string;
  message: string;
  expected_status: string;
  actual_status: string;
  passed: boolean;
  decision_passed: boolean;
  explanation_passed: boolean;
  failures: string[];
}
interface EvalReport {
  generated_at: string;
  mode: string;
  chat: {
    total: number;
    passed: number;
    decision_passed: number;
    explanation_passed: number;
    cases: EvalCase[];
    by_kind: { kind: string; label: string; total: number; passed: number }[];
  };
  simulation: {
    seeds: number[];
    normal: EvalRow[];
    shock: EvalRow[];
    tradeoffs: string[];
  };
  source_integrity: { passed: boolean };
}
function Evaluation({ onError }: { onError: (v: string) => void }) {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [running, setRunning] = useState(false);
  const [scenario, setScenario] = useState("normal");
  const [tab, setTab] = useState("simulation");
  const [caseFilter, setCaseFilter] = useState("all");
  useEffect(() => {
    api<EvalReport>("/evaluations")
      .then(setReport)
      .catch((e) => onError(e.message));
  }, [onError]);
  async function run() {
    setRunning(true);
    try {
      setReport(await api<EvalReport>("/evaluations/run", { method: "POST" }));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }
  return (
    <>
      <div className="eval-toolbar">
        <div className="segmented">
          {[
            ["simulation", "策略回放"],
            ["chat", "请求评估"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={tab === id ? "active" : ""}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <div>
          <button
            className="button"
            disabled={!report}
            onClick={() => exportJSON(report, "evaluation-report.json")}
          >
            <ArrowDownToLine size={15} />
            导出报告
          </button>
          <button
            className="primary"
            disabled={running}
            onClick={() => void run()}
          >
            <RefreshCw size={15} className={running ? "spin" : ""} />
            {running ? "正在运行完整评估…" : "重新运行评估"}
          </button>
        </div>
      </div>
      {report?.chat ? (
        <>
          <div className="stats-grid">
            <Stat
              label="真实请求评估"
              value={report.chat.passed}
              unit={`/ ${report.chat.total}`}
              icon={<CheckCheck />}
              note="结构化行为与解释分别校验"
            />
            <Stat
              label="行为正确"
              value={report.chat.decision_passed}
              unit={`/ ${report.chat.total}`}
              icon={<ShieldCheck />}
              note="追问、拒绝、推荐与不可行"
            />
            <Stat
              label="解释可追溯"
              value={report.chat.explanation_passed}
              unit={`/ ${report.chat.total}`}
              icon={<Layers3 />}
              note="确定性事实与计算结果校验"
            />
            <Stat
              label="回放随机种子"
              value={report.simulation.seeds.length}
              unit="组"
              icon={<ChartNoAxesCombined />}
              note="5105–5114 · 正常 / 停工场景"
            />
          </div>
          <div className="eval-notice">
            <CircleHelp size={17} />
            <p>
              当前为<strong>规则解析模式</strong>
              实测；尚未验证真实模型调用。课程数据上的准确率不代表任意自然语言输入的准确率。
            </p>
          </div>
          {tab === "simulation" ? (
            <>
              <section className="panel data-panel">
                <div className="panel-heading">
                  <div>
                    <h2>同一批订单，不同选择。</h2>
                    <p>主目标：减少迟交 · 官方模拟器未修改 · 默认工序模式</p>
                  </div>
                  <div className="segmented">
                    <button
                      className={scenario === "normal" ? "active" : ""}
                      onClick={() => setScenario("normal")}
                    >
                      正常场景
                    </button>
                    <button
                      className={scenario === "shock" ? "active" : ""}
                      onClick={() => setScenario("shock")}
                    >
                      停工 Shock
                    </button>
                  </div>
                </div>
                <div className="table-scroll">
                  <table className="eval-table">
                    <thead>
                      <tr>
                        <th>分配策略</th>
                        <th>迟交率 ↓</th>
                        <th>平均迟交 ↓</th>
                        <th>平均周转</th>
                        <th>缺陷件数占比</th>
                        <th>总成本¹</th>
                        <th>最高份额</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.simulation[
                        scenario === "normal" ? "normal" : "shock"
                      ].map((r) => (
                        <tr
                          key={r.policy}
                          className={
                            r.policy === "lateness" ? "selected-row" : ""
                          }
                        >
                          <td>
                            <strong>{r.label}</strong>
                            <small className="table-sub">{r.policy}</small>
                          </td>
                          <td>
                            <div className="metric-cell">
                              <strong>{n(r.metrics["% late"], 2)}%</strong>
                              <span>
                                <i
                                  style={{
                                    width:
                                      Math.max(r.metrics["% late"], 1) + "%",
                                  }}
                                />
                              </span>
                            </div>
                          </td>
                          <td>{n(r.metrics["late days"], 3)} 天</td>
                          <td>{n(r.metrics["mean days"], 2)} 天</td>
                          <td>{n(r.metrics["% def pcs"], 2)}%</td>
                          <td>{n(r.metrics.cost)}</td>
                          <td>{n(r.metrics["max share"], 1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="table-footer">
                  每个场景均为 10 个种子的平均值 · Shock 为随机工坊在第 30–44
                  天停工 · 工序扩展独立报告随源代码交付
                </p>
              </section>
              <section className="panel tradeoffs">
                <div className="section-line">
                  <h2>结果之外，还要看取舍。</h2>
                  <SlidersHorizontal size={18} />
                </div>
                {report.simulation.tradeoffs.map((v, i) => (
                  <p key={i}>
                    <span>{String(i + 1).padStart(2, "0")}</span>
                    {v}
                  </p>
                ))}
              </section>
            </>
          ) : (
            <section className="panel data-panel">
              <div className="list-toolbar">
                <h2>30 条请求 · 逐条验证</h2>
                <select
                  aria-label="评估筛选"
                  value={caseFilter}
                  onChange={(e) => setCaseFilter(e.target.value)}
                >
                  <option value="all">全部结果</option>
                  <option value="failed">仅看失败</option>
                </select>
              </div>
              {report.chat.cases
                .filter((c) => caseFilter === "all" || !c.passed)
                .map((c) => (
                  <details className="eval-case" key={c.id}>
                    <summary>
                      <span className="mono">{c.id}</span>
                      <strong>{c.label}</strong>
                      <span>{c.message}</span>
                      <Badge status={c.passed ? "recommended" : "infeasible"}>
                        {c.passed ? "通过" : "失败"}
                      </Badge>
                      <ChevronRight size={14} />
                    </summary>
                    <div>
                      <p>{c.message}</p>
                      <p>
                        预期：
                        {stateLabels[c.expected_status] ?? c.expected_status} ·
                        实际：{stateLabels[c.actual_status] ?? c.actual_status}
                      </p>
                      <p>
                        行为：{c.decision_passed ? "通过" : "未通过"} · 解释：
                        {c.explanation_passed ? "通过" : "未通过"}
                      </p>
                      {c.failures.map((v, i) => (
                        <p key={i}>{v}</p>
                      ))}
                    </div>
                  </details>
                ))}
              {caseFilter === "failed" &&
                !report.chat.cases.some((c) => !c.passed) && (
                  <Empty
                    title="本次评估没有失败项"
                    description="仍需根据新场景继续补充回归用例。"
                  />
                )}
            </section>
          )}
          <p className="footnote">
            报告生成：{new Date(report.generated_at).toLocaleString("zh-CN")} ·
            源文件完整性：{report.source_integrity.passed ? "已通过" : "需检查"}{" "}
            · 标注为工程核验，非外部人工盲评。
          </p>
        </>
      ) : (
        <Empty
          title="正在读取评估报告"
          description="也可以点击重新运行，生成全部请求与模拟器结果。"
        />
      )}
    </>
  );
}
