import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { IntervalUnit, MaintenanceItem, TimeBasedCost, UsageBasedCost } from "../api/types";
import { CostDistributionChart } from "../components/CostDistributionChart";
import { CostHistoryModal, type HistoryTarget, maintHistoryTarget, timeCostHistoryTarget } from "../components/CostHistoryModal";
import { EditActions, LabeledMoney } from "../components/EditFormControls";
import { Icon } from "../components/Icon";
import { ErrorState, LoadingState } from "../components/StateView";
import { SpatialMap, spatialItems } from "../components/SpatialMap";
import { TimeCostPanel } from "../components/TimeCostPanel";
import { useCurrency } from "../utils/currency";
import { fmtDate, fmtNumber } from "../utils/format";
import { maintenancePill } from "../utils/maintenanceStatus";
import { useAsync } from "../utils/useAsync";
import { useMutation } from "../utils/useMutation";

interface CostsScreenProps {
  assetId: string;
  onChanged: () => void;
  initialTab?: CostTab;
}

type CostTab = "time" | "usage" | "maint";

export function CostsScreen({ assetId, onChanged, initialTab }: CostsScreenProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [tab, setTab] = useState<CostTab>(initialTab ?? "time");
  const [history, setHistory] = useState<HistoryTarget | null>(null);
  const asset = useAsync(() => api.getAsset(assetId), [assetId]);
  const time = useAsync(() => api.listTimeBasedCosts(assetId), [assetId]);
  const usage = useAsync(() => api.listUsageBasedCosts(assetId), [assetId]);
  const maint = useAsync(() => api.listMaintenanceItems(assetId), [assetId]);
  const distribution = useAsync(() => api.getCostDistribution(assetId), [assetId]);

  const reloadAll = () => {
    asset.reload();
    time.reload();
    usage.reload();
    maint.reload();
    distribution.reload();
    onChanged();
  };

  if (asset.loading || time.loading || usage.loading || maint.loading || distribution.loading) {
    return <LoadingState label={t("costs.loading")} />;
  }
  if (asset.error || time.error || usage.error || maint.error || distribution.error || !asset.data) {
    return (
      <ErrorState
        message={asset.error ?? time.error ?? usage.error ?? maint.error ?? distribution.error ?? t("costs.failed_load")}
        onRetry={reloadAll}
      />
    );
  }

  const assetName = asset.data.name;
  const assetType = asset.data.type;
  const recommendedMonthly = asset.data.recommended_monthly_allocation;
  const avgMonthlyUsage = asset.data.average_monthly_usage;

  const timeRows = time.data ?? [];
  const usageRows = usage.data ?? [];
  const maintRows = maint.data ?? [];

  const activeTimeRows = timeRows.filter((t) => t.is_active);
  const timePerYear = activeTimeRows.reduce((sum, row) => sum + row.annualized_amount, 0);
  const usageRate = usageRows.filter((u) => u.is_active).reduce((s, u) => s + u.amount_per_unit, 0);

  return (
    <div className="content fade-in">
      <div className="section-head">
        <div>
          <div className="eyebrow">{t("costs.cost_editor", { name: assetName })}</div>
          <h1 className="h1" style={{ marginTop: 4 }}>
            {t("costs.define_costs", { type: assetType })}
          </h1>
        </div>
        <div className="seg">
          <button className="seg-btn" aria-pressed={tab === "time"} onClick={() => setTab("time")}>
            {t("costs.tab_time")}
          </button>
          <button className="seg-btn" aria-pressed={tab === "usage"} onClick={() => setTab("usage")}>
            {t("costs.tab_usage")}
          </button>
          <button className="seg-btn" aria-pressed={tab === "maint"} onClick={() => setTab("maint")}>
            {t("costs.tab_maint")}
          </button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 24 }}>
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
            {fmt(usageRate * avgMonthlyUsage, { decimals: 2 })}
            <span className="muted" style={{ fontSize: 14 }}>
              {t("costs.per_mo")}
            </span>
          </div>
          <div className="kpi-sub">
            {fmt(usageRate, { decimals: 3 })}
            {t("costs.per_unit")}
          </div>
        </div>
        <div className="kpi" style={{ background: "var(--accent-soft)", borderColor: "transparent" }}>
          <div className="kpi-label">{t("costs.required_allocation")}</div>
          <div className="num-lg">
            {fmt(recommendedMonthly, { decimals: 0 })}
            <span className="muted" style={{ fontSize: 14 }}>
              {t("costs.per_mo")}
            </span>
          </div>
          <div className="kpi-sub">{t("costs.time_usage_manual")}</div>
        </div>
      </div>

      {tab === "time" && (
        <>
          <TimeCostPanel costs={timeRows} onOpenHistory={(cost) => setHistory(timeCostHistoryTarget(cost, t, fmt))} />
          {timeRows.some((row) => row.is_active) && <div style={{ height: 20 }} />}
          <TimeTable assetId={assetId} rows={timeRows} onChanged={reloadAll} onOpenHistory={setHistory} />
        </>
      )}
      {tab === "usage" && (
        <UsageTable
          assetId={assetId}
          rows={usageRows}
          avgMonthlyUsage={avgMonthlyUsage}
          onChanged={reloadAll}
          onOpenHistory={setHistory}
        />
      )}
      {tab === "maint" && (
        <>
          {spatialItems(maintRows).length > 0 && (
            <>
              <SpatialMap maintenanceItems={maintRows} />
              <div style={{ height: 20 }} />
            </>
          )}
          <MaintTable assetId={assetId} rows={maintRows} onChanged={reloadAll} onOpenHistory={setHistory} />
        </>
      )}

      {history && (
        <CostHistoryModal
          assetId={assetId}
          kind={history.kind}
          costId={history.costId}
          label={history.label}
          meta={history.meta}
          onClose={() => setHistory(null)}
        />
      )}

      <div className="card" style={{ marginTop: 24 }}>
        <div className="card-hd">
          <div>
            <div className="card-title">{t("costs.distribution_title")}</div>
            {distribution.data && distribution.data.months_with_data > 0 && (
              <div className="card-sub">
                {t("costs.distribution_subtitle", { count: distribution.data.months_with_data })}
              </div>
            )}
          </div>
        </div>
        <div className="card-pad">
          {distribution.data && (
            <CostDistributionChart
              key={assetId}
              slices={distribution.data.slices}
              total={distribution.data.total}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Time-based ─────────────────────────────────────────────────────────
function TimeTable({
  assetId,
  rows,
  onChanged,
  onOpenHistory,
}: {
  assetId: string;
  rows: TimeBasedCost[];
  onChanged: () => void;
  onOpenHistory: (target: HistoryTarget) => void;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const openHistory = (row: TimeBasedCost) => onOpenHistory(timeCostHistoryTarget(row, t, fmt));

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: "32%" }}>{t("costs.th_cost")}</th>
            <th>{t("costs.th_amount")}</th>
            <th>{t("costs.th_every")}</th>
            <th>{t("costs.th_per_day")}</th>
            <th>{t("costs.th_next_due")}</th>
            <th style={{ width: 1 }}></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) =>
            editingId === row.id ? (
              <TimeEditRow
                key={row.id}
                assetId={assetId}
                row={row}
                onClose={() => setEditingId(null)}
                onChanged={onChanged}
              />
            ) : (
              <tr
                key={row.id}
                className="cost-row-clickable"
                style={{ opacity: row.is_active ? 1 : 0.5 }}
                onClick={() => openHistory(row)}
                title={t("costHistory.open_hint")}
              >
                <td className="col-name">
                  {row.label}
                  {!row.is_active && <span className="pill" style={{ marginLeft: 8 }}>{t("costs.inactive")}</span>}
                </td>
                <td className="col-num">{fmt(row.amount, { decimals: 0 })}</td>
                <td className="row-meta">
                  {t("costs.every_interval", { value: row.interval_value, unit: t(`costs.unit_${row.interval_unit}`) })}
                </td>
                <td className="col-num">{fmt(row.daily_rate, { decimals: 2 })}</td>
                <td className="row-meta">{row.next_due_date ? fmtDate(row.next_due_date) : "—"}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditingId(row.id)}>
                    <Icon name="edit" size={12} />
                  </button>
                </td>
              </tr>
            ),
          )}
          {adding && <TimeCreateRow assetId={assetId} onClose={() => setAdding(false)} onChanged={onChanged} />}
        </tbody>
      </table>
      {!adding && (
        <div className="add-row" onClick={() => setAdding(true)}>
          <Icon name="plus" size={14} /> {t("costs.add_time")}
        </div>
      )}
    </div>
  );
}

