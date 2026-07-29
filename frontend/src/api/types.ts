// TypeScript mirrors of the backend's Pydantic response/request shapes.
// FastAPI serializes Decimal via jsonable_encoder as JSON numbers, so money
// fields are `number` here. Dates are ISO "YYYY-MM-DD" strings; UUIDs are strings.

// ── Auth (GET /api/auth/me) ───────────────────────────────────────────
export interface CurrentUser {
  id: string;
  email: string;
  name: string;
}

// ── User settings (GET/PUT /api/users/me/settings) ────────────────────
// Closed unions mirroring the backend Literals; keep the string values identical.
export type CurrencyCode = "HUF" | "EUR" | "USD";
export type LanguageCode = "en" | "hu" | "en_hu_alloc";

export interface UserSettings {
  default_currency: CurrencyCode;
  language: LanguageCode;
}

export type MaintenanceStatus = "ok" | "soon" | "due" | "overdue";
export type IntervalUnit = "months" | "years";
export type TireType = "summer" | "winter" | "all_season";
export type ExpenseKind = "modeled" | "other";
export type ExpenseSourceType = "time_based_cost" | "usage_based_cost" | "maintenance_item";

// ── Workspace overview (GET /api/assets) ──────────────────────────────
export interface AssetSummary {
  id: string;
  type: string;
  name: string;
  status: string;
  currency: string;
  balance: number;
  recommended_monthly_allocation: number;
}

export interface WorkspaceTotals {
  total_balance: number;
  total_recommended_monthly_allocation: number;
}

export interface WorkspaceOverview {
  assets: AssetSummary[];
  totals: WorkspaceTotals;
}

// ── Asset detail (GET /api/assets/{id}) ───────────────────────────────
export interface MaintenanceItem {
  id: string;
  asset_id: string;
  label: string;
  technical_key: string | null;
  interval_km: number | null;
  interval_months: number | null;
  last_serviced_at_date: string | null;
  last_serviced_at_odometer: number | null;
  tire_type: string | null;
  estimated_cost: number | null;
  notes: string | null;
  is_active: boolean;
  status: MaintenanceStatus | null;
  km_since_service: number | null;
  months_since_service: number | null;
  km_progress: number | null;
  month_progress: number | null;
  remaining_km: number | null;
  remaining_months: number | null;
}

export interface ActivityItem {
  event_date: string;
  kind: "allocation" | "expense";
  label: string;
  amount: number;
  paid_out_of_pocket: number;
}

export interface UpcomingExpense {
  name: string;
  category: "time_based" | "maintenance";
  days_until: number;
  amount: number;
  overdue: boolean;
}

export interface AverageAllocation {
  months: 3 | 6 | 12;
  amount: number | null;
}

export interface AssetDetail {
  id: string;
  type: string;
  name: string;
  status: string;
  currency: string;
  balance: number;
  recommended_monthly_allocation: number;
  daily_accrual: number;
  vehicle_age_years: number | null;
  tracked_in_app_months: number;
  average_monthly_cost: number;
  avg_monthly_paid_out_of_pocket: number;
  next_maintenance: { label: string; remaining_km: number } | null;
  tracks_usage: boolean;
  current_usage: number | null;
  usage_since_last_check_in: number | null;
  last_check_in_date: string | null;
  maintenance_items: MaintenanceItem[];
  recent_activity: ActivityItem[];
  upcoming_expenses: UpcomingExpense[];
  manual_extra_monthly: number;
  manual_extra_recommended: number;
  manual_extra_recommended_months: number;
  average_monthly_usage: number;
  average_allocation: AverageAllocation;
}

export interface ManualExtraUpdate {
  manual_extra_monthly: number;
}

// ── Balance history (GET /api/assets/{id}/balance-history) ─────────────
export interface BalancePoint {
  month: string;
  as_of: string;
  balance: number;
}

export interface BalanceHistory {
  asset_id: string;
  currency: string;
  points: BalancePoint[];
}

// ── Cost distribution (GET /api/assets/{id}/cost-distribution) ─────────
export interface CostDistributionSlice {
  label: string;
  source_type: string | null;
  amount: number;
}

