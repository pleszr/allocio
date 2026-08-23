import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { ActivityItem } from "../api/types";
import type { CostsTab } from "../routes";
import {
  CostHistoryModal,
  type HistoryTarget,
  maintHistoryTarget,
  timeCostHistoryTarget,
} from "../components/CostHistoryModal";
import { Icon } from "../components/Icon";
import { Illo } from "../components/Illustrations";
import { ManualExtraEditor } from "../components/ManualExtraEditor";
import { MaintenancePanel } from "../components/MaintenancePanel";
import { Sparkline } from "../components/Sparkline";
import { TimeCostPanel } from "../components/TimeCostPanel";
import { ErrorState, LoadingState } from "../components/StateView";
import { illoBg, illoKind } from "../utils/assetType";
import { useCurrency } from "../utils/currency";
import { fmtDateShort, fmtMonthYear, fmtNumber } from "../utils/format";
import { isManualExtraRecommendationApplied } from "../utils/manualExtraRecommendation";
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
  const timeBased = useAsync(() => api.listTimeBasedCosts(assetId), [assetId]);
  const usageBased = useAsync(() => api.listUsageBasedCosts(assetId), [assetId]);
  const [months, setMonths] = useState(12);
  const [historyTarget, setHistoryTarget] = useState<HistoryTarget | null>(null);
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
  const activeMaintenance = e.maintenance_items.filter((m) => m.is_active);
  const hasManualExtraRecommendation =
    e.manual_extra_recommended > 0 &&
    !isManualExtraRecommendationApplied(assetId, e.manual_extra_recommended, e.manual_extra_monthly);
  const manualExtraRecommended = hasManualExtraRecommendation ? e.manual_extra_recommended : 0;
  const timeCosts = timeBased.data ?? [];
  const hasTimeCosts = timeCosts.some((c) => c.is_active);
  const usageRows = usageBased.data ?? [];
  const timePerYear = timeCosts.filter((c) => c.is_active).reduce((sum, row) => sum + row.annualized_amount, 0);
  const usageRate = usageRows.filter((u) => u.is_active).reduce((sum, u) => sum + u.amount_per_unit, 0);
  const usageMonthly = usageRate * e.average_monthly_usage;

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
              {e.tracks_usage && e.usage_since_last_check_in !== null && (
                <span className="muted" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>
                  {t("dashboard.usage_since_last", { km: fmtNumber(e.usage_since_last_check_in) })}
                </span>
              )}
            </div>
          </div>
          <div>
            <div className="hero-stat-label">{t("dashboard.average_allocation")}</div>
            <div className="hero-stat-val">{fmt(e.average_allocation, { decimals: 0 })}</div>
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => onTab("checkin")} style={{ alignSelf: "flex-start" }}>
            {t("dashboard.run_checkin")} <Icon name="arrowRight" size={12} />
          </button>
        </div>
      </div>

      {/* KPI grid — same tiles, content, and styling as the Costs screen's former grid */}
      <div className="kpi-grid kpi-grid-4" style={{ marginBottom: 24 }}>
        <div className="kpi">
          <div className="kpi-label">{t("costs.time_total")}</div>
          <div className="num-lg">
            {fmt(timePerYear / 12, { decimals: 0 })}
            <span className="muted" style={{ fontSize: 14 }}>
              {t("costs.per_mo")}
            </span>
          </div>
          <div className="kpi-sub">
            {fmt(timePerYear, { decimals: 0 })}
            {t("costs.per_yr")}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">{t("costs.usage_rate")}</div>
          <div className="num-lg">
            {fmt(usageMonthly, { decimals: 2 })}
            <span className="muted" style={{ fontSize: 14 }}>
              {t("costs.per_mo")}
            </span>
          </div>
          <div className="kpi-sub">
            {fmt(usageMonthly * 12, { decimals: 0 })}
            {t("costs.per_yr")}
          </div>
          <div className="kpi-sub">
            {fmt(usageRate, { decimals: 3 })}
            {t("costs.per_unit")}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">{t("costs.manual_extra")}</div>
          <div className="num-lg">
            {fmt(e.manual_extra_monthly, { decimals: 0 })}
            <span className="muted" style={{ fontSize: 14 }}>
              {t("costs.per_mo")}
            </span>
          </div>
          {hasManualExtraRecommendation ? (
            <div className="kpi-copy" style={{ fontSize: 12.5, marginTop: 6 }}>
              <div className="kpi-copy-line">
                {t("dashboard.extra_context_cost", { amount: fmt(e.average_actual_monthly_cost, { decimals: 0 }) })}
              </div>
              <div className="kpi-copy-line">
                {t("dashboard.extra_context_allocation", { amount: fmt(e.average_allocation, { decimals: 0 }) })}
              </div>
              <div className="kpi-copy-line">
                {t("costs.manual_extra_recommended_amount", {
                  amount: fmt(e.manual_extra_monthly + e.manual_extra_recommended, { decimals: 0 }),
                })}{" "}
                <ManualExtraEditor
                  assetId={assetId}
                  current={e.manual_extra_monthly}
                  recommended={manualExtraRecommended}
                  onChanged={detail.reload}
                  renderTrigger={({ ref, onClick }) => (
                    <button ref={ref} className="kpi-link-inline" onClick={onClick}>
                      {t("costs.manual_extra_set_it")}
                    </button>
                  )}
                />
              </div>
            </div>
          ) : (
            <>
              <div className="kpi-sub">{t("costs.manual_extra_sub")}</div>
              <ManualExtraEditor
                assetId={assetId}
                current={e.manual_extra_monthly}
                recommended={manualExtraRecommended}
                onChanged={detail.reload}
                renderTrigger={({ ref, onClick }) => (
                  <button ref={ref} className="kpi-link" onClick={onClick}>
                    {t("costs.manual_extra_edit")}
                  </button>
                )}
              />
            </>
          )}
        </div>
        <div className="kpi" style={{ background: "var(--accent-soft)", borderColor: "transparent" }}>
          <div className="kpi-label">{t("costs.required_allocation")}</div>
          <div className="num-lg">
            {fmt(e.recommended_monthly_allocation, { decimals: 0 })}
            <span className="muted" style={{ fontSize: 14 }}>
              {t("costs.per_mo")}
            </span>
          </div>
          <div className="kpi-sub">{t("costs.time_usage_manual")}</div>
        </div>
      </div>

      {/* Merged full-width maintenance panel (car diagram + unified list) */}
      {activeMaintenance.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <MaintenancePanel
            maintenanceItems={activeMaintenance}
            onManage={() => onTab("costs", "maint")}
            onOpenHistory={(item) => setHistoryTarget(maintHistoryTarget(item, t, fmt))}
          />
        </div>
      )}

      {/* Full-width time-based costs */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-hd">
          <div>
            <div className="card-title">{t("dashboard.time_based_title")}</div>
            <div className="card-sub">{t("dashboard.time_based_sub")}</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => onTab("costs", "time")}>
            {t("dashboard.manage")} <Icon name="chevronRight" size={12} />
          </button>
        </div>
        {timeBased.loading ? (
          <div className="row-meta" style={{ padding: "12px var(--pad)" }}>{t("common.loading")}</div>
        ) : hasTimeCosts ? (
          <div style={{ padding: "4px 0 4px" }}>
            <TimeCostPanel
              costs={timeCosts}
              compact
              onOpenHistory={(cost) => setHistoryTarget(timeCostHistoryTarget(cost, t, fmt))}
            />
          </div>
        ) : (
          <div className="row-meta" style={{ padding: "12px var(--pad)" }}>{t("dashboard.time_based_empty")}</div>
        )}
      </div>

      {/* Recent activity + balance history */}
      <div className="col-2">
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
      {historyTarget && (
        <CostHistoryModal
          assetId={assetId}
          kind={historyTarget.kind}
          costId={historyTarget.costId}
          label={historyTarget.label}
          meta={historyTarget.meta}
          onClose={() => setHistoryTarget(null)}
        />
      )}
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
