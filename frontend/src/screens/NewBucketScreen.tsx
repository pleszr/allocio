import { Fragment, useEffect, useMemo, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api/client";
import type { AssetTemplateCatalog, CreateAssetRequest, IntervalUnit, TemplateCostOverride } from "../api/types";
import { Icon } from "../components/Icon";
import { Illo } from "../components/Illustrations";
import type { IlloKind } from "../utils/assetType";
import { useCurrency, useCurrencyCode } from "../utils/currency";
import { fmtNumber, intervalDays } from "../utils/format";

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
  nameKey: string;
  descKey: string;
  bg: string;
  assetType: string;
}

// One review line for Step 4 / the running estimate. `monthly` is null for usage-based
// (variable) rows, which are excluded from the steady monthly figure.
interface ReviewLine {
  id: string;
  name: string;
  monthly: number | null;
  sub: string;
}

const TYPES: TypeOption[] = [
  { kind: "car", nameKey: "newBucket.type_vehicle_name", descKey: "newBucket.type_vehicle_desc", bg: "#DDE8F8", assetType: "vehicle" },
  { kind: "house", nameKey: "newBucket.type_house_name", descKey: "newBucket.type_house_desc", bg: "#F8E5E2", assetType: "house" },
  { kind: "pet", nameKey: "newBucket.type_pet_name", descKey: "newBucket.type_pet_desc", bg: "#F8EBD8", assetType: "pet" },
];

