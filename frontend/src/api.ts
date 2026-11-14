let token = "";
export function session(value: string) {
  token = value;
}

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  key?: string,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers: {
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(key ? { "Idempotency-Key": key } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.detail +
        " · HTTP " +
        response.status +
        " · " +
        (data.request_id ?? ""),
    );
  return data;
}

export type User = { login: string; name: string; role: string };
export type Factor = {
  code: string;
  name: string;
  version: number;
  hit: boolean;
  points: number;
  parameters: Record<string, number>;
};
export type Assessment = {
  id: string;
  score: number;
  risk: string;
  methodology: string;
  evaluations: Factor[];
  anomaly: Record<string, unknown>;
};
export type Tx = {
  id: string;
  external_id: string;
  amount: number;
  category: string;
  occurred_at: string;
  customer?: string;
  late: boolean;
  risk?: string;
  score?: number;
};
export type TxDetail = Tx & {
  source: string;
  account: string;
  recipient: string;
  channel: string;
  customer_name: string;
  features: Record<string, unknown>;
  assessments: Assessment[];
  history: Tx[];
};
export type Alert = {
  id: string;
  severity: string;
  amount: number;
  category: string;
  score: number;
  transaction: string;
  case_id: string;
  number: number;
  customer_name: string;
  status: string;
  occurred_at: string;
  evaluations: Factor[];
  anomaly: Record<string, unknown>;
};
export type CaseEntry = {
  id: number;
  kind: string;
  author: string;
  body: string;
  created_at: string;
  revision: number;
  details: Record<string, unknown>;
};
export type Case = {
  id: string;
  number: number;
  customer_name: string;
  status: string;
  assignee: string | null;
  assignee_name: string | null;
  revision: number;
  priority: number;
  due_at: string;
  closed_at: string | null;
  overdue: boolean;
  triage_overdue: boolean;
  entries: CaseEntry[];
  alerts: Alert[];
};
export type RuleVersion = {
  id: string;
  version: number;
  status: string;
  author: string;
  reason: string;
  publisher: string | null;
  parameters: Record<string, number>;
};
export type Rule = {
  code: string;
  name: string;
  enabled: boolean;
  versions: RuleVersion[];
  parameters: Record<string, { min: number; max: number; default: number }>;
};
export type RecordRow = Record<string, string | number | null>;
export type Analytics = {
  summary: Record<string, number | null>;
  outcomes: RecordRow[];
  severity: RecordRow[];
  workload: RecordRow[];
  hits: RecordRow[];
};
