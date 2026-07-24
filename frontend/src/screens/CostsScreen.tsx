import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { IntervalUnit, MaintenanceItem, TimeBasedCost, UsageBasedCost } from "../api/types";
import { Icon } from "../components/Icon";
import { ErrorState, LoadingState } from "../components/StateView";
import { useCurrency } from "../utils/currency";
import { fmtDate, fmtNumber, intervalDays } from "../utils/format";
import { maintenancePill } from "../utils/health";
import { useAsync } from "../utils/useAsync";

interface CostsScreenProps {
  assetId: string;
  onChanged: () => void;
}

type CostTab = "time" | "usage" | "maint";

export function CostsScreen({ assetId, onChanged }: CostsScreenProps) {
  const fmt = useCurrency();
  const [tab, setTab] = useState<CostTab>("time");
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

  if (asset.loading || time.loading || usage.loading || maint.loading) return <LoadingState label="Loading costs…" />;
  if (asset.error || time.error || usage.error || maint.error || !asset.data) {
    return (
      <ErrorState
        message={asset.error ?? time.error ?? usage.error ?? maint.error ?? "Failed to load."}
        onRetry={reloadAll}
      />
    );
  }

  const assetName = asset.data.name;
  const assetType = asset.data.type;
  const recommendedMonthly = asset.data.recommended_monthly_allocation;

  const timeRows = time.data ?? [];
  const usageRows = usage.data ?? [];
  const maintRows = maint.data ?? [];

  const timePerDay = timeRows
    .filter((t) => t.is_active)
    .reduce((s, t) => s + t.amount / intervalDays(t.interval_value, t.interval_unit), 0);
  const usageRate = usageRows.filter((u) => u.is_active).reduce((s, u) => s + u.amount_per_unit, 0);

  return (
    <div className="content fade-in">
      <div className="section-head">
        <div>
          <div className="eyebrow">Cost editor · {assetName}</div>
          <h1 className="h1" style={{ marginTop: 4 }}>
            Define what this {assetType} costs
          </h1>
        </div>
        <div className="seg">
          <button className="seg-btn" aria-pressed={tab === "time"} onClick={() => setTab("time")}>
            Time-based
          </button>
          <button className="seg-btn" aria-pressed={tab === "usage"} onClick={() => setTab("usage")}>
            Usage-based
          </button>
          <button className="seg-btn" aria-pressed={tab === "maint"} onClick={() => setTab("maint")}>
            Maintenance
          </button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 24 }}>
        <div className="kpi">
          <div className="kpi-label">Time-based total</div>
          <div className="num-lg">
            {fmt(timePerDay * 365, { decimals: 0 })}
            <span className="muted" style={{ fontSize: 14 }}>
              /yr
            </span>
          </div>
          <div className="kpi-sub">{fmt(timePerDay, { decimals: 2 })}/day equivalent</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Usage-based rate</div>
          <div className="num-lg">
            {fmt(usageRate, { decimals: 3 })}
            <span className="muted" style={{ fontSize: 14 }}>
              /unit
            </span>
          </div>
          <div className="kpi-sub">
            {usageRows.filter((u) => u.is_active).length} active component
            {usageRows.filter((u) => u.is_active).length === 1 ? "" : "s"}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Recommended allocation</div>
          <div className="num-lg">
            {fmt(recommendedMonthly, { decimals: 0 })}
            <span className="muted" style={{ fontSize: 14 }}>
              /mo
            </span>
          </div>
          <div className="kpi-sub">time-based + average usage</div>
        </div>
      </div>

      {tab === "time" && <TimeTable assetId={assetId} rows={timeRows} onChanged={reloadAll} />}
      {tab === "usage" && <UsageTable assetId={assetId} rows={usageRows} onChanged={reloadAll} />}
      {tab === "maint" && <MaintTable assetId={assetId} rows={maintRows} onChanged={reloadAll} />}
    </div>
  );
}

// ── Shared inline error + numeric parsing ──────────────────────────────
function useMutation(onChanged: () => void) {
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
      setError(err instanceof ApiError ? err.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, run };
}

// ── Time-based ─────────────────────────────────────────────────────────
function TimeTable({ assetId, rows, onChanged }: { assetId: string; rows: TimeBasedCost[]; onChanged: () => void }) {
  const fmt = useCurrency();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: "32%" }}>Cost</th>
            <th>Amount</th>
            <th>Every</th>
            <th>Per day</th>
            <th>Next due</th>
            <th style={{ width: 1 }}></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) =>
            editingId === t.id ? (
              <TimeEditRow
                key={t.id}
                assetId={assetId}
                row={t}
                onClose={() => setEditingId(null)}
                onChanged={onChanged}
              />
            ) : (
              <tr key={t.id} style={{ opacity: t.is_active ? 1 : 0.5 }}>
                <td className="col-name">
                  {t.label}
                  {!t.is_active && <span className="pill" style={{ marginLeft: 8 }}>inactive</span>}
                </td>
                <td className="col-num">{fmt(t.amount, { decimals: 0 })}</td>
                <td className="row-meta">
                  every {t.interval_value} {t.interval_unit}
                </td>
                <td className="col-num">{fmt(t.amount / intervalDays(t.interval_value, t.interval_unit), { decimals: 2 })}</td>
                <td className="row-meta">{t.next_due_date ? fmtDate(t.next_due_date) : "—"}</td>
                <td>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditingId(t.id)}>
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
          <Icon name="plus" size={14} /> Add a time-based cost…
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
          Editing · {row.label}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label="Name" value={label} onChange={setLabel} />
          <LabeledMoney label="Amount" value={amount} onChange={setAmount} />
          <LabeledInput label="Every (n)" value={value} onChange={setValue} type="number" />
          <div className="field">
            <label className="field-label">Unit</label>
            <select className="input" value={unit} onChange={(e) => setUnit(e.target.value as IntervalUnit)}>
              <option value="months">months</option>
              <option value="years">years</option>
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
          New time-based cost
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label="Name" value={label} onChange={setLabel} placeholder="Insurance" />
          <LabeledMoney label="Amount" value={amount} onChange={setAmount} />
          <LabeledInput label="Every (n)" value={value} onChange={setValue} type="number" />
          <div className="field">
            <label className="field-label">Unit</label>
            <select className="input" value={unit} onChange={(e) => setUnit(e.target.value as IntervalUnit)}>
              <option value="months">months</option>
              <option value="years">years</option>
            </select>
          </div>
          <EditActions busy={busy} disabled={!label.trim() || !amount} onCancel={onClose} onSave={create} saveLabel="Add" />
        </div>
        {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
      </td>
    </tr>
  );
}

