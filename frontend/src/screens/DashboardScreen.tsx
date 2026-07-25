import { useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { ActivityItem, MaintenanceItem, UpcomingExpense } from "../api/types";
import type { CostsTab } from "../routes";
import { Icon } from "../components/Icon";
import { Illo } from "../components/Illustrations";
import { Sparkline } from "../components/Sparkline";
import { ErrorState, LoadingState } from "../components/StateView";
import { illoBg, illoKind } from "../utils/assetType";
import { useCurrency } from "../utils/currency";
import { fmtDateShort, fmtMonthYear, fmtNumber } from "../utils/format";
import { maintenancePill } from "../utils/maintenanceStatus";
import { useAsync } from "../utils/useAsync";

interface DashboardScreenProps {
  assetId: string;
  onTab: (tab: "costs" | "checkin", costsSubTab?: CostsTab) => void;
}

const RANGES: { label: string; months: number }[] = [
  { label: "3M", months: 3 },
  { label: "12M", months: 12 },
  { label: "All", months: 60 },
];

export function DashboardScreen({ assetId, onTab }: DashboardScreenProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const detail = useAsync(() => api.getAsset(assetId), [assetId]);
  const [months, setMonths] = useState(12);
  const history = useAsync(() => api.getBalanceHistory(assetId, months), [assetId, months]);

  if (detail.loading) return <LoadingState label={t("dashboard.loading")} />;
  if (detail.error || !detail.data) {
    return <ErrorState message={detail.error ?? t("dashboard.not_found")} onRetry={detail.reload} />;
  }

  const e = detail.data;
  const kind = illoKind(e.type);
  const points = history.data?.points ?? [];
  const balances = points.map((p) => p.balance);
  const delta = balances.length >= 2 ? balances[balances.length - 1] - balances[balances.length - 2] : 0;
  const dueSoon = e.maintenance_items.filter((m) => m.status && m.status !== "ok");
  const activeMaintenance = e.maintenance_items.filter((m) => m.is_active);
  const annualService = e.tracks_usage
    ? undefined
    : activeMaintenance.find((m) => m.technical_key === "annual_service");
  const averageAllocation = e.average_allocation;
  const upcomingTotal = e.upcoming_expenses.reduce((sum, item) => sum + item.amount, 0);
  const costCount = e.maintenance_items.length;

  return (
    <div className="content fade-in">
      {/* HERO */}
      <div className="entity-hero" style={{ marginBottom: 24 }}>
        <div className="entity-hero-illo" style={{ background: illoBg(kind), borderRadius: 14 }}>
          <Illo kind={kind} />
        </div>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <h1 className="h1" style={{ fontSize: 24 }}>
              {e.name}
            </h1>
          </div>
          <div className="muted" style={{ fontSize: 13.5, marginBottom: 4 }}>
            {t("dashboard.bucket_balance")}
          </div>
          <div className="num-xl">{fmt(e.balance, { decimals: 2 })}</div>
          <div style={{ marginTop: 10, fontSize: 13.5, color: "var(--muted)" }}>
            <span className={delta >= 0 ? "delta-up" : "delta-down"} style={{ fontWeight: 600 }}>
              {delta >= 0 ? "↑" : "↓"} {fmt(Math.abs(delta), { decimals: 0 })}
            </span>{" "}
            {t("dashboard.this_month")}
          </div>
        </div>
        <div className="hero-stats">
          <div>
            <div className="hero-stat-label">
              {e.tracks_usage ? t("dashboard.current_usage") : t("dashboard.daily_accrual")}
            </div>
            <div className="hero-stat-val">
              {e.tracks_usage && e.current_usage !== null
                ? `${fmtNumber(e.current_usage)} km`
                : fmt(e.daily_accrual, { decimals: 2 })}
            </div>
          </div>
          <div>
            <div className="hero-stat-label">{t("dashboard.average_allocation")}</div>
            {averageAllocation.amount === null ? (
              <div className="hero-stat-val">{t("dashboard.no_allocation_history")}</div>
            ) : (
              <>
                <div className="hero-stat-val">{fmt(averageAllocation.amount, { decimals: 0 })}</div>
                <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                  {t("dashboard.average_allocation_meta", { months: averageAllocation.months })}
                </div>
              </>
            )}
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => onTab("checkin")} style={{ alignSelf: "flex-start" }}>
            {t("dashboard.run_checkin")} <Icon name="arrowRight" size={12} />
          </button>
        </div>
      </div>

      {/* KPI grid */}
      <div className="kpi-grid" style={{ marginBottom: 24 }}>
        {e.tracks_usage ? (
          <div className="kpi">
            <div className="kpi-label">{t("dashboard.vehicle_overview")}</div>
            <div className="kpi-copy">
              {e.vehicle_age_years !== null && (
                <div className="kpi-copy-line">
                  {t("dashboard.vehicle_age", { count: e.vehicle_age_years })}
                </div>
              )}
              <div className="kpi-copy-line">
                {t("dashboard.tracked_in_app", {
                  duration: formatTrackedDuration(e.tracked_in_app_months, t),
                })}
              </div>
              <div className="kpi-copy-line">
                {t("dashboard.average_monthly_cost", {
                  amount: fmt(e.average_monthly_cost, { decimals: 0 }),
                })}
              </div>
            </div>
          </div>
        ) : (
          <div className="kpi">
            <div className="kpi-label">{t("dashboard.daily_accrual")}</div>
            <div className="num-lg">{fmt(e.daily_accrual, { decimals: 2 })}</div>
            <div className="kpi-sub">
              {t("dashboard.per_mo_recommended", {
                amount: fmt(e.recommended_monthly_allocation, { decimals: 0 }),
              })}
            </div>
          </div>
        )}
        {e.tracks_usage && e.current_usage !== null ? (
          <div className="kpi">
            <div className="kpi-label">{t("dashboard.current_usage")}</div>
            <div className="num-lg">
              {fmtNumber(e.current_usage)} <span className="muted" style={{ fontSize: 14 }}>km</span>
            </div>
            <div className="kpi-sub">
              {e.usage_since_last_check_in !== null
                ? t("dashboard.usage_since_checkin", { km: fmtNumber(e.usage_since_last_check_in) })
                : t("dashboard.no_checkin_yet")}
            </div>
          </div>
        ) : (
          <div className="kpi">
            <div className="kpi-label">{t("dashboard.maintenance_items")}</div>
            <div className="num-lg">{costCount}</div>
            <div className="kpi-sub">
              {dueSoon.length > 0 ? t("dashboard.need_attention", { n: dueSoon.length }) : t("dashboard.all_current")}
            </div>
          </div>
        )}
        {e.tracks_usage ? (
          <div className="kpi">
            <div className="kpi-label">{t("dashboard.next_maintenance")}</div>
            <div className="kpi-copy">
              <div className="kpi-copy-line">
                {e.next_maintenance
                  ? t("dashboard.next_maintenance_detail", {
                      name: e.next_maintenance.label,
                      km: fmtNumber(e.next_maintenance.remaining_km),
                    })
                  : t("dashboard.next_maintenance_empty")}
              </div>
            </div>
          </div>
        ) : (
          <div className="kpi">
            <div className="kpi-label">{t("dashboard.until_annual_service")}</div>
            {annualService?.remaining_km !== null && annualService?.remaining_km !== undefined ? (
              <div className="num-lg">
                {fmtNumber(annualService.remaining_km)}{" "}
                <span className="muted" style={{ fontSize: 14 }}>
                  km
                </span>
              </div>
            ) : (
              <div className="kpi-sub">
                {annualService
                  ? t("dashboard.annual_service_baseline_missing")
                  : t("dashboard.annual_service_not_configured")}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Maintenance + upcoming expenses + recent activity + balance history */}
      <div className="col-2">
        <div className="card">
          <div className="card-hd">
            <div>
              <div className="card-title">{t("dashboard.maintenance")}</div>
              <div className="card-sub">
                {dueSoon.length > 0
                  ? t("dashboard.items_need_attention", { count: dueSoon.length })
                  : e.maintenance_items.length > 0
                    ? t("dashboard.everything_current")
                    : t("dashboard.no_maintenance_items")}
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => onTab("costs", "maint")}>
              {t("dashboard.manage")} <Icon name="chevronRight" size={12} />
            </button>
          </div>
          {activeMaintenance.length > 0 ? (
            <div className="maint-grid">
              {activeMaintenance.map((m) => (
                <MaintCompactRow key={m.id} item={m} />
              ))}
            </div>
          ) : (
            <div className="row-meta" style={{ padding: "12px var(--pad)" }}>
              {t("dashboard.add_maintenance_costs_tab")}
            </div>
          )}
        </div>

        <div className="stack">
          <div className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">{t("dashboard.upcoming_title")}</div>
                <div className="card-sub">{t("dashboard.upcoming_sub")}</div>
              </div>
              {upcomingTotal > 0 && <span className="pill pill-accent">{fmt(upcomingTotal, { decimals: 0 })}</span>}
            </div>
            <div style={{ marginTop: 10, paddingBottom: 6 }}>
              {e.upcoming_expenses.length === 0 ? (
                <div className="row-meta" style={{ padding: "10px var(--pad) 14px" }}>
                  {t("dashboard.upcoming_empty")}
                </div>
              ) : (
                e.upcoming_expenses.map((item, i) => <UpcomingRow key={i} item={item} />)
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">{t("dashboard.recent_activity")}</div>
                <div className="card-sub">{t("dashboard.recent_activity_sub")}</div>
              </div>
            </div>
            <div style={{ marginTop: 14, paddingBottom: 6 }}>
              {e.recent_activity.slice(0, 6).map((tx, i) => (
                <TxRow key={i} tx={tx} />
              ))}
              {e.recent_activity.length === 0 && (
                <div className="row-meta" style={{ padding: "12px var(--pad)" }}>
                  {t("dashboard.no_activity")}
                </div>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">{t("dashboard.balance_history")}</div>
                <div className="card-sub">{t("dashboard.balance_history_sub", { name: e.name })}</div>
              </div>
              <div className="seg">
                {RANGES.map((r) => (
                  <button
                    key={r.months}
                    className="seg-btn"
                    aria-pressed={months === r.months}
                    onClick={() => setMonths(r.months)}
                  >
                    {r.months === 60 ? t("dashboard.range_all") : r.label}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ padding: "20px var(--pad) var(--pad)" }}>
              {history.loading ? (
                <div className="row-meta">{t("common.loading")}</div>
              ) : points.length === 0 ? (
                <div className="row-meta">{t("dashboard.no_history")}</div>
              ) : (
                <>
                  <Sparkline
                    data={balances}
                    width={900}
                    height={130}
                    padding={12}
                    months={points.map((p) => fmtMonthYear(p.as_of))}
                    fmtValue={(v) => fmt(v, { decimals: 0 })}
                  />
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
                    <span className="row-meta">{fmtMonthYear(points[0].as_of)}</span>
                    <span className="row-meta">{fmtMonthYear(points[points.length - 1].as_of)}</span>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatTrackedDuration(totalMonths: number, t: TFunction): string {
  if (totalMonths < 24) {
    return t("dashboard.duration_month", { count: totalMonths });
  }
  const years = Math.floor(totalMonths / 12);
  const months = totalMonths % 12;
  return t("dashboard.duration_years_and_months", {
    years: t("dashboard.duration_year", { count: years }),
    months: t("dashboard.duration_month", { count: months }),
  });
}

function MaintCompactRow({ item }: { item: MaintenanceItem }) {
  const { t } = useTranslation();
  const pill = maintenancePill(item.status);
  const progress = Math.min(1, Math.max(item.km_progress ?? 0, item.month_progress ?? 0));
  const byKm = item.interval_km !== null;
  const remainingText =
    item.status === "overdue"
      ? t("dashboard.overdue")
      : byKm
        ? t("dashboard.maint_remaining_km", { km: fmtNumber(item.remaining_km ?? 0) })
        : t("dashboard.maint_remaining_mo", { months: item.remaining_months ?? 0 });
  const rowCls = item.status === "overdue" ? "row-overdue" : item.status === "due" || item.status === "soon" ? "row-soon" : "";
  const statusCls = pill.fill ? `maint-cell-status ${pill.fill}` : "maint-cell-status";

  return (
    <div className={`maint-cell ${rowCls}`}>
      <div className="maint-cell-top">
        <span className="maint-cell-name">{item.label}</span>
        <span className={statusCls}>{remainingText}</span>
      </div>
      <div className="bar-track">
        <div className={`bar-fill ${pill.fill}`} style={{ ["--pct" as string]: `${progress * 100}%` }} />
      </div>
    </div>
  );
}

function UpcomingRow({ item }: { item: UpcomingExpense }) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const dueText = item.overdue
    ? t("dashboard.due_overdue")
    : item.days_until === 0
      ? t("dashboard.due_now")
      : t("dashboard.due_in_days", { days: item.days_until });
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto",
        gap: 12,
        padding: "9px var(--pad)",
        borderTop: "1px solid var(--line-soft)",
        alignItems: "center",
      }}
    >
      <div>
        <div style={{ fontSize: 13.5, fontWeight: 500 }}>{item.name}</div>
        <div className="row-meta" style={{ marginTop: 2 }}>
          {item.category === "time_based" ? t("dashboard.category_time_based") : t("dashboard.category_maintenance")} ·{" "}
          {item.overdue ? <span style={{ color: "var(--bad)", fontWeight: 600 }}>{dueText}</span> : dueText}
        </div>
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, fontFeatureSettings: '"tnum"' }}>{fmt(item.amount, { decimals: 0 })}</div>
    </div>
  );
}

function TxRow({ tx }: { tx: ActivityItem }) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const pos = tx.amount >= 0;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto",
        padding: "12px var(--pad)",
        borderTop: "1px solid var(--line-soft)",
        alignItems: "baseline",
      }}
    >
      <div>
        <div style={{ fontSize: 14 }}>{tx.label}</div>
        <div className="row-meta" style={{ marginTop: 2 }}>
          {fmtDateShort(tx.event_date)} · {tx.kind === "allocation" ? t("dashboard.into_bucket") : t("dashboard.from_bucket")}
        </div>
        {tx.paid_out_of_pocket > 0 && (
          <div className="row-meta" style={{ marginTop: 2 }}>
            {t("dashboard.paid_out_of_pocket", {
              amount: fmt(tx.paid_out_of_pocket, { decimals: 2 }),
            })}
          </div>
        )}
      </div>
      <div
        style={{
          fontSize: 15,
          fontWeight: 600,
          fontFeatureSettings: '"tnum"',
          color: pos ? "var(--good)" : "var(--ink)",
        }}
      >
        {fmt(tx.amount, { decimals: 2, sign: true })}
      </div>
    </div>
  );
}
