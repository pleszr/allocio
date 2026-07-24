import { useState } from "react";
import { api } from "../api/client";
import type { ActivityItem, MaintenanceItem } from "../api/types";
import { Icon } from "../components/Icon";
import { Illo } from "../components/Illustrations";
import { Sparkline } from "../components/Sparkline";
import { ErrorState, LoadingState } from "../components/StateView";
import { illoBg, illoKind } from "../utils/assetType";
import { useCurrency } from "../utils/currency";
import { fmtDateShort, fmtMonthYear, fmtNumber, mockNextAllocation } from "../utils/format";
import { healthPill, maintenancePill } from "../utils/health";
import { useAsync } from "../utils/useAsync";

interface DashboardScreenProps {
  assetId: string;
  onTab: (tab: "costs" | "checkin") => void;
}

const RANGES: { label: string; months: number }[] = [
  { label: "3M", months: 3 },
  { label: "12M", months: 12 },
  { label: "All", months: 60 },
];

export function DashboardScreen({ assetId, onTab }: DashboardScreenProps) {
  const fmt = useCurrency();
  const detail = useAsync(() => api.getAsset(assetId), [assetId]);
  const [months, setMonths] = useState(12);
  const history = useAsync(() => api.getBalanceHistory(assetId, months), [assetId, months]);

  if (detail.loading) return <LoadingState label="Loading dashboard…" />;
  if (detail.error || !detail.data) {
    return <ErrorState message={detail.error ?? "Asset not found."} onRetry={detail.reload} />;
  }

  const e = detail.data;
  const kind = illoKind(e.type);
  const pill = healthPill(e.health);
  const points = history.data?.points ?? [];
  const balances = points.map((p) => p.balance);
  const delta = balances.length >= 2 ? balances[balances.length - 1] - balances[balances.length - 2] : 0;
  const dueSoon = e.maintenance_items.filter((m) => m.status && m.status !== "ok");
  const next = mockNextAllocation();
  const nextLabel = new Date(next.dateIso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const pending = e.daily_accrual * next.daysUntil;
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
            <span className={`pill ${pill.cls}`}>{pill.label}</span>
          </div>
          <div className="muted" style={{ fontSize: 13.5, marginBottom: 4 }}>
            Bucket balance
          </div>
          <div className="num-xl">{fmt(e.balance, { decimals: 2 })}</div>
          <div style={{ marginTop: 10, fontSize: 13.5, color: "var(--muted)" }}>
            <span className={delta >= 0 ? "delta-up" : "delta-down"} style={{ fontWeight: 600 }}>
              {delta >= 0 ? "↑" : "↓"} {fmt(Math.abs(delta), { decimals: 0 })}
            </span>{" "}
            this month
          </div>
        </div>
        <div className="hero-stats">
          <div>
            <div className="hero-stat-label">{e.current_usage !== null ? "Current usage" : "Daily accrual"}</div>
            <div className="hero-stat-val">
              {e.current_usage !== null ? `${fmtNumber(e.current_usage)} km` : fmt(e.daily_accrual, { decimals: 2 })}
            </div>
          </div>
          <div>
            <div className="hero-stat-label">Next allocation</div>
            <div className="hero-stat-val">{fmt(e.recommended_monthly_allocation, { decimals: 0 })}</div>
            <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
              on {nextLabel} · in {next.daysUntil} days
            </div>
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => onTab("checkin")} style={{ alignSelf: "flex-start" }}>
            Run check-in <Icon name="arrowRight" size={12} />
          </button>
        </div>
      </div>

      {/* Balance history */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-hd">
          <div>
            <div className="card-title">Balance history</div>
            <div className="card-sub">How {e.name}'s bucket has tracked over time</div>
          </div>
          <div className="seg">
            {RANGES.map((r) => (
              <button key={r.months} className="seg-btn" aria-pressed={months === r.months} onClick={() => setMonths(r.months)}>
                {r.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ padding: "20px var(--pad) var(--pad)" }}>
          {history.loading ? (
            <div className="row-meta">Loading…</div>
          ) : points.length === 0 ? (
            <div className="row-meta">No history yet.</div>
          ) : (
            <>
              <Sparkline data={balances} width={900} height={130} padding={12} />
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
                <span className="row-meta">{fmtMonthYear(points[0].as_of)}</span>
                <span className="row-meta">{fmtMonthYear(points[points.length - 1].as_of)}</span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* KPI grid */}
      <div className="kpi-grid" style={{ marginBottom: 24 }}>
        <div className="kpi">
          <div className="kpi-label">Daily accrual</div>
          <div className="num-lg">{fmt(e.daily_accrual, { decimals: 2 })}</div>
          <div className="kpi-sub">{fmt(e.recommended_monthly_allocation, { decimals: 0 })}/mo recommended</div>
        </div>
        {e.current_usage !== null ? (
          <div className="kpi">
            <div className="kpi-label">Current usage</div>
            <div className="num-lg">
              {fmtNumber(e.current_usage)} <span className="muted" style={{ fontSize: 14 }}>km</span>
            </div>
            <div className="kpi-sub">
              {e.usage_since_last_check_in !== null
                ? `+${fmtNumber(e.usage_since_last_check_in)} km since last check-in`
                : "No check-in yet"}
            </div>
          </div>
        ) : (
          <div className="kpi">
            <div className="kpi-label">Maintenance items</div>
            <div className="num-lg">{costCount}</div>
            <div className="kpi-sub">{dueSoon.length > 0 ? `${dueSoon.length} need attention` : "all current"}</div>
          </div>
        )}
        <div className="kpi">
          <div className="kpi-label">Next allocation</div>
          <div className="num-lg">{nextLabel}</div>
          <div className="kpi-sub">
            {next.daysUntil} days · {fmt(pending, { decimals: 0 })} pending
          </div>
        </div>
      </div>

      {/* Maintenance + recent activity */}
      <div className="col-3-2">
        <div className="card">
          <div className="card-hd">
            <div>
              <div className="card-title">Maintenance</div>
              <div className="card-sub">
                {dueSoon.length > 0
                  ? `${dueSoon.length} item${dueSoon.length > 1 ? "s" : ""} need attention`
                  : e.maintenance_items.length > 0
                    ? "Everything is current"
                    : "No maintenance items"}
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => onTab("costs")}>
              Manage <Icon name="chevronRight" size={12} />
            </button>
          </div>
          <div style={{ marginTop: 14, paddingBottom: 6 }}>
            {e.maintenance_items.slice(0, 5).map((m) => (
              <MaintRow key={m.id} item={m} />
            ))}
            {e.maintenance_items.length === 0 && (
              <div className="row-meta" style={{ padding: "12px var(--pad)" }}>
                Add maintenance items on the Costs tab.
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-hd">
            <div>
              <div className="card-title">Recent activity</div>
              <div className="card-sub">Latest bucket movements</div>
            </div>
          </div>
          <div style={{ marginTop: 14, paddingBottom: 6 }}>
            {e.recent_activity.slice(0, 6).map((tx, i) => (
              <TxRow key={i} tx={tx} />
            ))}
            {e.recent_activity.length === 0 && (
              <div className="row-meta" style={{ padding: "12px var(--pad)" }}>
                No activity yet — run a check-in to record allocations.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MaintRow({ item }: { item: MaintenanceItem }) {
  const pill = maintenancePill(item.status);
  const progress = Math.min(1, Math.max(item.km_progress ?? 0, item.month_progress ?? 0));
  const byKm = item.interval_km !== null;
  const currentText = byKm
    ? `${fmtNumber(item.km_since_service ?? 0)} / ${fmtNumber(item.interval_km ?? 0)} km`
    : `${item.months_since_service ?? 0} / ${item.interval_months ?? 0} mo`;
  const remainingText =
    item.status === "overdue"
      ? "overdue"
      : byKm
        ? `${fmtNumber(item.remaining_km ?? 0)} km left`
        : `${item.remaining_months ?? 0} mo left`;

  return (
    <div style={{ padding: "12px var(--pad)", borderTop: "1px solid var(--line-soft)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 500 }}>{item.label}</span>
        <span className={`pill ${pill.cls}`}>{pill.label}</span>
      </div>
      <div className="bar-track">
        <div className={`bar-fill ${pill.fill}`} style={{ ["--pct" as string]: `${progress * 100}%` }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
        <span className="row-meta">{currentText}</span>
        <span className="row-meta">{remainingText}</span>
      </div>
    </div>
  );
}

function TxRow({ tx }: { tx: ActivityItem }) {
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
          {fmtDateShort(tx.event_date)} · {tx.kind === "allocation" ? "into bucket" : "from bucket"}
        </div>
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