// ── Usage-based ────────────────────────────────────────────────────────
function UsageTable({ assetId, rows, onChanged }: { assetId: string; rows: UsageBasedCost[]; onChanged: () => void }) {
  const fmt = useCurrency();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: "40%" }}>Component</th>
            <th>Rate</th>
            <th>Per 100</th>
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
                  {!u.is_active && <span className="pill" style={{ marginLeft: 8 }}>inactive</span>}
                </td>
                <td className="col-num">
                  {fmt(u.amount_per_unit, { decimals: 3 })}/{u.usage_unit}
                </td>
                <td className="col-num">{fmt(u.amount_per_unit * 100, { decimals: 2 })}</td>
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
          <Icon name="plus" size={14} /> Add a usage-based cost…
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
          Editing · {row.label}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label="Name" value={label} onChange={setLabel} />
          <LabeledMoney label="Per unit" value={rate} onChange={setRate} step="0.001" />
          <LabeledInput label="Unit" value={unit} onChange={setUnit} />
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
  const { error, busy, run } = useMutation(onChanged);

  const create = () =>
    run(() => api.createUsageBasedCost(assetId, { label, amount_per_unit: Number(rate), usage_unit: unit }), onClose);

  return (
    <tr style={{ background: "var(--surface-sunk)" }}>
      <td colSpan={4} style={{ padding: "20px var(--pad)" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          New usage-based cost
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label="Name" value={label} onChange={setLabel} placeholder="Fuel" />
          <LabeledMoney label="Per unit" value={rate} onChange={setRate} step="0.001" />
          <LabeledInput label="Unit" value={unit} onChange={setUnit} />
          <EditActions busy={busy} disabled={!label.trim() || !rate} onCancel={onClose} onSave={create} saveLabel="Add" />
        </div>
        {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
      </td>
    </tr>
  );
}

// ── Maintenance ────────────────────────────────────────────────────────
function MaintTable({ assetId, rows, onChanged }: { assetId: string; rows: MaintenanceItem[]; onChanged: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: "32%" }}>Item</th>
            <th>Replace every</th>
            <th>Last serviced</th>
            <th>Status</th>
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
                  {!m.is_active && <span className="pill" style={{ marginLeft: 8 }}>inactive</span>}
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
          <Icon name="plus" size={14} /> Add a maintenance item…
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
      <td colSpan={5} style={{ padding: "20px var(--pad)" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          Editing · {row.label}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label="Name" value={label} onChange={setLabel} />
          <LabeledInput label="Every (km)" value={km} onChange={setKm} type="number" />
          <LabeledInput label="Every (months)" value={mo} onChange={setMo} type="number" />
          <LabeledInput label="Last serviced (km)" value={lastKm} onChange={setLastKm} type="number" />
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
      <td colSpan={5} style={{ padding: "20px var(--pad)" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          New maintenance item
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <LabeledInput label="Name" value={label} onChange={setLabel} placeholder="Brake pads" />
          <LabeledInput label="Every (km)" value={km} onChange={setKm} type="number" />
          <LabeledInput label="Every (months)" value={mo} onChange={setMo} type="number" />
          <LabeledInput label="Last serviced (km)" value={lastKm} onChange={setLastKm} type="number" />
          <EditActions busy={busy} disabled={!label.trim() || (!km && !mo)} onCancel={onClose} onSave={doCreate} saveLabel="Add" />
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
  saveLabel = "Save",
}: {
  busy: boolean;
  disabled?: boolean;
  onCancel: () => void;
  onSave: () => void;
  saveLabel?: string;
}) {
  return (
    <div style={{ display: "flex", gap: 8 }}>
      <button className="btn btn-sm" onClick={onCancel}>
        Cancel
      </button>
      <button className="btn btn-primary btn-sm" disabled={busy || disabled} onClick={onSave}>
        {busy ? "…" : saveLabel}
      </button>
    </div>
  );
}

function ActiveToggle({ active, onToggle }: { active: boolean; onToggle: (v: boolean) => void }) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 12.5, color: "var(--muted)" }}>
      <input type="checkbox" checked={active} onChange={(e) => onToggle(e.target.checked)} />
      Active (drives future allocations)
    </label>
  );
}
