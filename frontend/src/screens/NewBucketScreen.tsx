import { Fragment, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { CreateAssetRequest } from "../api/types";
import { Icon } from "../components/Icon";
import { Illo } from "../components/Illustrations";
import type { IlloKind } from "../utils/assetType";
import { fmtNumber } from "../utils/format";

interface NewBucketScreenProps {
  onCancel: () => void;
  onCreated: (assetId: string) => void;
}

type Period = "month" | "year" | "2 years" | "usage";
interface DraftCost {
  id: string;
  name: string;
  period: Period;
  amount: number;
  unit?: string;
}

interface TypeOption {
  kind: IlloKind;
  name: string;
  desc: string;
  bg: string;
  assetType: string;
}

const TYPES: TypeOption[] = [
  { kind: "car", name: "Vehicle", desc: "Car, motorcycle, or anything with an odometer.", bg: "#DDE8F8", assetType: "vehicle" },
  { kind: "house", name: "Property", desc: "House, apartment, or any place you maintain.", bg: "#F8E5E2", assetType: "house" },
  { kind: "pet", name: "Pet", desc: "A dog, cat, or another companion with recurring care.", bg: "#F8EBD8", assetType: "pet" },
];

const SUGGESTED: Record<IlloKind, DraftCost[]> = {
  car: [
    draft("Insurance", "year", 1280),
    draft("Registration", "year", 184),
    draft("Roadside assistance", "year", 96),
    draft("Fuel", "usage", 0.118, "km"),
    draft("Tire wear", "usage", 0.041, "km"),
  ],
  house: [
    draft("Property tax", "year", 4200),
    draft("Home insurance", "year", 1140),
    draft("HVAC service", "year", 280),
    draft("Roof reserve", "year", 1800),
  ],
  pet: [draft("Vet checkup", "year", 280), draft("Vaccinations", "year", 180), draft("Food", "month", 65), draft("Grooming", "month", 70)],
};

const PERIOD_DAYS: Record<Exclude<Period, "usage">, number> = { month: 30, year: 365, "2 years": 730 };

function draft(name: string, period: Period, amount: number, unit?: string): DraftCost {
  return { id: Math.random().toString(36).slice(2, 8), name, period, amount, unit };
}

function periodDays(period: Period): number {
  return period === "usage" ? 365 : PERIOD_DAYS[period];
}

export function NewBucketScreen({ onCancel, onCreated }: NewBucketScreenProps) {
  const [step, setStep] = useState(1);
  const [type, setType] = useState<TypeOption | null>(null);
  const [name, setName] = useState("");
  const [meta, setMeta] = useState<Record<string, string>>({});
  const [costs, setCosts] = useState<DraftCost[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const perDay = useMemo(
    () =>
      costs.reduce((s, c) => (c.period === "usage" ? s : s + c.amount / PERIOD_DAYS[c.period]), 0),
    [costs],
  );
  const monthlyEst = perDay * 30;
  const yearlyEst = perDay * 365;

  const addCost = (c: DraftCost) => setCosts((arr) => [...arr, { ...c, id: Math.random().toString(36).slice(2, 8) }]);
  const removeCost = (id: string) => setCosts((arr) => arr.filter((c) => c.id !== id));
  const updateCost = (id: string, patch: Partial<DraftCost>) =>
    setCosts((arr) => arr.map((c) => (c.id === id ? { ...c, ...patch } : c)));

  const canNext = step === 1 ? !!type : step === 2 ? !!name.trim() : true;

  const submit = async () => {
    if (!type) return;
    setSubmitting(true);
    setError(null);
    try {
      const req = buildCreateRequest(type, name, meta);
      const created = await api.createAsset(req);
      const id = created.asset.id;
      // Post each drafted cost row individually (the API creates rows one at a time).
      for (const c of costs) {
        if (c.period === "usage") {
          await api.createUsageBasedCost(id, { label: c.name || "Usage cost", amount_per_unit: c.amount, usage_unit: c.unit || "km" });
        } else {
          await api.createTimeBasedCost(id, {
            label: c.name || "Cost",
            amount: c.amount,
            interval_value: c.period === "2 years" ? 2 : 1,
            interval_unit: c.period === "month" ? "months" : "years",
          });
        }
      }
      onCreated(id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the bucket.");
      setSubmitting(false);
    }
  };

  return (
    <div className="content fade-in">
      <div className="wizard">
        <div className="section-head" style={{ marginBottom: 6 }}>
          <div>
            <h1 className="h1">New bucket</h1>
            <div className="muted" style={{ fontSize: 14, marginTop: 4 }}>
              Set up a tracked item — Allocio figures out the monthly allocation for you.
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onCancel}>
            Cancel
          </button>
        </div>

        <WizardSteps step={step} steps={["Type", "Details", "Costs", "Review"]} />

        {step === 1 && <Step1 selected={type} onSelect={setType} />}
        {step === 2 && <Step2 type={type!} name={name} setName={setName} meta={meta} setMeta={setMeta} />}
        {step === 3 && (
          <Step3
            type={type!}
            costs={costs}
            onAdd={addCost}
            onRemove={removeCost}
            onUpdate={updateCost}
          />
        )}
        {step === 4 && <Step4 type={type!} name={name} meta={meta} costs={costs} monthlyEst={monthlyEst} yearlyEst={yearlyEst} perDay={perDay} />}

        {error && (
          <div className="error-banner" style={{ marginTop: 16 }}>
            {error}
          </div>
        )}

        <div className="wizard-footer">
          <button className="btn btn-outline" onClick={() => (step > 1 ? setStep(step - 1) : onCancel())}>
            ← {step > 1 ? "Back" : "Cancel"}
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {step >= 3 && (
              <div style={{ textAlign: "right" }}>
                <div className="muted" style={{ fontSize: 11.5 }}>
                  Estimated allocation
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, fontFeatureSettings: '"tnum"' }}>
                  ${fmtNumber(monthlyEst)}
                  <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
                    /mo
                  </span>
                </div>
              </div>
            )}
            {step < 4 ? (
              <button className="btn btn-primary" disabled={!canNext} onClick={() => canNext && setStep(step + 1)}>
                Continue <Icon name="arrowRight" size={13} />
              </button>
            ) : (
              <button className="btn btn-primary" disabled={submitting} onClick={submit}>
                <Icon name="check" size={14} /> {submitting ? "Creating…" : "Create bucket"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function buildCreateRequest(type: TypeOption, name: string, meta: Record<string, string>): CreateAssetRequest {
  if (type.kind === "car") {
    return {
      name,
      template: "vehicle",
      vehicle: {
        make: meta.make || null,
        year: meta.year ? Number(meta.year) : null,
        starting_odometer: meta.odometer ? Number(meta.odometer.replace(/[^\d]/g, "")) : 0,
      },
      subtitle: subtitleFromMeta(meta) || null,
    };
  }
  const attributes = Object.fromEntries(Object.entries(meta).filter(([, v]) => v.trim() !== ""));
  return {
    name,
    type: type.assetType,
    subtitle: subtitleFromMeta(meta) || null,
    attributes: Object.keys(attributes).length > 0 ? attributes : null,
  };
}

function subtitleFromMeta(meta: Record<string, string>): string {
  return Object.values(meta)
    .filter((v) => v.trim() !== "")
    .join(" · ");
}

function WizardSteps({ step, steps }: { step: number; steps: string[] }) {
  return (
    <div className="wizard-steps">
      {steps.map((label, i) => {
        const n = i + 1;
        const cls = n < step ? "done" : n === step ? "active" : "";
        return (
          <Fragment key={i}>
            <div className={`wizard-step ${cls}`}>
              <span className="wizard-step-num">{n < step ? "✓" : n}</span>
              {label}
            </div>
            {i < steps.length - 1 && <span className="wizard-step-bar" />}
          </Fragment>
        );
      })}
    </div>
  );
}

function Step1({ selected, onSelect }: { selected: TypeOption | null; onSelect: (t: TypeOption) => void }) {
  return (
    <div className="card card-pad">
      <div className="card-title" style={{ marginBottom: 4 }}>
        What are you tracking?
      </div>
      <div className="card-sub" style={{ marginBottom: 18 }}>
        Pick a category — it sets the icon, the profile fields, and the suggested costs.
      </div>
      <div className="type-grid">
        {TYPES.map((t) => (
          <button key={t.kind} className="type-card" aria-pressed={selected?.kind === t.kind} onClick={() => onSelect(t)}>
            <div className="type-illo" style={{ background: t.bg }}>
              <Illo kind={t.kind} />
            </div>
            <div className="type-card-body">
              <div className="type-card-name">{t.name}</div>
              <div className="type-card-desc">{t.desc}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

interface MetaField {
  key: string;
  label: string;
  placeholder: string;
  suffix?: string;
  short?: boolean;
}

function Step2({
  type,
  name,
  setName,
  meta,
  setMeta,
}: {
  type: TypeOption;
  name: string;
  setName: (v: string) => void;
  meta: Record<string, string>;
  setMeta: (m: Record<string, string>) => void;
}) {
  const fields: MetaField[] =
    type.kind === "car"
      ? [
          { key: "make", label: "Make & model", placeholder: "Honda Civic" },
          { key: "year", label: "Year", placeholder: "2019", short: true },
          { key: "odometer", label: "Current odometer", placeholder: "47213", suffix: "km", short: true },
        ]
      : type.kind === "house"
        ? [
            { key: "address", label: "Address or label", placeholder: "Cedar St. apartment" },
            { key: "built", label: "Year built", placeholder: "1978", short: true },
            { key: "size", label: "Size", placeholder: "85", suffix: "m²", short: true },
          ]
        : [
            { key: "breed", label: "Breed", placeholder: "Border Collie" },
            { key: "age", label: "Age", placeholder: "4", suffix: "years", short: true },
            { key: "weight", label: "Weight", placeholder: "18", suffix: "kg", short: true },
          ];

  return (
    <div className="card card-pad">
      <div className="card-title" style={{ marginBottom: 4 }}>
        Tell us about it
      </div>
      <div className="card-sub" style={{ marginBottom: 22 }}>
        Just the basics — you can edit any of this later.
      </div>

      <div style={{ display: "grid", gap: 16 }}>
        <div className="field">
          <label className="field-label">Bucket name</label>
          <input
            className="input"
            placeholder={type.kind === "car" ? "Honda Civic" : type.kind === "house" ? "Cedar St." : "Maya"}
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          {fields.map((f) => (
            <div key={f.key} className="field" style={{ gridColumn: f.short ? "auto" : "1 / -1" }}>
              <label className="field-label">{f.label}</label>
              <div className="input-prefix-wrap">
                <input
                  className="input"
                  placeholder={f.placeholder}
                  value={meta[f.key] || ""}
                  onChange={(e) => setMeta({ ...meta, [f.key]: e.target.value })}
                />
                {f.suffix && <span className="input-suffix">{f.suffix}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Step3({
  type,
  costs,
  onAdd,
  onRemove,
  onUpdate,
}: {
  type: TypeOption;
  costs: DraftCost[];
  onAdd: (c: DraftCost) => void;
  onRemove: (id: string) => void;
  onUpdate: (id: string, patch: Partial<DraftCost>) => void;
}) {
  const suggestions = SUGGESTED[type.kind].filter((s) => !costs.some((c) => c.name === s.name));

  return (
    <>
      {type.kind === "car" && (
        <div className="card card-pad" style={{ marginBottom: 16, background: "var(--surface-sunk)" }}>
          <div className="row-meta" style={{ lineHeight: 1.5 }}>
            The vehicle template already seeds common costs (insurance, registration, fuel reserve, tire wear…). Add anything
            extra below — you can fine-tune everything on the Costs tab afterwards.
          </div>
        </div>
      )}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ padding: "20px var(--pad) 14px" }}>
          <div className="card-title">Costs</div>
          <div className="card-sub">Add recurring costs and per-use rates. Allocio averages them into a steady monthly draw.</div>
        </div>

        {costs.length === 0 ? (
          <div style={{ padding: "14px var(--pad) 18px", borderTop: "1px solid var(--line-soft)" }}>
            <div className="muted" style={{ fontSize: 13 }}>
              No costs added yet. Pick from the suggestions below or add a custom one.
            </div>
          </div>
        ) : (
          costs.map((c) => <CostRow key={c.id} cost={c} onUpdate={(p) => onUpdate(c.id, p)} onRemove={() => onRemove(c.id)} />)
        )}

        <div className="add-row" onClick={() => onAdd(draft("", "year", 0))}>
          <Icon name="plus" size={14} /> Add a custom cost…
        </div>
      </div>

      {suggestions.length > 0 && (
        <div className="card card-pad">
          <div className="card-title" style={{ fontSize: 13, marginBottom: 10 }}>
            Suggested for {type.name.toLowerCase()}
          </div>
          <div className="suggested-list">
            {suggestions.map((s) => (
              <button key={s.id} className="suggested-chip" onClick={() => onAdd(s)}>
                <Icon name="plus" size={11} stroke={2.4} /> {s.name} ·{" "}
                {s.period === "usage" ? `$${s.amount}/${s.unit}` : `$${s.amount}/${s.period}`}
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function CostRow({ cost, onUpdate, onRemove }: { cost: DraftCost; onUpdate: (p: Partial<DraftCost>) => void; onRemove: () => void }) {
  return (
    <div className="cost-row">
      <input className="input" placeholder="Cost name" value={cost.name} onChange={(e) => onUpdate({ name: e.target.value })} />
      <div className="input-prefix-wrap">
        <span className="input-prefix">$</span>
        <input
          className="input mono"
          type="number"
          value={cost.amount}
          onChange={(e) => onUpdate({ amount: Number(e.target.value) })}
        />
      </div>
      <select className="input" value={cost.period} onChange={(e) => onUpdate({ period: e.target.value as Period })}>
        <option value="month">per month</option>
        <option value="year">per year</option>
        <option value="2 years">every 2 years</option>
        <option value="usage">per use</option>
      </select>
      {cost.period === "usage" ? (
        <select className="input" value={cost.unit || "km"} onChange={(e) => onUpdate({ unit: e.target.value })}>
          <option value="km">/ km</option>
          <option value="hour">/ hour</option>
          <option value="use">/ use</option>
        </select>
      ) : (
        <div className="row-meta" style={{ textAlign: "right" }}>
          ≈ ${(cost.amount / PERIOD_DAYS[cost.period]).toFixed(2)}/day
        </div>
      )}
      <button className="cost-row-x" aria-label="Remove" onClick={onRemove}>
        ×
      </button>
    </div>
  );
}

function Step4({
  type,
  name,
  meta,
  costs,
  monthlyEst,
  yearlyEst,
  perDay,
}: {
  type: TypeOption;
  name: string;
  meta: Record<string, string>;
  costs: DraftCost[];
  monthlyEst: number;
  yearlyEst: number;
  perDay: number;
}) {
  const usageCosts = costs.filter((c) => c.period === "usage");
  const timeCosts = costs.filter((c) => c.period !== "usage");

  return (
    <div className="stack">
      <div className="allocation-callout">
        <div>
          <div className="label">Estimated monthly allocation</div>
          <div className="num">${fmtNumber(monthlyEst)}</div>
          <div className="sub">
            ${perDay.toFixed(2)}/day · ${fmtNumber(yearlyEst)}/year
            {type.kind === "car" ? " · plus vehicle template costs" : ""}
          </div>
        </div>
        <div style={{ width: 140, height: 100, background: "rgba(255,255,255,.12)", borderRadius: 12, padding: 8 }}>
          <div style={{ background: type.bg, borderRadius: 10, width: "100%", height: "100%", display: "grid", placeItems: "center" }}>
            <Illo kind={type.kind} />
          </div>
        </div>
      </div>

      <div className="card">
        <div style={{ padding: "20px var(--pad) 14px" }}>
          <div className="card-title">{name || "Untitled"} · review</div>
          <div className="card-sub">{subtitleFromMeta(meta) || "No details"}</div>
        </div>

        {timeCosts.map((c) => (
          <div key={c.id} className="review-row">
            <div>
              <div>{c.name || "(unnamed)"}</div>
              <div className="row-meta" style={{ marginTop: 2 }}>
                ${c.amount.toFixed(2)} per {c.period} · ${(c.amount / periodDays(c.period)).toFixed(2)}/day
              </div>
            </div>
            <div className="review-row-amt">
              ${fmtNumber((c.amount / periodDays(c.period)) * 30)}
              <span className="muted" style={{ fontSize: 11.5, fontWeight: 400 }}>
                /mo
              </span>
            </div>
          </div>
        ))}

        {usageCosts.length > 0 && (
          <>
            <div style={{ padding: "14px var(--pad) 6px", borderTop: "1px solid var(--line)" }}>
              <div className="eyebrow">Usage-based (charged at check-in)</div>
            </div>
            {usageCosts.map((c) => (
              <div key={c.id} className="review-row">
                <div>
                  <div>{c.name || "(unnamed)"}</div>
                  <div className="row-meta" style={{ marginTop: 2 }}>
                    ${c.amount.toFixed(3)} per {c.unit || "km"}
                  </div>
                </div>
                <div className="review-row-amt muted" style={{ fontWeight: 400, fontSize: 12.5 }}>
                  variable
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="card card-pad" style={{ background: "var(--surface-sunk)" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 8,
              background: "var(--accent-soft)",
              color: "var(--accent-ink)",
              display: "grid",
              placeItems: "center",
              flexShrink: 0,
            }}
          >
            <Icon name="bell" size={15} />
          </div>
          <div>
            <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 4 }}>What happens next</div>
            <div className="muted" style={{ fontSize: 12.5, lineHeight: 1.55 }}>
              Allocio starts accruing{" "}
              <strong style={{ color: "var(--ink)" }}>${perDay.toFixed(2)}/day</strong> into this bucket. Run a monthly
              check-in to log usage and post the accrual.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
