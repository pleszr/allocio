// Thin fetch client for the Allocio backend. All calls go through `/api/*`,
// which Vite proxies to the FastAPI server in local development. Auth is a
// backend-side stub (fixed dev user), so no token handling is needed here.

import type {
  AssetDetail,
  BalanceHistory,
  CheckInBody,
  CheckInPreview,
  CreateAssetRequest,
  CreateAssetResponse,
  CreateMaintenanceItemRequest,
  CreateTimeBasedCostRequest,
  CreateUsageBasedCostRequest,
  MaintenanceItem,
  TimeBasedCost,
  UsageBasedCost,
  WorkspaceOverview,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// The backend uses Pydantic v2, which serializes Decimal fields as JSON strings
// (e.g. "11341.58"). These keys are money/ratio Decimals in the API contract;
// we coerce them back to numbers at the boundary so the app can treat them as
// numbers everywhere. Integer fields already arrive as JSON numbers.
const DECIMAL_KEYS = new Set([
  "balance",
  "recommended_monthly_allocation",
  "daily_accrual",
  "total_balance",
  "total_recommended_monthly_allocation",
  "amount",
  "amount_per_unit",
  "estimated_cost",
  "km_progress",
  "month_progress",
  "balance_before",
  "balance_after",
  "total_allocation",
  "total_expense",
  "net_bucket_change",
]);

function decimalReviver(key: string, value: unknown): unknown {
  return DECIMAL_KEYS.has(key) && typeof value === "string" ? Number(value) : value;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Is the backend running?");
  }
  if (!res.ok) {
    throw new ApiError(res.status, await errorDetail(res));
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text, decimalReviver) : undefined) as T;
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      // FastAPI validation errors: [{loc, msg, ...}]
      return body.detail
        .map((e) => (e && typeof e === "object" && "msg" in e ? String((e as { msg: unknown }).msg) : ""))
        .filter(Boolean)
        .join("; ");
    }
  } catch {
    /* fall through */
  }
  return `Request failed (${res.status}).`;
}

const body = (data: unknown): RequestInit => ({ body: JSON.stringify(data) });

export const api = {
  // Workspace + detail reads
  listAssets: () => request<WorkspaceOverview>("/assets"),
  getAsset: (id: string) => request<AssetDetail>(`/assets/${id}`),
  getBalanceHistory: (id: string, months = 12) =>
    request<BalanceHistory>(`/assets/${id}/balance-history?months=${months}`),

  // Cost rows
  listTimeBasedCosts: (id: string) => request<TimeBasedCost[]>(`/assets/${id}/time-based-costs`),
  listUsageBasedCosts: (id: string) => request<UsageBasedCost[]>(`/assets/${id}/usage-based-costs`),
  listMaintenanceItems: (id: string) => request<MaintenanceItem[]>(`/assets/${id}/maintenance-items`),

  createTimeBasedCost: (id: string, data: CreateTimeBasedCostRequest) =>
    request<TimeBasedCost>(`/assets/${id}/time-based-costs`, { method: "POST", ...body(data) }),
  updateTimeBasedCost: (id: string, costId: string, data: Partial<TimeBasedCost>) =>
    request<TimeBasedCost>(`/assets/${id}/time-based-costs/${costId}`, { method: "PATCH", ...body(data) }),

  createUsageBasedCost: (id: string, data: CreateUsageBasedCostRequest) =>
    request<UsageBasedCost>(`/assets/${id}/usage-based-costs`, { method: "POST", ...body(data) }),
  updateUsageBasedCost: (id: string, costId: string, data: Partial<UsageBasedCost>) =>
    request<UsageBasedCost>(`/assets/${id}/usage-based-costs/${costId}`, { method: "PATCH", ...body(data) }),

  createMaintenanceItem: (id: string, data: CreateMaintenanceItemRequest) =>
    request<MaintenanceItem>(`/assets/${id}/maintenance-items`, { method: "POST", ...body(data) }),
  updateMaintenanceItem: (id: string, itemId: string, data: Partial<MaintenanceItem>) =>
    request<MaintenanceItem>(`/assets/${id}/maintenance-items/${itemId}`, { method: "PATCH", ...body(data) }),

  // Create asset
  createAsset: (data: CreateAssetRequest) =>
    request<CreateAssetResponse>("/assets", { method: "POST", ...body(data) }),

  // Check-in
  previewCheckIn: (id: string, data: CheckInBody) =>
    request<CheckInPreview>(`/assets/${id}/check-ins/preview`, { method: "POST", ...body(data) }),
  postCheckIn: (id: string, data: CheckInBody) =>
    request<unknown>(`/assets/${id}/check-ins`, { method: "POST", ...body(data) }),
};
