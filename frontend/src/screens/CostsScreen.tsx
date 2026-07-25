import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api/client";
import type { IntervalUnit, MaintenanceItem, TimeBasedCost, UsageBasedCost } from "../api/types";
import { Icon } from "../components/Icon";
import { ErrorState, LoadingState } from "../components/StateView";
import { useCurrency } from "../utils/currency";
import { fmtDate, fmtNumber } from "../utils/format";
import { maintenancePill } from "../utils/maintenanceStatus";
import { useAsync } from "../utils/useAsync";

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
  const [manualEditing, setManualEditing] = useState(false);
  const asset = useAsync(() => api.getAsset(assetId), [assetId]);
  const time = useAsync(() => api.listTimeBasedCosts(assetId), [assetId]);
  const usage = useAsync(() => api.listUsageBasedCosts(assetId), [assetId]);
  const maint = useAsync(() => api.listMaintenanceItems(assetId), [assetId]);

  const reloadAll = () => {
    asset.reload();
    time.reload();
    usage.reload();
    maint.reload();
    onChanged();
  };

  if (asset.loading || time.loading || usage.loading || maint.loading) return <LoadingState label={t("costs.loading")} />;
  if (asset.error || time.error || usage.error || maint.error || !asset.data) {
    return (
      <ErrorState
        message={asset.error ?? time.error ?? usage.error ?? maint.error ?? t("costs.failed_load")}
        onRetry={reloadAll}
      />
    );
  }

  const assetName = asset.data.name;
  const assetType = asset.data.type;
  const recommendedMonthly = asset.data.recommended_monthly_allocation;
  const manualExtra = asset.data.manual_extra_monthly;
  const manualExtraRecommended = asset.data.manual_extra_recommended;
  const avgMonthlyUsage = asset.data.average_monthly_usage;

  const timeRows = time.data ?? [];
  const usageRows = usage.data ?? [];
  const maintRows = maint.data ?? [];

  const activeTimeRows = timeRows.filter((t) => t.is_active);
  const timePerDay = activeTimeRows.reduce((sum, row) => sum + row.daily_rate, 0);
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

      {manualEditing && (
        <ManualExtraEditor
          assetId={assetId}
          current={manualExtra}
          recommended={manualExtraRecommended}
          onClose={() => setManualEditing(false)}
          onChanged={reloadAll}
        />
      )}

      <div className="kpi-grid kpi-grid-4" style={{ marginBottom: 24 }}>
        <div className="kpi">
          <div className="kpi-label">{t("costs.time_total")}</div>
          <div className="num-lg">
            {fmt(timePerYear, { decimals: 0 })}
            <span className="muted" style={{ fontSize: 14 }}>
              {t("costs.per_yr")}
            </span>
          </div>
          <div className="kpi-sub">{t("costs.per_day_equivalent", { amount: fmt(timePerDay, { decimals: 2 }) })}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">{t("costs.usage_rate")}</div>
          <div className="num-lg">
            {fmt(usageRate, { decimals: 3 })}
            <span className="muted" style={{ fontSize: 14 }}>
              {t("costs.per_unit")}
            </span>
          </div>
          <div className="kpi-sub">
            {t("costs.active_components", { count: usageRows.filter((u) => u.is_active).length })}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">{t("costs.manual_extra")}</div>
          <div className="num-lg">
            {fmt(manualExtra, { decimals: 0 })}
            <span className="muted" style={{ fontSize: 14 }}>
              {t("costs.per_mo")}
            </span>
          </div>
          <div className="kpi-sub">
            {manualExtraRecommended > 0
              ? t("costs.manual_extra_recommended_sub", { amount: fmt(manualExtraRecommended, { decimals: 0 }) })
              : t("costs.manual_extra_sub")}
          </div>
          <button className="kpi-link" onClick={() => setManualEditing(true)}>
            <Icon name="edit" size={11} /> {t("costs.manual_extra_edit")}
          </button>
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

      {tab === "time" && <TimeTable assetId={assetId} rows={timeRows} onChanged={reloadAll} />}
      {tab === "usage" && <UsageTable assetId={assetId} rows={usageRows} avgMonthlyUsage={avgMonthlyUsage} onChanged={reloadAll} />}
      {tab === "maint" && <MaintTable assetId={assetId} rows={maintRows} onChanged={reloadAll} />}
    </div>
  );
}

