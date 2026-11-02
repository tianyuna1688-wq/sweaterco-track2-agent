export type Objective =
  | "lateness"
  | "quality"
  | "fairness"
  | "robustness"
  | "hybrid";
export type Page =
  | "desk"
  | "orders"
  | "workshops"
  | "history"
  | "evaluation"
  | "settings";
export interface Order {
  order_id: string;
  customer: string;
  product: string;
  category: string;
  pieces: number;
  due_date: string;
  status: string;
  current_stage: string;
  order_date: string;
  last_activity_date: string;
}
export interface Workshop {
  workshop_id: string;
  name: string;
  capacity_pieces_per_day: number;
  pickup_lead_days: number;
  defect_rate: number;
  cost_per_piece: number;
  makes: string;
  status: string;
  max_batch_pieces: number | null;
  current_queue_days: number;
  notes: string;
  stages?: string;
}
export interface DispatchRequest {
  id: string;
  time: string;
  sender: string;
  message: string;
}
export interface Candidate {
  workshop_id: string;
  name: string;
  eligible: boolean;
  reasons: string[];
  queue_days: number;
  processing_days: number;
  lead_days: number;
  expected_days: number;
  optimistic_date: string;
  expected_date: string;
  rework_date: string;
  cost: number;
  defect_rate: number;
  on_time: boolean;
  score: (number | string)[] | null;
}
export interface Recommendation {
  candidates: Candidate[];
  recommended: Candidate | null;
  earliest_date: string | null;
  feasibility: string;
  assumptions: string[];
  options: string[];
  preferred_refusal: {
    workshop_id: string;
    name: string;
    reasons: string[];
  } | null;
  split_plan?: {
    parts: {
      workshop_id: string;
      name: string;
      pieces: number;
      expected_date: string;
      cost: number;
    }[];
    expected_date: string;
    cost: number;
    note: string;
    on_time: boolean;
  } | null;
  ranking_explanation?: string;
  objective?: string;
}
export interface ChatResult {
  session_id: string;
  request_id: string;
  status: string;
  message: string;
  input?: string;
  parsed: {
    order_id: string | null;
    pieces: number | null;
    due_date: string | null;
    excluded_workshops: string[];
    preferred_workshop: string | null;
    constraints: {
      type: string;
      value: unknown;
      source: string;
      scope: string;
    }[];
    allow_split?: boolean;
    objective?: string;
  };
  recommendation: Recommendation | null;
  clarification: { fields: string[]; options?: unknown[] } | null;
  trace: {
    step: string;
    status: string;
    detail: string;
    duration_ms?: number;
  }[];
  provider: string;
  provider_warning?: string | null;
  created_at: string;
}
export interface Health {
  status: string;
  mode: string;
  reference_date: string;
  data: { orders: number; workshops: number; requests: number };
  version: string;
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    let message = "服务暂时不可用，请稍后重试。";
    try {
      const e = await response.json();
      message =
        e.error?.message ?? (typeof e.detail === "string" ? e.detail : message);
    } catch {
      /* response may not be JSON */
    }
    throw new Error(message);
  }
  return response.json();
}