function TimeEditRow({
  assetId,
  row,
  onClose,
  onChanged,
}: {
  assetId: string;
  row: TimeBasedCost;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [label, setLabel] = useState(row.label);
  const [amount, setAmount] = useState(String(row.amount));
  const [value, setValue] = useState(String(row.interval_value));
  const [unit, setUnit] = useState<IntervalUnit>(row.interval_unit);
  const [active, setActive] = useState(row.is_active);
  const { t } = useTranslation();
  const { error, busy, run } = useMutation(onChanged);

  const save = () =>
    run(
      () =>
        api.updateTimeBasedCost(assetId, row.id, {
          label,
          amount: Number(amount),
          interval_value: Number(value),
          interval_unit: unit,
          is_active: active,
        }),
      onClose,
    );

  return (
    <tr style={{ background: "var(--surface-sunk)" }}>
      <td colSpan={6} style={{ padding: "20px var(--pad)" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          {t("costs.editing", { name: row.label })}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label={t("costs.field_name")} value={label} onChange={setLabel} />
          <LabeledMoney label={t("costs.field_amount")} value={amount} onChange={setAmount} />
          <LabeledInput label={t("costs.field_every_n")} value={value} onChange={setValue} type="number" />
          <div className="field">
            <label className="field-label">{t("costs.field_unit")}</label>
            <select className="input" value={unit} onChange={(e) => setUnit(e.target.value as IntervalUnit)}>
              <option value="months">{t("costs.unit_months")}</option>
              <option value="years">{t("costs.unit_years")}</option>
            </select>
          </div>
          <EditActions busy={busy} onCancel={onClose} onSave={save} />
        </div>
        <ActiveToggle active={active} onToggle={setActive} />
        {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
      </td>
    </tr>
  );
}

function TimeCreateRow({ assetId, onClose, onChanged }: { assetId: string; onClose: () => void; onChanged: () => void }) {
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [value, setValue] = useState("1");
  const [unit, setUnit] = useState<IntervalUnit>("years");
  const { t } = useTranslation();
  const { error, busy, run } = useMutation(onChanged);

  const create = () =>
    run(
      () =>
        api.createTimeBasedCost(assetId, {
          label,
          amount: Number(amount),
          interval_value: Number(value),
          interval_unit: unit,
        }),
      onClose,
    );

  return (
    <tr style={{ background: "var(--surface-sunk)" }}>
      <td colSpan={6} style={{ padding: "20px var(--pad)" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          {t("costs.new_time")}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label={t("costs.field_name")} value={label} onChange={setLabel} placeholder={t("costs.ph_insurance")} />
          <LabeledMoney label={t("costs.field_amount")} value={amount} onChange={setAmount} />
          <LabeledInput label={t("costs.field_every_n")} value={value} onChange={setValue} type="number" />
          <div className="field">
            <label className="field-label">{t("costs.field_unit")}</label>
            <select className="input" value={unit} onChange={(e) => setUnit(e.target.value as IntervalUnit)}>
              <option value="months">{t("costs.unit_months")}</option>
              <option value="years">{t("costs.unit_years")}</option>
            </select>
          </div>
          <EditActions busy={busy} disabled={!label.trim() || !amount} onCancel={onClose} onSave={create} saveLabel={t("costs.add")} />
        </div>
        {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
      </td>
    </tr>
  );
}

// ── Usage-based ────────────────────────────────────────────────────────
function UsageTable({
  assetId,
  rows,
  avgMonthlyUsage,
  onChanged,
  onOpenHistory,
}: {
  assetId: string;
  rows: UsageBasedCost[];
  avgMonthlyUsage: number;
  onChanged: () => void;
  onOpenHistory: (target: HistoryTarget) => void;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const openHistory = (row: UsageBasedCost) =>
    onOpenHistory({
      kind: "usage",
      costId: row.id,
      label: row.label,
      meta: [
        { label: t("costs.th_rate"), value: `${fmt(row.amount_per_unit, { decimals: 3 })}/${row.usage_unit}` },
        {
          label: t("costs.th_est_month"),
          value: fmt(row.amount_per_unit * avgMonthlyUsage, { decimals: 2 }),
        },
      ],
    });

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: "40%" }}>{t("costs.th_component")}</th>
            <th>{t("costs.th_rate")}</th>
            <th>{t("costs.th_est_month")}</th>
            <th style={{ width: 1 }}></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((u) =>
            editingId === u.id ? (
              <UsageEditRow key={u.id} assetId={assetId} row={u} onClose={() => setEditingId(null)} onChanged={onChanged} />
            ) : (
              <tr
                key={u.id}
                className="cost-row-clickable"
                style={{ opacity: u.is_active ? 1 : 0.5 }}
                onClick={() => openHistory(u)}
                title={t("costHistory.open_hint")}
              >
                <td className="col-name">
                  {u.label}
                  {!u.is_active && <span className="pill" style={{ marginLeft: 8 }}>{t("costs.inactive")}</span>}
                </td>
                <td className="col-num">
                  {fmt(u.amount_per_unit, { decimals: 3 })}/{u.usage_unit}
                </td>
                <td className="col-num">
                  {fmt(u.amount_per_unit * avgMonthlyUsage, { decimals: 2 })}
                  <div className="row-meta">
                    {t("costs.avg_per_month", { amount: fmtNumber(avgMonthlyUsage, 0), unit: u.usage_unit })}
                  </div>
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditingId(u.id)}>
                    <Icon name="edit" size={12} />
                  </button>
                </td>
              </tr>
            ),
          )}
          {adding && <UsageCreateRow assetId={assetId} onClose={() => setAdding(false)} onChanged={onChanged} />}
        </tbody>
      </table>
      {!adding && (
        <div className="add-row" onClick={() => setAdding(true)}>
          <Icon name="plus" size={14} /> {t("costs.add_usage")}
        </div>
      )}
    </div>
  );
}

function UsageEditRow({ assetId, row, onClose, onChanged }: { assetId: string; row: UsageBasedCost; onClose: () => void; onChanged: () => void }) {
  const [label, setLabel] = useState(row.label);
  const [rate, setRate] = useState(String(row.amount_per_unit));
  const [unit, setUnit] = useState(row.usage_unit);
  const [active, setActive] = useState(row.is_active);
  const { t } = useTranslation();
  const { error, busy, run } = useMutation(onChanged);

  const save = () =>
    run(
      () => api.updateUsageBasedCost(assetId, row.id, { label, amount_per_unit: Number(rate), usage_unit: unit, is_active: active }),
      onClose,
    );

  return (
    <tr style={{ background: "var(--surface-sunk)" }}>
      <td colSpan={4} style={{ padding: "20px var(--pad)" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          {t("costs.editing", { name: row.label })}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label={t("costs.field_name")} value={label} onChange={setLabel} />
          <LabeledMoney label={t("costs.field_per_unit")} value={rate} onChange={setRate} step="0.001" />
          <LabeledInput label={t("costs.field_unit")} value={unit} onChange={setUnit} />
          <EditActions busy={busy} onCancel={onClose} onSave={save} />
        </div>
        <ActiveToggle active={active} onToggle={setActive} />
        {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
      </td>
    </tr>
  );
}

function UsageCreateRow({ assetId, onClose, onChanged }: { assetId: string; onClose: () => void; onChanged: () => void }) {
  const [label, setLabel] = useState("");
  const [rate, setRate] = useState("");
  const [unit, setUnit] = useState("km");
  const { t } = useTranslation();
  const { error, busy, run } = useMutation(onChanged);

  const create = () =>
    run(() => api.createUsageBasedCost(assetId, { label, amount_per_unit: Number(rate), usage_unit: unit }), onClose);

  return (
    <tr style={{ background: "var(--surface-sunk)" }}>
      <td colSpan={4} style={{ padding: "20px var(--pad)" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          {t("costs.new_usage")}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label={t("costs.field_name")} value={label} onChange={setLabel} placeholder={t("costs.ph_fuel")} />
          <LabeledMoney label={t("costs.field_per_unit")} value={rate} onChange={setRate} step="0.001" />
          <LabeledInput label={t("costs.field_unit")} value={unit} onChange={setUnit} />
          <EditActions busy={busy} disabled={!label.trim() || !rate} onCancel={onClose} onSave={create} saveLabel={t("costs.add")} />
        </div>
        {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
      </td>
    </tr>
  );
}

// ── Maintenance ────────────────────────────────────────────────────────
function MaintTable({
  assetId,
  rows,
  onChanged,
  onOpenHistory,
}: {
  assetId: string;
  rows: MaintenanceItem[];
  onChanged: () => void;
  onOpenHistory: (target: HistoryTarget) => void;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const openHistory = (m: MaintenanceItem) => onOpenHistory(maintHistoryTarget(m, t, fmt));

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: "32%" }}>{t("costs.th_item")}</th>
            <th>{t("costs.th_replace_every")}</th>
            <th>{t("costs.th_last_serviced")}</th>
            <th>{t("costs.th_now")}</th>
            <th>{t("costs.th_status")}</th>
            <th style={{ width: 1 }}></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) =>
            editingId === m.id ? (
              <MaintEditRow key={m.id} assetId={assetId} row={m} onClose={() => setEditingId(null)} onChanged={onChanged} />
            ) : (
              <tr
                key={m.id}
                className="cost-row-clickable"
                style={{ opacity: m.is_active ? 1 : 0.5 }}
                onClick={() => openHistory(m)}
                title={t("costHistory.open_hint")}
              >
                <td className="col-name">
                  {m.label}
                  {!m.is_active && <span className="pill" style={{ marginLeft: 8 }}>{t("costs.inactive")}</span>}
                </td>
                <td className="col-num">
                  {m.interval_km ? `${fmtNumber(m.interval_km)} km` : ""}
                  {m.interval_km && m.interval_months ? " / " : ""}
                  {m.interval_months ? `${m.interval_months} mo` : ""}
                  {!m.interval_km && !m.interval_months ? "—" : ""}
                </td>
                <td className="col-num">
                  {m.last_serviced_at_odometer !== null
                    ? `${fmtNumber(m.last_serviced_at_odometer)} km`
                    : m.last_serviced_at_date
                      ? fmtDate(m.last_serviced_at_date)
                      : "—"}
                </td>
                <td className="col-num">
                  {m.interval_km !== null
                    ? m.km_since_service !== null
                      ? `${fmtNumber(m.km_since_service)} km`
                      : "—"
                    : m.months_since_service !== null
                      ? t("costs.now_months", { months: m.months_since_service })
                      : "—"}
                </td>
                <td>
                  <span className={`pill ${maintenancePill(m.status).cls}`}>{maintenancePill(m.status).label}</span>
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditingId(m.id)}>
                    <Icon name="edit" size={12} />
                  </button>
                </td>
              </tr>
            ),
          )}
          {adding && <MaintCreateRow assetId={assetId} onClose={() => setAdding(false)} onChanged={onChanged} />}
        </tbody>
      </table>
      {!adding && (
        <div className="add-row" onClick={() => setAdding(true)}>
          <Icon name="plus" size={14} /> {t("costs.add_maint")}
        </div>
      )}
    </div>
  );
}

function MaintEditRow({ assetId, row, onClose, onChanged }: { assetId: string; row: MaintenanceItem; onClose: () => void; onChanged: () => void }) {
  const [label, setLabel] = useState(row.label);
  const [km, setKm] = useState(row.interval_km !== null ? String(row.interval_km) : "");
  const [mo, setMo] = useState(row.interval_months !== null ? String(row.interval_months) : "");
  const [lastKm, setLastKm] = useState(row.last_serviced_at_odometer !== null ? String(row.last_serviced_at_odometer) : "");
  const [active, setActive] = useState(row.is_active);
  const { t } = useTranslation();
  const { error, busy, run } = useMutation(onChanged);

  const save = () =>
    run(
      () =>
        api.updateMaintenanceItem(assetId, row.id, {
          label,
          interval_km: km ? Number(km) : null,
          interval_months: mo ? Number(mo) : null,
          last_serviced_at_odometer: lastKm ? Number(lastKm) : null,
          is_active: active,
        }),
      onClose,
    );

  return (
    <tr style={{ background: "var(--surface-sunk)" }}>
      <td colSpan={6} style={{ padding: "20px var(--pad)" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          {t("costs.editing", { name: row.label })}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label={t("costs.field_name")} value={label} onChange={setLabel} />
          <LabeledInput label={t("costs.field_every_km")} value={km} onChange={setKm} type="number" />
          <LabeledInput label={t("costs.field_every_months")} value={mo} onChange={setMo} type="number" />
          <LabeledInput label={t("costs.field_last_serviced_km")} value={lastKm} onChange={setLastKm} type="number" />
          <EditActions busy={busy} onCancel={onClose} onSave={save} />
        </div>
        <ActiveToggle active={active} onToggle={setActive} />
        {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
      </td>
    </tr>
  );
}

function MaintCreateRow({ assetId, onClose, onChanged }: { assetId: string; onClose: () => void; onChanged: () => void }) {
  const [label, setLabel] = useState("");
  const [km, setKm] = useState("");
  const [mo, setMo] = useState("");
  const [lastKm, setLastKm] = useState("");
  const { t } = useTranslation();
  const { error, busy, run } = useMutation(onChanged);

  const doCreate = () =>
    run(
      () =>
        api.createMaintenanceItem(assetId, {
          label,
          interval_km: km ? Number(km) : null,
          interval_months: mo ? Number(mo) : null,
          last_serviced_at_odometer: lastKm ? Number(lastKm) : null,
        }),
      onClose,
    );

  return (
    <tr style={{ background: "var(--surface-sunk)" }}>
      <td colSpan={6} style={{ padding: "20px var(--pad)" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          {t("costs.new_maint")}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label={t("costs.field_name")} value={label} onChange={setLabel} placeholder={t("costs.ph_brake_pads")} />
          <LabeledInput label={t("costs.field_every_km")} value={km} onChange={setKm} type="number" />
          <LabeledInput label={t("costs.field_every_months")} value={mo} onChange={setMo} type="number" />
          <LabeledInput label={t("costs.field_last_serviced_km")} value={lastKm} onChange={setLastKm} type="number" />
          <EditActions busy={busy} disabled={!label.trim() || (!km && !mo)} onCancel={onClose} onSave={doCreate} saveLabel={t("costs.add")} />
        </div>
        {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
      </td>
    </tr>
  );
}

// ── Small reusable form bits ───────────────────────────────────────────
function LabeledInput({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input className="input" type={type} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function ActiveToggle({ active, onToggle }: { active: boolean; onToggle: (v: boolean) => void }) {
  const { t } = useTranslation();
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 12.5, color: "var(--muted)" }}>
      <input type="checkbox" checked={active} onChange={(e) => onToggle(e.target.checked)} />
      {t("costs.active_toggle")}
    </label>
  );
}