// ── Manual extra ─────────────────────────────────────────────────────────
function ManualExtraEditor({
  assetId,
  current,
  recommended,
  onClose,
  onChanged,
}: {
  assetId: string;
  current: number;
  recommended: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [amount, setAmount] = useState(String(current));
  const { error, busy, run } = useMutation(onChanged);

  const save = () => run(() => api.updateManualExtra(assetId, Number(amount)), onClose);

  return (
    <div className="card card-pad" style={{ marginBottom: 20, background: "var(--surface-sunk)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 24, flexWrap: "wrap" }}>
        <div style={{ maxWidth: 380 }}>
          <div className="card-title" style={{ marginBottom: 6 }}>
            {t("costs.manual_extra_panel_title")}
          </div>
          <div className="muted" style={{ fontSize: 12.5, lineHeight: 1.5, marginBottom: 12 }}>
            {t("costs.manual_extra_panel_desc")}
          </div>
          <LabeledMoney label={t("costs.field_extra_per_month")} value={amount} onChange={setAmount} />
        </div>
        <div style={{ minWidth: 240, borderLeft: "1px solid var(--line)", paddingLeft: 24 }}>
          <div className="card-title" style={{ marginBottom: 6 }}>
            {t("costs.manual_extra_recommendation_title")}
          </div>
          <div className="muted" style={{ fontSize: 12.5, lineHeight: 1.6 }}>
            {t("costs.manual_extra_recommendation_desc")}
          </div>
          <div style={{ marginTop: 10, display: "flex", alignItems: "baseline", gap: 8 }}>
            <span className="num-md">
              {fmt(recommended, { decimals: 0 })}
              <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
                {t("costs.per_mo")}
              </span>
            </span>
            <button className="btn btn-sm btn-primary" onClick={() => setAmount(String(recommended))}>
              {t("costs.use_this")}
            </button>
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <EditActions busy={busy} onCancel={onClose} onSave={save} />
      </div>
      {error && (
        <div className="error-banner" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
    </div>
  );
}

// ── Shared inline error + numeric parsing ──────────────────────────────
function useMutation(onChanged: () => void) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>, done: () => void) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      done();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("costs.save_failed"));
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, run };
}

// ── Time-based ─────────────────────────────────────────────────────────
function TimeTable({ assetId, rows, onChanged }: { assetId: string; rows: TimeBasedCost[]; onChanged: () => void }) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

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
              <tr key={row.id} style={{ opacity: row.is_active ? 1 : 0.5 }}>
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
                <td>
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
}: {
  assetId: string;
  rows: UsageBasedCost[];
  avgMonthlyUsage: number;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

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
              <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
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
                <td>
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
function MaintTable({ assetId, rows, onChanged }: { assetId: string; rows: MaintenanceItem[]; onChanged: () => void }) {
  const { t } = useTranslation();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

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
              <tr key={m.id} style={{ opacity: m.is_active ? 1 : 0.5 }}>
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
                <td>
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

function LabeledMoney({ label, value, onChange, step }: { label: string; value: string; onChange: (v: string) => void; step?: string }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <div className="input-prefix-wrap">
        <span className="input-prefix">$</span>
        <input className="input mono" type="number" step={step} value={value} onChange={(e) => onChange(e.target.value)} />
      </div>
    </div>
  );
}

function EditActions({
  busy,
  disabled,
  onCancel,
  onSave,
  saveLabel,
}: {
  busy: boolean;
  disabled?: boolean;
  onCancel: () => void;
  onSave: () => void;
  saveLabel?: string;
}) {
  const { t } = useTranslation();
  return (
    <div style={{ display: "flex", gap: 8 }}>
      <button className="btn btn-sm" onClick={onCancel}>
        {t("costs.cancel")}
      </button>
      <button className="btn btn-primary btn-sm" disabled={busy || disabled} onClick={onSave}>
        {busy ? "…" : (saveLabel ?? t("costs.save"))}
      </button>
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