export interface CostDistribution {
  asset_id: string;
  currency: string;
  window_start: string;
  window_end: string;
  months_with_data: number;
  total: number;
  slices: CostDistributionSlice[];
}

// ── Check-in history (GET /api/assets/{id}/check-in-history) ───────────
export interface CheckInHistoryRow {
  check_in_id: string;
  period_end: string;
  usage_end: number | null;
  usage_since_last: number | null;
  elapsed_days: number;
  allocated: number;
  expense: number;
  bucket_expense: number;
  paid_out_of_pocket: number;
  net: number;
  balance: number;
  expenses: CheckInExpenseLine[];
}

export interface CheckInHistory {
  asset_id: string;
  currency: string;
  rows: CheckInHistoryRow[];
}

// ── Cost rows ─────────────────────────────────────────────────────────
export interface TimeBasedCost {
  id: string;
  asset_id: string;
  label: string;
  technical_key: string | null;
  amount: number;
  reference_amount: number;
  annualized_amount: number;
  daily_rate: number;
  interval_value: number;
  interval_unit: IntervalUnit;
  first_due_date: string | null;
  next_due_date: string | null;
  notes: string | null;
  is_active: boolean;
}

export interface UsageBasedCost {
  id: string;
  asset_id: string;
  label: string;
  technical_key: string | null;
  amount_per_unit: number;
  usage_unit: string;
  currency: string;
  notes: string | null;
  is_active: boolean;
}

// ── Check-in preview / post ───────────────────────────────────────────
export interface AllocationLine {
  source_type: string;
  source_id: string | null;
  label: string;
  amount: number;
}

export interface ExpenseLine {
  kind: ExpenseKind;
  amount: number;
  bucket_amount: number;
  paid_out_of_pocket: number;
  event_date: string;
  comment: string | null;
  source_type: string | null;
  source_id: string | null;
  usage_counter_at_event: number | null;
}

export interface CheckInExpenseLine {
  kind: ExpenseKind;
  amount: number;
  bucket_amount: number;
  paid_out_of_pocket: number;
  event_date: string;
  comment: string | null;
  source_type: string | null;
  source_id: string | null;
  usage_counter_at_event: number | null;
  label: string;
}

export interface CheckInPreview {
  asset_id: string;
  period_start: string;
  period_end: string;
  usage_start: number | null;
  usage_end: number | null;
  elapsed_days: number;
  usage_amount: number | null;
  active_tire_type: string | null;
  allocation_lines: AllocationLine[];
  expense_lines: ExpenseLine[];
  balance_before: number;
  total_allocation: number;
  total_expense: number;
  total_bucket_expense: number;
  paid_out_of_pocket: number;
  net_bucket_change: number;
  balance_after: number;
}

// ── Check-in detail / edit (GET/PATCH /api/assets/{id}/check-ins/{check_in_id}) ────
export interface CheckInDetail {
  check_in_id: string;
  period_end: string;
  usage_end: number | null;
  active_tire_type: TireType | null;
  elapsed_days: number;
  usage_amount: number | null;
  allocation_lines: AllocationLine[];
  expense_lines: ExpenseLine[];
  notes: string | null;
}

// Mirrors CheckInPreview minus asset_id/period_start/usage_start (unchanged and already known from
// the earlier getCheckIn call), plus the edit-only validity fields. Deliberately close enough to
// CheckInPreview that CheckInScreen's existing preview rendering (Step 2 card, confirm panel) can
// render either shape without a separate code path.
export interface EditCheckInPreview {
  period_end: string;
  usage_end: number | null;
  active_tire_type: string | null;
  elapsed_days: number;
  usage_amount: number | null;
  allocation_lines: AllocationLine[];
  expense_lines: ExpenseLine[];
  balance_before: number;
  total_allocation: number;
  total_expense: number;
  total_bucket_expense: number;
  paid_out_of_pocket: number;
  net_bucket_change: number;
  balance_after: number;
  is_valid: boolean;
  first_invalid_check_in_id: string | null;
  first_invalid_period_end: string | null;
}