// Suggestions for non-vehicle types stay hardcoded (no backend catalog exists for them).
// The vehicle path no longer uses this map — it reads the real template catalog instead.
const SUGGESTED: Record<Exclude<IlloKind, "car">, DraftCost[]> = {
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

function allCatalogKeys(catalog: AssetTemplateCatalog): Set<string> {
  return new Set([
    ...catalog.time_based_costs.map((c) => c.technical_key),
    ...catalog.usage_based_costs.map((c) => c.technical_key),
    ...catalog.maintenance_items.map((m) => m.technical_key),
  ]);
}

// Human-readable recurrence for a catalog time-based row (e.g. "/yr", "/mo", "/6 mo").
function intervalLabel(value: number, unit: "months" | "years"): string {
  if (unit === "months" && value === 12) return "/yr";
  if (unit === "months" && value === 1) return "/mo";
  if (unit === "years" && value === 1) return "/yr";
  return `/${value} ${unit === "years" ? "yr" : "mo"}`;
}

// Human-readable interval for a catalog maintenance row (km and/or months).
function maintenanceDetail(interval_km: number | null, interval_months: number | null, t: TFunction): string {
  const parts: string[] = [];
  if (interval_km != null) parts.push(`${fmtNumber(interval_km)} km`);
  if (interval_months != null) parts.push(`${interval_months} mo`);
  return parts.length > 0 ? t("newBucket.maint_every", { parts: parts.join(" / ") }) : t("newBucket.no_fixed_interval");
}

// A vehicle template row's label, translated by its stable `technical_key`; falls back to the
// backend-supplied English label if a translation key is missing (e.g. a future untranslated row).
function templateLabel(t: TFunction, technicalKey: string, fallback: string): string {
  return t(`templates.vehicle.${technicalKey}.label`, { defaultValue: fallback });
}

interface CatalogOverride {
  amount: number;
  interval_value?: number; // time-based rows only
  interval_unit?: IntervalUnit; // time-based rows only
}

export function NewBucketScreen({ onCancel, onCreated }: NewBucketScreenProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const currencyCode = useCurrencyCode();
  const periodLabel = (p: Period) => t(`newBucket.period_noun_${p === "2 years" ? "2years" : p}`);
  const [step, setStep] = useState(1);
  const [type, setType] = useState<TypeOption | null>(null);
  const [name, setName] = useState("");
  const [meta, setMeta] = useState<Record<string, string>>({});
  const [costs, setCosts] = useState<DraftCost[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Vehicle template catalog + the user's row selection. Owned here so it survives Back/Continue.
  const isVehicle = type?.kind === "car";
  const [catalog, setCatalog] = useState<AssetTemplateCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  // The user-edited amount/interval for each time-based/usage-based catalog row, seeded from the
  // template default in the owner's currency once, then owned by the user. Maintenance items don't
  // participate here — they have no curated amount to edit.
  const [catalogOverrides, setCatalogOverrides] = useState<Record<string, CatalogOverride>>({});

  const loadCatalog = () => {
    setCatalogLoading(true);
    setCatalogError(null);
    api
      .getTemplateCatalog("vehicle")
      .then((c) => {
        setCatalog(c);
        // Seed the default selection to every row the first time the catalog arrives.
        // The effect below never re-fetches once `catalog` is set, so this seeds only once
        // and the user's later edits are preserved across step navigation.
        setSelectedKeys(allCatalogKeys(c));
        setCatalogOverrides({
          ...Object.fromEntries(
            c.time_based_costs.map((row) => [
              row.technical_key,
              { amount: row.amounts[currencyCode], interval_value: row.interval_value, interval_unit: row.interval_unit },
            ]),
          ),
          ...Object.fromEntries(
            c.usage_based_costs.map((row) => [row.technical_key, { amount: row.amounts_per_unit[currencyCode] }]),
          ),
        });
      })
      .catch((err: unknown) => setCatalogError(err instanceof ApiError ? err.message : t("newBucket.catalog_error")))
      .finally(() => setCatalogLoading(false));
  };

  const updateCatalogOverride = (key: string, patch: Partial<CatalogOverride>) =>
    setCatalogOverrides((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));

  // Fetch the vehicle catalog once, as soon as the vehicle path is chosen.
  useEffect(() => {
    if (isVehicle && !catalog && !catalogLoading && !catalogError) loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isVehicle]);

  const toggleKey = (key: string) =>
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const setGroup = (keys: string[], on: boolean) =>
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      for (const k of keys) {
        if (on) next.add(k);
        else next.delete(k);
      }
      return next;
    });

  const catalogTimePerDay = useMemo(() => {
    if (!isVehicle || !catalog) return 0;
    return catalog.time_based_costs
      .filter((c) => selectedKeys.has(c.technical_key))
      .reduce((s, c) => {
        const o = catalogOverrides[c.technical_key];
        const amount = o?.amount ?? c.amounts[currencyCode];
        const intervalValue = o?.interval_value ?? c.interval_value;
        const intervalUnit = o?.interval_unit ?? c.interval_unit;
        return s + amount / intervalDays(intervalValue, intervalUnit);
      }, 0);
  }, [isVehicle, catalog, selectedKeys, catalogOverrides, currencyCode]);

  const draftPerDay = useMemo(
    () => costs.reduce((s, c) => (c.period === "usage" ? s : s + c.amount / PERIOD_DAYS[c.period]), 0),
    [costs],
  );

  const perDay = draftPerDay + catalogTimePerDay;
  const monthlyEst = perDay * 30;
  const yearlyEst = perDay * 365;

  // Combined review lines: selected catalog rows (vehicle) plus custom drafts.
  const reviewTimeLines = useMemo<ReviewLine[]>(() => {
    const lines: ReviewLine[] = [];
    if (isVehicle && catalog) {
      for (const c of catalog.time_based_costs) {
        if (!selectedKeys.has(c.technical_key)) continue;
        const o = catalogOverrides[c.technical_key];
        const amount = o?.amount ?? c.amounts[currencyCode];
        const intervalValue = o?.interval_value ?? c.interval_value;
        const intervalUnit = o?.interval_unit ?? c.interval_unit;
        const perDayLine = amount / intervalDays(intervalValue, intervalUnit);
        lines.push({
          id: c.technical_key,
          name: templateLabel(t, c.technical_key, c.label),
          monthly: perDayLine * 30,
          sub: `${fmtNumber(amount)}${intervalLabel(intervalValue, intervalUnit)}`,
        });
      }
    }
    for (const c of costs.filter((c) => c.period !== "usage")) {
      lines.push({
        id: c.id,
        name: c.name || t("newBucket.unnamed"),
        monthly: (c.amount / periodDays(c.period)) * 30,
        sub: t("newBucket.review_per_period", { amount: fmt(c.amount, { decimals: 2 }), period: periodLabel(c.period) }),
      });
    }
    return lines;
  }, [isVehicle, catalog, selectedKeys, catalogOverrides, currencyCode, costs, fmt, t]);

  const reviewUsageLines = useMemo<ReviewLine[]>(() => {
    const lines: ReviewLine[] = [];
    if (isVehicle && catalog) {
      for (const c of catalog.usage_based_costs) {
        if (!selectedKeys.has(c.technical_key)) continue;
        const amount = catalogOverrides[c.technical_key]?.amount ?? c.amounts_per_unit[currencyCode];
        lines.push({
          id: c.technical_key,
          name: templateLabel(t, c.technical_key, c.label),
          monthly: null,
          sub: `${fmtNumber(amount)}/${c.usage_unit}`,
        });
      }
    }
    for (const c of costs.filter((c) => c.period === "usage")) {
      lines.push({
        id: c.id,
        name: c.name || t("newBucket.unnamed"),
        monthly: null,
        sub: t("newBucket.review_per_unit", { amount: fmt(c.amount, { decimals: 3 }), unit: c.unit || "km" }),
      });
    }
    return lines;
  }, [isVehicle, catalog, selectedKeys, catalogOverrides, currencyCode, costs, fmt, t]);

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
      const req = buildCreateRequest(type, name, meta, selectedKeys, catalogOverrides);
      const created = await api.createAsset(req);
      const id = created.asset.id;
      // Only genuinely custom draft rows are posted here; catalog rows are cloned server-side
      // from `selected_cost_keys` and must NOT be double-posted.
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
      setError(err instanceof ApiError ? err.message : t("newBucket.create_error"));
      setSubmitting(false);
    }
  };

  return (
    <div className="content fade-in">
      <div className="wizard">
        <div className="section-head" style={{ marginBottom: 6 }}>
          <div>
            <h1 className="h1">{t("newBucket.title")}</h1>
            <div className="muted" style={{ fontSize: 14, marginTop: 4 }}>
              {t("newBucket.subtitle")}
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onCancel}>
            {t("newBucket.cancel")}
          </button>
        </div>

        <WizardSteps
          step={step}
          steps={[t("newBucket.step_type"), t("newBucket.step_details"), t("newBucket.step_costs"), t("newBucket.step_review")]}
        />

        {step === 1 && (
          <Step1
            selected={type}
            onSelect={(t) => {
              setType(t);
              setStep(2);
            }}
          />
        )}
        {step === 2 && <Step2 type={type!} name={name} setName={setName} meta={meta} setMeta={setMeta} />}
        {step === 3 && (
          <Step3
            type={type!}
            costs={costs}
            onAdd={addCost}
            onRemove={removeCost}
            onUpdate={updateCost}
            catalog={catalog}
            catalogLoading={catalogLoading}
            catalogError={catalogError}
            onRetryCatalog={loadCatalog}
            selectedKeys={selectedKeys}
            onToggleKey={toggleKey}
            onSetGroup={setGroup}
            catalogOverrides={catalogOverrides}
            onUpdateCatalogOverride={updateCatalogOverride}
          />
        )}
        {step === 4 && (
          <Step4
            type={type!}
            name={name}
            meta={meta}
            timeLines={reviewTimeLines}
            usageLines={reviewUsageLines}
            monthlyEst={monthlyEst}
            yearlyEst={yearlyEst}
            perDay={perDay}
          />
        )}

        {error && (
          <div className="error-banner" style={{ marginTop: 16 }}>
            {error}
          </div>
        )}

        <div className="wizard-footer">
          <button className="btn btn-outline" onClick={() => (step > 1 ? setStep(step - 1) : onCancel())}>
            ← {step > 1 ? t("newBucket.back") : t("newBucket.cancel")}
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {step >= 3 && (
              <div style={{ textAlign: "right" }}>
                <div className="muted" style={{ fontSize: 11.5 }}>
                  {t("newBucket.estimated_allocation")}
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, fontFeatureSettings: '"tnum"' }}>
                  {fmt(monthlyEst, { decimals: 0 })}
                  <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
                    {t("newBucket.per_mo")}
                  </span>
                </div>
              </div>
            )}
            {step === 1 ? null : step < 4 ? (
              <button className="btn btn-primary" disabled={!canNext} onClick={() => canNext && setStep(step + 1)}>
                {t("newBucket.continue")} <Icon name="arrowRight" size={13} />
              </button>
            ) : (
              <button className="btn btn-primary" disabled={submitting} onClick={submit}>
                <Icon name="check" size={14} /> {submitting ? t("newBucket.creating") : t("newBucket.create")}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function buildCreateRequest(
  type: TypeOption,
  name: string,
  meta: Record<string, string>,
  selectedKeys: Set<string>,
  catalogOverrides: Record<string, { amount: number; interval_value?: number; interval_unit?: IntervalUnit }>,
): CreateAssetRequest {
  if (type.kind === "car") {
    const costOverrides: TemplateCostOverride[] = Array.from(selectedKeys)
      .filter((key) => key in catalogOverrides)
      .map((key) => {
        const o = catalogOverrides[key];
        return o.interval_value != null && o.interval_unit != null
          ? { technical_key: key, amount: o.amount, interval_value: o.interval_value, interval_unit: o.interval_unit }
          : { technical_key: key, amount: o.amount };
      });
    return {
      name,
      template: "vehicle",
      vehicle: {
        make: meta.make || null,
        year: meta.year ? Number(meta.year) : null,
        starting_odometer: meta.odometer ? Number(meta.odometer.replace(/[^\d]/g, "")) : 0,
      },
      subtitle: subtitleFromMeta(meta) || null,
      // Catalog rows are cloned server-side from these keys; only the chosen rows are created.
      selected_cost_keys: Array.from(selectedKeys),
      cost_overrides: costOverrides,
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
  const { t } = useTranslation();
  return (
    <div className="card card-pad">
      <div className="card-title" style={{ marginBottom: 4 }}>
        {t("newBucket.step1_title")}
      </div>
      <div className="card-sub" style={{ marginBottom: 18 }}>
        {t("newBucket.step1_sub")}
      </div>
      <div className="type-grid">
        {TYPES.map((opt) => (
          <button key={opt.kind} className="type-card" aria-pressed={selected?.kind === opt.kind} onClick={() => onSelect(opt)}>
            <div className="type-illo" style={{ background: opt.bg }}>
              <Illo kind={opt.kind} />
            </div>
            <div className="type-card-body">
              <div className="type-card-name">{t(opt.nameKey)}</div>
              <div className="type-card-desc">{t(opt.descKey)}</div>
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
  const { t } = useTranslation();
  const fields: MetaField[] =
    type.kind === "car"
      ? [
          { key: "make", label: t("newBucket.field_make"), placeholder: "Honda Civic" },
          { key: "year", label: t("newBucket.field_year"), placeholder: "2019", short: true },
          { key: "odometer", label: t("newBucket.field_odometer"), placeholder: "47213", suffix: "km", short: true },
        ]
      : type.kind === "house"
        ? [
            { key: "address", label: t("newBucket.field_address"), placeholder: "Cedar St. apartment" },
            { key: "built", label: t("newBucket.field_built"), placeholder: "1978", short: true },
            { key: "size", label: t("newBucket.field_size"), placeholder: "85", suffix: "m²", short: true },
          ]
        : [
            { key: "breed", label: t("newBucket.field_breed"), placeholder: "Border Collie" },
            { key: "age", label: t("newBucket.field_age"), placeholder: "4", suffix: t("newBucket.suffix_years"), short: true },
            { key: "weight", label: t("newBucket.field_weight"), placeholder: "18", suffix: "kg", short: true },
          ];

  return (
    <div className="card card-pad">
      <div className="card-title" style={{ marginBottom: 4 }}>
        {t("newBucket.step2_title")}
      </div>
      <div className="card-sub" style={{ marginBottom: 22 }}>
        {t("newBucket.step2_sub")}
      </div>

      <div style={{ display: "grid", gap: 16 }}>
        <div className="field">
          <label className="field-label">{t("newBucket.bucket_name")}</label>
          <input
            className="input"
            data-testid="bucket-name-input"
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

interface Step3Props {
  type: TypeOption;
  costs: DraftCost[];
  onAdd: (c: DraftCost) => void;
  onRemove: (id: string) => void;
  onUpdate: (id: string, patch: Partial<DraftCost>) => void;
  catalog: AssetTemplateCatalog | null;
  catalogLoading: boolean;
  catalogError: string | null;
  onRetryCatalog: () => void;
  selectedKeys: Set<string>;
  onToggleKey: (key: string) => void;
  onSetGroup: (keys: string[], on: boolean) => void;
  catalogOverrides: Record<string, CatalogOverride>;
  onUpdateCatalogOverride: (key: string, patch: Partial<CatalogOverride>) => void;
}

function Step3(props: Step3Props) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const periodLabel = (p: Period) => t(`newBucket.period_noun_${p === "2 years" ? "2years" : p}`);
  const { type, costs, onAdd, onRemove, onUpdate } = props;
  const isVehicle = type.kind === "car";
  const suggestions = isVehicle ? [] : SUGGESTED[type.kind as Exclude<IlloKind, "car">].filter((s) => !costs.some((c) => c.name === s.name));

  return (
    <>
      {isVehicle && <VehicleCatalogPicker {...props} />}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ padding: "20px var(--pad) 14px" }}>
          <div className="card-title">{isVehicle ? t("newBucket.custom_costs") : t("newBucket.costs_heading")}</div>
          <div className="card-sub">
            {isVehicle ? t("newBucket.costs_sub_vehicle") : t("newBucket.costs_sub_other")}
          </div>
        </div>

        {costs.length === 0 ? (
          <div style={{ padding: "14px var(--pad) 18px", borderTop: "1px solid var(--line-soft)" }}>
            <div className="muted" style={{ fontSize: 13 }}>
              {isVehicle ? t("newBucket.no_custom_costs_vehicle") : t("newBucket.no_costs_other")}
            </div>
          </div>
        ) : (
          costs.map((c) => <CostRow key={c.id} cost={c} onUpdate={(p) => onUpdate(c.id, p)} onRemove={() => onRemove(c.id)} />)
        )}

        <div className="add-row" onClick={() => onAdd(draft("", "year", 0))}>
          <Icon name="plus" size={14} /> {t("newBucket.add_custom_cost")}
        </div>
      </div>

      {suggestions.length > 0 && (
        <div className="card card-pad">
          <div className="card-title" style={{ fontSize: 13, marginBottom: 10 }}>
            {t("newBucket.suggested_for", { type: t(type.nameKey).toLowerCase() })}
          </div>
          <div className="suggested-list">
            {suggestions.map((s) => (
              <button key={s.id} className="suggested-chip" onClick={() => onAdd(s)}>
                <Icon name="plus" size={11} stroke={2.4} /> {s.name} ·{" "}
                {s.period === "usage"
                  ? `${fmt(s.amount, { decimals: 0 })}/${s.unit}`
                  : `${fmt(s.amount, { decimals: 0 })}/${periodLabel(s.period)}`}
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function VehicleCatalogPicker({
  catalog,
  catalogLoading,
  catalogError,
  onRetryCatalog,
  selectedKeys,
  onToggleKey,
  onSetGroup,
  catalogOverrides,
  onUpdateCatalogOverride,
}: Step3Props) {
  const { t } = useTranslation();
  const currencyCode = useCurrencyCode();
  if (catalogLoading) {
    return (
      <div className="card card-pad" style={{ marginBottom: 16 }}>
        <div className="muted" style={{ fontSize: 13 }}>
          {t("newBucket.catalog_loading")}
        </div>
      </div>
    );
  }
  if (catalogError) {
    return (
      <div className="card card-pad" style={{ marginBottom: 16 }}>
        <div className="error-banner" style={{ marginBottom: 12 }}>
          {catalogError}
        </div>
        <button className="btn btn-outline btn-sm" onClick={onRetryCatalog}>
          {t("newBucket.retry")}
        </button>
      </div>
    );
  }
  if (!catalog) return null;

  const timeKeys = catalog.time_based_costs.map((c) => c.technical_key);
  const usageKeys = catalog.usage_based_costs.map((c) => c.technical_key);
  const maintKeys = catalog.maintenance_items.map((m) => m.technical_key);

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ padding: "20px var(--pad) 6px" }}>
        <div className="card-title">{t("newBucket.template_costs")}</div>
        <div className="card-sub">
          {t("newBucket.template_costs_sub")}
        </div>
      </div>

      <CatalogGroup title={t("newBucket.group_recurring")} allKeys={timeKeys} selectedKeys={selectedKeys} onSetGroup={onSetGroup}>
        {catalog.time_based_costs.map((c) => {
          const o = catalogOverrides[c.technical_key];
          return (
            <EditableCatalogRow
              key={c.technical_key}
              technicalKey={c.technical_key}
              checked={selectedKeys.has(c.technical_key)}
              onToggle={() => onToggleKey(c.technical_key)}
              label={templateLabel(t, c.technical_key, c.label)}
              amount={o?.amount ?? c.amounts[currencyCode]}
              onAmountChange={(v) => onUpdateCatalogOverride(c.technical_key, { amount: v })}
              intervalValue={o?.interval_value ?? c.interval_value}
              intervalUnit={o?.interval_unit ?? c.interval_unit}
              onIntervalChange={(value, unit) =>
                onUpdateCatalogOverride(c.technical_key, { interval_value: value, interval_unit: unit })
              }
            />
          );
        })}
      </CatalogGroup>

      <CatalogGroup title={t("newBucket.group_usage")} allKeys={usageKeys} selectedKeys={selectedKeys} onSetGroup={onSetGroup}>
        {catalog.usage_based_costs.map((c) => (
          <EditableCatalogRow
            key={c.technical_key}
            technicalKey={c.technical_key}
            checked={selectedKeys.has(c.technical_key)}
            onToggle={() => onToggleKey(c.technical_key)}
            label={`${templateLabel(t, c.technical_key, c.label)} (/${c.usage_unit})`}
            amount={catalogOverrides[c.technical_key]?.amount ?? c.amounts_per_unit[currencyCode]}
            onAmountChange={(v) => onUpdateCatalogOverride(c.technical_key, { amount: v })}
          />
        ))}
      </CatalogGroup>

      <CatalogGroup title={t("newBucket.group_maint")} allKeys={maintKeys} selectedKeys={selectedKeys} onSetGroup={onSetGroup}>
        {catalog.maintenance_items.map((m) => (
          <CatalogRow
            key={m.technical_key}
            checked={selectedKeys.has(m.technical_key)}
            onToggle={() => onToggleKey(m.technical_key)}
            label={templateLabel(t, m.technical_key, m.label)}
            detail={maintenanceDetail(m.interval_km, m.interval_months, t)}
          />
        ))}
      </CatalogGroup>
    </div>
  );
}

function CatalogGroup({
  title,
  allKeys,
  selectedKeys,
  onSetGroup,
  children,
}: {
  title: string;
  allKeys: string[];
  selectedKeys: Set<string>;
  onSetGroup: (keys: string[], on: boolean) => void;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const selectedCount = allKeys.filter((k) => selectedKeys.has(k)).length;

  return (
    <div style={{ borderTop: "1px solid var(--line)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px var(--pad) 6px" }}>
        <div className="eyebrow">
          {title} · {selectedCount}/{allKeys.length}
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => onSetGroup(allKeys, true)}>
            {t("newBucket.group_all")}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => onSetGroup(allKeys, false)}>
            {t("newBucket.group_none")}
          </button>
        </div>
      </div>
      <div style={{ padding: "0 var(--pad) 8px" }}>{children}</div>
    </div>
  );
}

function CatalogRow({ checked, onToggle, label, detail }: { checked: boolean; onToggle: () => void; label: string; detail: string }) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", cursor: "pointer" }}>
      <input type="checkbox" checked={checked} onChange={onToggle} />
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13.5 }}>{label}</div>
        <div className="row-meta" style={{ marginTop: 2 }}>
          {detail}
        </div>
      </div>
    </label>
  );
}

// Editable counterpart of `CatalogRow`, used for time-based/usage-based template rows: the
// checkbox stays, but amount (and, for time-based rows, the interval) become inputs pre-filled
// from the template default. `intervalValue`/`intervalUnit`/`onIntervalChange` are omitted for
// usage-based rows, which have no time interval to edit.
function EditableCatalogRow({
  technicalKey,
  checked,
  onToggle,
  label,
  amount,
  onAmountChange,
  intervalValue,
  intervalUnit,
  onIntervalChange,
}: {
  technicalKey: string;
  checked: boolean;
  onToggle: () => void;
  label: string;
  amount: number;
  onAmountChange: (v: number) => void;
  intervalValue?: number;
  intervalUnit?: IntervalUnit;
  onIntervalChange?: (value: number, unit: IntervalUnit) => void;
}) {
  const { t } = useTranslation();
  const hasInterval = intervalValue != null && intervalUnit != null && onIntervalChange;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: hasInterval ? "auto 1fr 110px 70px 100px" : "auto 1fr 110px",
        gap: 10,
        alignItems: "center",
        padding: "8px 0",
      }}
    >
      <input type="checkbox" checked={checked} onChange={onToggle} />
      <div style={{ fontSize: 13.5, minWidth: 0 }}>{label}</div>
      <input
        className="input mono"
        type="number"
        style={{ width: "100%", boxSizing: "border-box" }}
        value={amount}
        onChange={(e) => onAmountChange(Number(e.target.value))}
        disabled={!checked}
        data-testid={`catalog-amount-${technicalKey}`}
      />
      {hasInterval && (
        <>
          <input
            className="input mono"
            type="number"
            style={{ width: "100%", boxSizing: "border-box" }}
            value={intervalValue}
            onChange={(e) => onIntervalChange(Number(e.target.value), intervalUnit)}
            disabled={!checked}
            data-testid={`catalog-interval-value-${technicalKey}`}
          />
          <select
            className="input"
            style={{ width: "100%", boxSizing: "border-box" }}
            value={intervalUnit}
            onChange={(e) => onIntervalChange(intervalValue, e.target.value as IntervalUnit)}
            disabled={!checked}
            data-testid={`catalog-interval-unit-${technicalKey}`}
          >
            <option value="months">{t("newBucket.interval_unit_months")}</option>
            <option value="years">{t("newBucket.interval_unit_years")}</option>
          </select>
        </>
      )}
    </div>
  );
}

function CostRow({ cost, onUpdate, onRemove }: { cost: DraftCost; onUpdate: (p: Partial<DraftCost>) => void; onRemove: () => void }) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  return (
    <div className="cost-row">
      <input className="input" placeholder={t("newBucket.cost_name_ph")} value={cost.name} onChange={(e) => onUpdate({ name: e.target.value })} />
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
        <option value="month">{t("newBucket.period_month")}</option>
        <option value="year">{t("newBucket.period_year")}</option>
        <option value="2 years">{t("newBucket.period_2years")}</option>
        <option value="usage">{t("newBucket.period_usage")}</option>
      </select>
      {cost.period === "usage" ? (
        <select className="input" value={cost.unit || "km"} onChange={(e) => onUpdate({ unit: e.target.value })}>
          <option value="km">{t("newBucket.unit_km")}</option>
          <option value="hour">{t("newBucket.unit_hour")}</option>
          <option value="use">{t("newBucket.unit_use")}</option>
        </select>
      ) : (
        <div className="row-meta" style={{ textAlign: "right" }}>
          {t("newBucket.per_day_approx", { amount: fmt(cost.amount / PERIOD_DAYS[cost.period], { decimals: 2 }) })}
        </div>
      )}
      <button className="cost-row-x" aria-label={t("newBucket.remove")} onClick={onRemove}>
        ×
      </button>
    </div>
  );
}

function Step4({
  type,
  name,
  meta,
  timeLines,
  usageLines,
  monthlyEst,
  yearlyEst,
  perDay,
}: {
  type: TypeOption;
  name: string;
  meta: Record<string, string>;
  timeLines: ReviewLine[];
  usageLines: ReviewLine[];
  monthlyEst: number;
  yearlyEst: number;
  perDay: number;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  return (
    <div className="stack">
      <div className="allocation-callout">
        <div>
          <div className="label">{t("newBucket.estimated_monthly")}</div>
          <div className="num">{fmt(monthlyEst, { decimals: 0 })}</div>
          <div className="sub">
            {t("newBucket.est_sub", { perDay: fmt(perDay, { decimals: 2 }), yearly: fmt(yearlyEst, { decimals: 0 }) })}
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
          <div className="card-title">{t("newBucket.review_suffix", { name: name || t("newBucket.untitled") })}</div>
          <div className="card-sub">{subtitleFromMeta(meta) || t("newBucket.no_details")}</div>
        </div>

        {timeLines.length === 0 && usageLines.length === 0 && (
          <div style={{ padding: "0 var(--pad) 18px" }}>
            <div className="muted" style={{ fontSize: 13 }}>
              {t("newBucket.no_cost_rows")}
            </div>
          </div>
        )}

        {timeLines.map((c) => (
          <div key={c.id} className="review-row">
            <div>
              <div>{c.name}</div>
              <div className="row-meta" style={{ marginTop: 2 }}>
                {c.sub}
              </div>
            </div>
            <div className="review-row-amt">
              {fmt(c.monthly ?? 0, { decimals: 0 })}
              <span className="muted" style={{ fontSize: 11.5, fontWeight: 400 }}>
                {t("newBucket.per_mo")}
              </span>
            </div>
          </div>
        ))}

        {usageLines.length > 0 && (
          <>
            <div style={{ padding: "14px var(--pad) 6px", borderTop: "1px solid var(--line)" }}>
              <div className="eyebrow">{t("newBucket.usage_based_header")}</div>
            </div>
            {usageLines.map((c) => (
              <div key={c.id} className="review-row">
                <div>
                  <div>{c.name}</div>
                  <div className="row-meta" style={{ marginTop: 2 }}>
                    {c.sub}
                  </div>
                </div>
                <div className="review-row-amt muted" style={{ fontWeight: 400, fontSize: 12.5 }}>
                  {t("newBucket.variable")}
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
            <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 4 }}>{t("newBucket.what_happens_next")}</div>
            <div className="muted" style={{ fontSize: 12.5, lineHeight: 1.55 }}>
              {t("newBucket.accruing_prefix")}{" "}
              <strong style={{ color: "var(--ink)" }}>{fmt(perDay, { decimals: 2 })}/day</strong> {t("newBucket.accruing_suffix")}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