export interface EditCheckInBody {
  expenses: ExpenseDraft[];
  notes?: string | null;
}

// ── Template catalog (GET /api/asset-templates/{key}/catalog) ─────────
// Money fields (amount, amount_per_unit, estimated_cost) are `number` here
// because the client reviver coerces the backend's Decimal strings. Interval
// fields arrive as JSON numbers already.
export interface TemplateTimeBasedCostItem {
  technical_key: string;
  label: string;
  amounts: Record<CurrencyCode, number>;
  interval_value: number;
  interval_unit: IntervalUnit;
}

export interface TemplateUsageBasedCostItem {
  technical_key: string;
  label: string;
  amounts_per_unit: Record<CurrencyCode, number>;
  usage_unit: string;
}

export interface TemplateMaintenanceItem {
  technical_key: string;
  label: string;
  interval_km: number | null;
  interval_months: number | null;
  tire_type: string | null;
  estimated_costs: Record<CurrencyCode, number> | null;
}

export interface AssetTemplateCatalog {
  template_key: string;
  time_based_costs: TemplateTimeBasedCostItem[];
  usage_based_costs: TemplateUsageBasedCostItem[];
  maintenance_items: TemplateMaintenanceItem[];
  manual_extra_monthly_amounts: Record<CurrencyCode, number>;
}

// ── Request bodies ────────────────────────────────────────────────────
export interface VehicleDetailsInput {
  starting_odometer?: number;
  manufacture_year?: number | null;
}

export interface TemplateCostOverride {
  technical_key: string;
  amount: number;
  interval_value?: number | null;
  interval_unit?: IntervalUnit | null;
}

export interface CreateAssetRequest {
  name: string;
  type?: string | null;
  template?: "vehicle" | "house" | "pet" | null;
  vehicle?: VehicleDetailsInput | null;
  selected_cost_keys?: string[] | null;
  cost_overrides?: TemplateCostOverride[] | null;
  manual_extra_monthly?: number | null;
}

export interface CreateAssetResponse {
  asset: { id: string; type: string; name: string };
}

export interface AllocationEstimateCustomCost {
  client_key: string;
  label: string;
  amount: number;
  interval_value: number;
  interval_unit: IntervalUnit;
}

export interface AllocationEstimateRequest {
  template?: string | null;
  selected_cost_keys?: string[] | null;
  cost_overrides?: TemplateCostOverride[] | null;
  custom_time_based_costs?: AllocationEstimateCustomCost[] | null;
  manual_extra_monthly?: number | null;
}

export interface AllocationEstimateLine {
  key: string;
  label: string;
  reference_amount: number;
  annualized_amount: number;
  monthly_amount: number;
  daily_rate: number;
}

export interface AllocationEstimate {
  currency: string;
  lines: AllocationEstimateLine[];
  daily_total: number;
  monthly_total: number;
  yearly_total: number;
}

export interface CreateTimeBasedCostRequest {
  label: string;
  amount: number;
  interval_value: number;
  interval_unit: IntervalUnit;
  first_due_date?: string | null;
  notes?: string | null;
}

export interface CreateUsageBasedCostRequest {
  label: string;
  amount_per_unit: number;
  usage_unit?: string;
  notes?: string | null;
}

export interface CreateMaintenanceItemRequest {
  label: string;
  interval_km?: number | null;
  interval_months?: number | null;
  last_serviced_at_date?: string | null;
  last_serviced_at_odometer?: number | null;
  estimated_cost?: number | null;
  tire_type?: TireType | null;
  notes?: string | null;
}

export interface ExpenseDraft {
  kind: ExpenseKind;
  amount: number;
  paid_out_of_pocket_override?: number | null;
  event_date?: string | null;
  usage_counter_at_event?: number | null;
  comment?: string | null;
  source_type?: ExpenseSourceType | null;
  source_id?: string | null;
}

export interface CheckInBody {
  period_end: string;
  usage_end?: number | null;
  active_tire_type?: TireType | null;
  expenses?: ExpenseDraft[];
  notes?: string | null;
}
