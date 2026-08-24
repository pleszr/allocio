import { useEffect, useMemo, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api/client";
import type {
  AllocationEstimate,
  AllocationEstimateRequest,
  AssetTemplateCatalog,
  CreateAssetRequest,
  IntervalUnit,
  TemplateCostOverride,
} from "../api/types";
import { Icon } from "../components/Icon";
import { Illo } from "../components/Illustrations";
import type { IlloKind } from "../utils/assetType";
import { useCurrency, useCurrencyCode, useCurrencySymbol } from "../utils/currency";
import { fmtNumber, todayIso } from "../utils/format";

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
  templateKey?: TemplateKey;
}

type TemplateKey = "vehicle" | "house" | "pet";

// One review line for the review step / the running estimate. `monthly` is null for usage-based
// (variable) rows, which are excluded from the steady monthly figure.
interface ReviewLine {
  id: string;
  name: string;
  monthly: number | null;
  sub: string;
}

// A single ad-hoc "what for / amount" row collected on the optional first-check-in step.
interface CheckinExpenseDraft {
  id: string;
  name: string;
  amount: number;
}

const TYPES: TypeOption[] = [
  {
    kind: "car",
    nameKey: "newBucket.type_vehicle_name",
    descKey: "newBucket.type_vehicle_desc",
    bg: "#DDE8F8",
    assetType: "vehicle",
    templateKey: "vehicle",
  },
  {
    kind: "house",
    nameKey: "newBucket.type_house_name",
    descKey: "newBucket.type_house_desc",
    bg: "#F8E5E2",
    assetType: "house",
    templateKey: "house",
  },
  {
    kind: "pet",
    nameKey: "newBucket.type_pet_name",
    descKey: "newBucket.type_pet_desc",
    bg: "#F8EBD8",
    assetType: "pet",
    templateKey: "pet",
  },
];

// The wizard's guided one-question-per-step flow. `path`/`history` (not a plain number) so Back
// can retrace the actual branch taken — "ask-checkin" forks to either "first-checkin" or straight
// to "review" depending on the user's Yes/No answer.
type WizardStep = "type" | "details" | "costs" | "safety" | "ask-checkin" | "first-checkin" | "review";

// Monotonic progress-bar weights along the longest possible path. Back/Continue always moves the
// bar in the expected direction regardless of which branch ("ask-checkin" → "first-checkin" or
// straight to "review") was actually taken.
const STEP_WEIGHT: Record<WizardStep, number> = {
  type: 1,
  details: 2,
  costs: 3,
  safety: 4,
  "ask-checkin": 5,
  "first-checkin": 6,
  review: 7,
};
const TOTAL_WEIGHT = 7;

// Order used only to test "have we reached the costs step yet" (the estimate fetch/footer total
// gate) — not for computing progress-bar position, which uses STEP_WEIGHT above.
const STEP_ORDER: WizardStep[] = ["type", "details", "costs", "safety", "ask-checkin", "first-checkin", "review"];

// The step a step's own footer "Continue" button advances to. "type" auto-advances on card click
// and "ask-checkin" navigates on the Yes/No click itself — neither has a footer Continue button.
const NEXT_STEP: Partial<Record<WizardStep, WizardStep>> = {
  details: "costs",
  costs: "safety",
  safety: "ask-checkin",
  "first-checkin": "review",
};

type SafetyPresetId = "none" | "light" | "recommended" | "extra";
interface SafetyPreset {
  id: SafetyPresetId;
  amount: number;
}

function draft(name: string, period: Period, amount: number, unit?: string): DraftCost {
  return { id: Math.random().toString(36).slice(2, 8), name, period, amount, unit };
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

// A built-in template row's label, translated by its stable `technical_key`; falls back to the
// backend-supplied English label if a translation key is missing (e.g. a future untranslated row).
function templateLabel(t: TFunction, templateKey: TemplateKey, technicalKey: string, fallback: string): string {
  return t(`templates.${templateKey}.${technicalKey}.label`, { defaultValue: fallback });
}

function catalogSupportsCurrency(catalog: AssetTemplateCatalog, currency: string): boolean {
  if (!(currency in catalog.manual_extra_monthly_amounts)) return false;
  if (catalog.time_based_costs.some((row) => !(currency in row.amounts))) return false;
  if (catalog.usage_based_costs.some((row) => !(currency in row.amounts_per_unit))) return false;
  return !catalog.maintenance_items.some(
    (row) => row.estimated_costs != null && !(currency in row.estimated_costs),
  );
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
  const [step, setStep] = useState<WizardStep>("type");
  const [history, setHistory] = useState<WizardStep[]>(["type"]);
  const [type, setType] = useState<TypeOption | null>(null);
  const [name, setName] = useState("");
  const [manufactureYear, setManufactureYear] = useState("");
  const [odometer, setOdometer] = useState("");
  const [costs, setCosts] = useState<DraftCost[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Safety-buffer preset and optional first-check-in expenses (new steps).
  const [safetyId, setSafetyId] = useState<SafetyPresetId>("recommended");
  const [logFirstCheckin, setLogFirstCheckin] = useState<boolean | null>(null);
  const [checkinExpenses, setCheckinExpenses] = useState<CheckinExpenseDraft[]>([]);

  // Template catalog + the user's row selection. Owned here so it survives Back/Continue.
  const isVehicle = type?.kind === "car";
  const templateKey = type?.templateKey ?? null;
  const [catalog, setCatalog] = useState<AssetTemplateCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  // The user-edited amount/interval for each time-based/usage-based catalog row, seeded from the
  // template default in the owner's currency once, then owned by the user. Maintenance items don't
  // participate here — they have no curated amount to edit.
  const [catalogOverrides, setCatalogOverrides] = useState<Record<string, CatalogOverride>>({});
  const [estimate, setEstimate] = useState<AllocationEstimate | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [estimateRetry, setEstimateRetry] = useState(0);
  const estimateRequestId = useRef(0);
  const catalogRequestId = useRef(0);
  const activeTemplateKey = useRef<TemplateKey | null>(templateKey);
  activeTemplateKey.current = templateKey;

  const goTo = (next: WizardStep) => {
    setHistory((h) => [...h, next]);
    setStep(next);
  };
  const back = () => {
    if (history.length <= 1) {
      onCancel();
      return;
    }
    const nextHistory = history.slice(0, -1);
    setHistory(nextHistory);
    setStep(nextHistory[nextHistory.length - 1]);
  };

  const loadCatalog = (requestedTemplate: TemplateKey | null = activeTemplateKey.current) => {
    if (!requestedTemplate) return;
    const requestId = ++catalogRequestId.current;
    setCatalogLoading(true);
    setCatalogError(null);
    api
      .getTemplateCatalog(requestedTemplate)
      .then((c) => {
        if (requestId !== catalogRequestId.current || activeTemplateKey.current !== requestedTemplate) return;
        if (!catalogSupportsCurrency(c, currencyCode)) {
          setCatalog(null);
          setCatalogError(t("newBucket.catalog_error"));
          return;
        }
        setCatalog(c);
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
      .catch(() => {
        if (requestId === catalogRequestId.current && activeTemplateKey.current === requestedTemplate) {
          setCatalogError(t("newBucket.catalog_error"));
        }
      })
      .finally(() => {
        if (requestId === catalogRequestId.current && activeTemplateKey.current === requestedTemplate) {
          setCatalogLoading(false);
        }
      });
  };

  const updateCatalogOverride = (key: string, patch: Partial<CatalogOverride>) =>
    setCatalogOverrides((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));

  // A template switch invalidates in-flight catalog/estimate requests and resets only template state.
  useEffect(() => {
    estimateRequestId.current += 1;
    setCatalog(null);
    setCatalogLoading(false);
    setCatalogError(null);
    setSelectedKeys(new Set());
    setCatalogOverrides({});
    setEstimate(null);
    setEstimateLoading(false);
    setEstimateError(null);
    if (templateKey) loadCatalog(templateKey);
    else catalogRequestId.current += 1;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateKey]);

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

  const estimateRequest = useMemo<AllocationEstimateRequest>(
    () => buildEstimateRequest(templateKey, selectedKeys, catalogOverrides, costs),
    [templateKey, selectedKeys, catalogOverrides, costs],
  );

  // The wizard keeps the last successful estimate while a settled edit is refreshed. Starts as
  // soon as the "costs" step is reached (rather than only once the review step renders) because
  // the "safety" step needs `baseMonthly` before the user gets there.
  useEffect(() => {
    if (STEP_ORDER.indexOf(step) < STEP_ORDER.indexOf("costs") || (templateKey && !catalog)) {
      estimateRequestId.current += 1;
      setEstimateLoading(false);
      return;
    }
    const requestId = ++estimateRequestId.current;
    const timer = window.setTimeout(() => {
      setEstimateLoading(true);
      setEstimateError(null);
      api
        .estimateAllocation(estimateRequest)
        .then((result) => {
          if (requestId === estimateRequestId.current) setEstimate(result);
        })
        .catch((err: unknown) => {
          if (requestId === estimateRequestId.current) {
            setEstimateError(err instanceof ApiError ? err.message : t("newBucket.estimate_error"));
          }
        })
        .finally(() => {
          if (requestId === estimateRequestId.current) setEstimateLoading(false);
        });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [step, templateKey, catalog, estimateRequest, estimateRetry, t]);

  // Combine backend-derived time rows with presentation-only labels and recurrence descriptions.
  const reviewTimeLines = useMemo<ReviewLine[]>(() => {
    if (!estimate) return [];
    return estimate.lines.map((line) => {
      const catalogRow = catalog?.time_based_costs.find((row) => row.technical_key === line.key);
      const customRow = costs.find((row) => row.id === line.key);
      const override = catalogRow ? catalogOverrides[catalogRow.technical_key] : undefined;
      const intervalValue = override?.interval_value ?? catalogRow?.interval_value;
      const intervalUnit = override?.interval_unit ?? catalogRow?.interval_unit;
      return {
        id: line.key,
        name: catalogRow
          ? templateLabel(t, templateKey!, catalogRow.technical_key, catalogRow.label)
          : customRow?.name || line.label || t("newBucket.unnamed"),
        monthly: line.monthly_amount,
        sub:
          catalogRow && intervalValue != null && intervalUnit != null
            ? `${fmtNumber(line.reference_amount)}${intervalLabel(intervalValue, intervalUnit)}`
            : customRow
              ? t("newBucket.review_per_period", {
                  amount: fmt(line.reference_amount),
                  period: periodLabel(customRow.period),
                })
              : "",
      };
    });
  }, [estimate, catalog, catalogOverrides, costs, fmt, t, templateKey]);

  const reviewUsageLines = useMemo<ReviewLine[]>(() => {
    const lines: ReviewLine[] = [];
    if (templateKey && catalog) {
      for (const c of catalog.usage_based_costs) {
        if (!selectedKeys.has(c.technical_key)) continue;
        const amount = catalogOverrides[c.technical_key]?.amount ?? c.amounts_per_unit[currencyCode];
        lines.push({
          id: c.technical_key,
          name: templateLabel(t, templateKey, c.technical_key, c.label),
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
  }, [templateKey, catalog, selectedKeys, catalogOverrides, currencyCode, costs, fmt, t]);

  const addCost = (c: DraftCost) => setCosts((arr) => [...arr, { ...c, id: Math.random().toString(36).slice(2, 8) }]);
  const removeCost = (id: string) => setCosts((arr) => arr.filter((c) => c.id !== id));
  const updateCost = (id: string, patch: Partial<DraftCost>) =>
    setCosts((arr) => arr.map((c) => (c.id === id ? { ...c, ...patch } : c)));

  const addCheckinExpense = () =>
    setCheckinExpenses((arr) => [...arr, { id: Math.random().toString(36).slice(2, 8), name: "", amount: 0 }]);
  const removeCheckinExpense = (id: string) => setCheckinExpenses((arr) => arr.filter((e) => e.id !== id));
  const updateCheckinExpense = (id: string, patch: Partial<CheckinExpenseDraft>) =>
    setCheckinExpenses((arr) => arr.map((e) => (e.id === id ? { ...e, ...patch } : e)));

  // Safety-buffer presets, derived from the running estimate (0 while it's still loading).
  const baseMonthly = estimate?.monthly_total ?? 0;
  const presets = useMemo<SafetyPreset[]>(() => {
    const recommended = Math.max(10, Math.round(baseMonthly * 0.15));
    return [
      { id: "none", amount: 0 },
      { id: "light", amount: Math.round(recommended * 0.4) },
      { id: "recommended", amount: recommended },
      { id: "extra", amount: Math.round(recommended * 2) },
    ];
  }, [baseMonthly]);
  const chosenPreset = presets.find((p) => p.id === safetyId) ?? presets[2];
  // Computed once and reused everywhere a running total is shown (footer + review callout) rather
  // than repeating `estimate.monthly_total + chosenPreset.amount` inline in multiple spots.
  const displayedMonthlyTotal = baseMonthly + chosenPreset.amount;

  const manufactureYearValid = !isVehicle || isValidManufactureYear(manufactureYear);
  const templateReady = templateKey == null || (!!catalog && !catalogLoading && !catalogError);
  const canNext =
    step === "details"
      ? !!name.trim() && manufactureYearValid
      : step === "costs"
        ? templateReady
        : true;
  const showRunningTotal = STEP_ORDER.indexOf(step) >= STEP_ORDER.indexOf("costs");

  const submit = async () => {
    if (!type) return;
    setSubmitting(true);
    setError(null);
    let assetCreated = false;
    try {
      const req = buildCreateRequest(type, name, manufactureYear, odometer, selectedKeys, catalogOverrides);
      const created = await api.createAsset(req);
      assetCreated = true;
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
      if (safetyId !== "none") {
        await api.updateManualExtra(id, chosenPreset.amount);
      }
      if (logFirstCheckin === true && checkinExpenses.length > 0) {
        await api.postCheckIn(id, {
          period_end: todayIso(),
          usage_end: type.kind === "car" ? Number(odometer.replace(/[^\d]/g, "")) || 0 : null,
          expenses: checkinExpenses.map((e) => ({ kind: "other", amount: e.amount, comment: e.name || null })),
        });
      }
      onCreated(id);
    } catch (err) {
      // A failure after the asset already exists is a partial-success state — the asset was
      // created but the safety buffer and/or first check-in didn't get applied. Surface that
      // distinctly rather than implying nothing was created; no automatic rollback (no
      // delete-asset endpoint exists) — the user finishes the rest from CostsScreen/CheckInScreen.
      if (assetCreated) {
        setError(t("newBucket.create_partial_error"));
      } else {
        setError(err instanceof ApiError ? err.message : t("newBucket.create_error"));
      }
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

        <WizardProgress step={step} />

        {step === "type" && (
          <StepType
            selected={type}
            onSelect={(picked) => {
              setType(picked);
              goTo("details");
            }}
          />
        )}
        {step === "details" && (
          <StepDetails
            type={type!}
            name={name}
            setName={setName}
            manufactureYear={manufactureYear}
            setManufactureYear={setManufactureYear}
            odometer={odometer}
            setOdometer={setOdometer}
          />
        )}
        {step === "costs" && (
          <StepCosts
            type={type!}
            costs={costs}
            onAdd={addCost}
            onRemove={removeCost}
            onUpdate={updateCost}
            catalog={catalog}
            catalogLoading={catalogLoading}
            catalogError={catalogError}
            onRetryCatalog={() => loadCatalog()}
            selectedKeys={selectedKeys}
            onToggleKey={toggleKey}
            onSetGroup={setGroup}
            catalogOverrides={catalogOverrides}
            onUpdateCatalogOverride={updateCatalogOverride}
          />
        )}
        {step === "safety" && <StepSafety presets={presets} safetyId={safetyId} onSelect={setSafetyId} />}
        {step === "ask-checkin" && (
          <StepAskCheckin
            value={logFirstCheckin}
            onYes={() => {
              setLogFirstCheckin(true);
              goTo("first-checkin");
            }}
            onNo={() => {
              setLogFirstCheckin(false);
              goTo("review");
            }}
          />
        )}
        {step === "first-checkin" && (
          <StepFirstCheckin
            expenses={checkinExpenses}
            onAdd={addCheckinExpense}
            onRemove={removeCheckinExpense}
            onUpdate={updateCheckinExpense}
          />
        )}
        {step === "review" && (
          <StepReview
            type={type!}
            name={name}
            timeLines={reviewTimeLines}
            usageLines={reviewUsageLines}
            estimate={estimate}
            estimateLoading={estimateLoading}
            estimateError={estimateError}
            onRetryEstimate={() => setEstimateRetry((value) => value + 1)}
            displayedMonthlyTotal={displayedMonthlyTotal}
            safetyId={safetyId}
            safetyAmount={chosenPreset.amount}
            logFirstCheckin={logFirstCheckin}
            checkinExpensesCount={checkinExpenses.length}
          />
        )}

        {error && (
          <div className="error-banner" style={{ marginTop: 16 }}>
            {error}
          </div>
        )}

        <div className="wizard-footer">
          <button className="btn btn-outline" onClick={back}>
            ← {history.length > 1 ? t("newBucket.back") : t("newBucket.cancel")}
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {showRunningTotal && (
              <div style={{ textAlign: "right" }}>
                <div className="muted" style={{ fontSize: 11.5 }}>
                  {t("newBucket.estimated_allocation")}
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, fontFeatureSettings: '"tnum"' }}>
                  {estimate ? fmt(displayedMonthlyTotal) : "—"}
                  <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
                    {t("newBucket.per_mo")}
                  </span>
                </div>
                {estimateLoading && estimate && (
                  <div className="muted" style={{ fontSize: 11 }}>
                    {t("newBucket.estimate_updating")}
                  </div>
                )}
              </div>
            )}
            {step === "type" || step === "ask-checkin" ? null : step !== "review" ? (
              <button className="btn btn-primary" disabled={!canNext} onClick={() => canNext && goTo(NEXT_STEP[step]!)}>
                {t("newBucket.continue")} <Icon name="arrowRight" size={13} />
              </button>
            ) : (
              <button className="btn btn-primary" disabled={submitting || !templateReady} onClick={submit}>
                <Icon name="check" size={14} /> {submitting ? t("newBucket.creating") : t("newBucket.create")}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function buildEstimateRequest(
  templateKey: TemplateKey | null,
  selectedKeys: Set<string>,
  catalogOverrides: Record<string, CatalogOverride>,
  costs: DraftCost[],
): AllocationEstimateRequest {
  const costOverrides: TemplateCostOverride[] = templateKey
    ? Array.from(selectedKeys)
        .filter((key) => key in catalogOverrides)
        .map((key) => {
          const override = catalogOverrides[key];
          return override.interval_value != null && override.interval_unit != null
            ? {
                technical_key: key,
                amount: override.amount,
                interval_value: override.interval_value,
                interval_unit: override.interval_unit,
              }
            : { technical_key: key, amount: override.amount };
        })
    : [];
  return {
    template: templateKey,
    selected_cost_keys: templateKey ? Array.from(selectedKeys) : [],
    cost_overrides: costOverrides,
    custom_time_based_costs: costs
      .filter((cost) => cost.period !== "usage")
      .map((cost) => ({
        client_key: cost.id,
        label: cost.name || "Cost",
        amount: cost.amount,
        interval_value: cost.period === "2 years" ? 2 : 1,
        interval_unit: cost.period === "month" ? "months" : "years",
      })),
  };
}

function buildCreateRequest(
  type: TypeOption,
  name: string,
  manufactureYear: string,
  odometer: string,
  selectedKeys: Set<string>,
  catalogOverrides: Record<string, { amount: number; interval_value?: number; interval_unit?: IntervalUnit }>,
): CreateAssetRequest {
  if (type.templateKey) {
    const costOverrides: TemplateCostOverride[] = Array.from(selectedKeys)
      .filter((key) => key in catalogOverrides)
      .map((key) => {
        const o = catalogOverrides[key];
        return o.interval_value != null && o.interval_unit != null
          ? { technical_key: key, amount: o.amount, interval_value: o.interval_value, interval_unit: o.interval_unit }
          : { technical_key: key, amount: o.amount };
      });
    const request: CreateAssetRequest = {
      name,
      template: type.templateKey,
      selected_cost_keys: Array.from(selectedKeys),
      cost_overrides: costOverrides,
    };
    if (type.templateKey === "vehicle") {
      const trimmedManufactureYear = manufactureYear.trim();
      request.vehicle = {
        ...(trimmedManufactureYear && isValidManufactureYear(trimmedManufactureYear)
          ? { manufacture_year: Number(trimmedManufactureYear) }
          : {}),
        starting_odometer: odometer ? Number(odometer.replace(/[^\d]/g, "")) : 0,
      };
    }
    return request;
  }
  return {
    name,
    type: type.assetType,
  };
}

function isValidManufactureYear(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  if (!/^\d+$/.test(trimmed)) return false;
  const year = Number(trimmed);
  return Number.isInteger(year) && year >= 1886 && year <= new Date().getFullYear();
}

// Single horizontal progress bar (replaces the old numbered step-dot rendering, which doesn't
// represent a branching path well). Fill width is the current step's weight over the longest
// possible path, so Back/Continue always moves it monotonically along the path actually taken.
function WizardProgress({ step }: { step: WizardStep }) {
  const pct = (STEP_WEIGHT[step] / TOTAL_WEIGHT) * 100;
  return (
    <div className="wizard-progress">
      <div className="wizard-progress-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

function StepType({ selected, onSelect }: { selected: TypeOption | null; onSelect: (t: TypeOption) => void }) {
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

function StepDetails({
  type,
  name,
  setName,
  manufactureYear,
  setManufactureYear,
  odometer,
  setOdometer,
}: {
  type: TypeOption;
  name: string;
  setName: (v: string) => void;
  manufactureYear: string;
  setManufactureYear: (value: string) => void;
  odometer: string;
  setOdometer: (value: string) => void;
}) {
  const { t } = useTranslation();
  const currentYear = new Date().getFullYear();
  const manufactureYearInvalid = !isValidManufactureYear(manufactureYear);

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
          <label className="field-label" htmlFor="bucket-name">
            {t("newBucket.bucket_name")}
          </label>
          <input
            id="bucket-name"
            className="input"
            data-testid="bucket-name-input"
            placeholder={
              type.kind === "car"
                ? "Honda Civic"
                : type.kind === "pet"
                  ? t("newBucket.type_pet_name_placeholder")
                  : "Cedar St."
            }
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </div>
        {type.kind === "car" && (
          <>
            <div className="field">
              <label className="field-label" htmlFor="bucket-manufacture-year">
                {t("newBucket.field_manufacture_year")}
              </label>
              <input
                id="bucket-manufacture-year"
                className="input"
                type="number"
                inputMode="numeric"
                min={1886}
                max={currentYear}
                value={manufactureYear}
                onChange={(e) => setManufactureYear(e.target.value)}
                aria-invalid={manufactureYearInvalid}
                aria-describedby={manufactureYearInvalid ? "bucket-manufacture-year-error" : undefined}
              />
              {manufactureYearInvalid && (
                <div id="bucket-manufacture-year-error" className="field-error">
                  {t("newBucket.manufacture_year_invalid", { currentYear })}
                </div>
              )}
            </div>
            <div className="field">
              <label className="field-label" htmlFor="bucket-odometer">
                {t("newBucket.field_odometer")}
              </label>
              <div className="input-prefix-wrap">
                <input
                  id="bucket-odometer"
                  className="input"
                  inputMode="numeric"
                  placeholder="47213"
                  value={odometer}
                  onChange={(e) => setOdometer(e.target.value)}
                />
                <span className="input-suffix">km</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

interface StepCostsProps {
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

function StepCosts(props: StepCostsProps) {
  const { t } = useTranslation();
  const { type, costs, onAdd, onRemove, onUpdate } = props;
  const hasTemplate = type.templateKey != null;

  return (
    <>
      {hasTemplate && <TemplateCatalogPicker {...props} />}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ padding: "20px var(--pad) 14px" }}>
          <div className="card-title">{hasTemplate ? t("newBucket.custom_costs") : t("newBucket.costs_heading")}</div>
          <div className="card-sub">
            {hasTemplate ? t("newBucket.costs_sub_vehicle") : t("newBucket.costs_sub_other")}
          </div>
        </div>

        {costs.length === 0 ? (
          <div style={{ padding: "14px var(--pad) 18px", borderTop: "1px solid var(--line-soft)" }}>
            <div className="muted" style={{ fontSize: 13 }}>
              {hasTemplate ? t("newBucket.no_custom_costs_vehicle") : t("newBucket.no_costs_other")}
            </div>
          </div>
        ) : (
          costs.map((c) => <CostRow key={c.id} cost={c} onUpdate={(p) => onUpdate(c.id, p)} onRemove={() => onRemove(c.id)} />)
        )}

        <div className="add-row" onClick={() => onAdd(draft("", "year", 0))}>
          <Icon name="plus" size={14} /> {t("newBucket.add_custom_cost")}
        </div>
      </div>
    </>
  );
}

function TemplateCatalogPicker({
  type,
  catalog,
  catalogLoading,
  catalogError,
  onRetryCatalog,
  selectedKeys,
  onToggleKey,
  onSetGroup,
  catalogOverrides,
  onUpdateCatalogOverride,
}: StepCostsProps) {
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
  const templateKey = type.templateKey!;

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

      {timeKeys.length > 0 && (
        <CatalogGroup title={t("newBucket.group_recurring")} allKeys={timeKeys} selectedKeys={selectedKeys} onSetGroup={onSetGroup}>
          {catalog.time_based_costs.map((c) => {
            const o = catalogOverrides[c.technical_key];
            return (
              <EditableCatalogRow
                key={c.technical_key}
                technicalKey={c.technical_key}
                checked={selectedKeys.has(c.technical_key)}
                onToggle={() => onToggleKey(c.technical_key)}
                label={templateLabel(t, templateKey, c.technical_key, c.label)}
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
      )}

      {usageKeys.length > 0 && (
        <CatalogGroup title={t("newBucket.group_usage")} allKeys={usageKeys} selectedKeys={selectedKeys} onSetGroup={onSetGroup}>
          {catalog.usage_based_costs.map((c) => (
            <EditableCatalogRow
              key={c.technical_key}
              technicalKey={c.technical_key}
              checked={selectedKeys.has(c.technical_key)}
              onToggle={() => onToggleKey(c.technical_key)}
              label={`${templateLabel(t, templateKey, c.technical_key, c.label)} (/${c.usage_unit})`}
              amount={catalogOverrides[c.technical_key]?.amount ?? c.amounts_per_unit[currencyCode]}
              onAmountChange={(v) => onUpdateCatalogOverride(c.technical_key, { amount: v })}
            />
          ))}
        </CatalogGroup>
      )}

      {maintKeys.length > 0 && (
        <CatalogGroup title={t("newBucket.group_maint")} allKeys={maintKeys} selectedKeys={selectedKeys} onSetGroup={onSetGroup}>
          {catalog.maintenance_items.map((m) => (
            <CatalogRow
              key={m.technical_key}
              checked={selectedKeys.has(m.technical_key)}
              onToggle={() => onToggleKey(m.technical_key)}
              label={templateLabel(t, templateKey, m.technical_key, m.label)}
              detail={maintenanceDetail(m.interval_km, m.interval_months, t)}
            />
          ))}
        </CatalogGroup>
      )}
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
  const { symbol, position } = useCurrencySymbol();
  return (
    <div className="cost-row">
      <input className="input" placeholder={t("newBucket.cost_name_ph")} value={cost.name} onChange={(e) => onUpdate({ name: e.target.value })} />
      <div className="input-prefix-wrap">
        {position === "prefix" && <span className="input-prefix">{symbol}</span>}
        <input
          className="input mono"
          type="number"
          value={cost.amount}
          onChange={(e) => onUpdate({ amount: Number(e.target.value) })}
        />
        {position === "suffix" && <span className="input-suffix">{symbol}</span>}
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
        <div />
      )}
      <button className="cost-row-x" aria-label={t("newBucket.remove")} onClick={onRemove}>
        ×
      </button>
    </div>
  );
}

function StepSafety({
  presets,
  safetyId,
  onSelect,
}: {
  presets: SafetyPreset[];
  safetyId: SafetyPresetId;
  onSelect: (id: SafetyPresetId) => void;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const copy: Record<SafetyPresetId, { label: string; desc: string }> = {
    none: { label: t("newBucket.safety_none_label"), desc: t("newBucket.safety_none_desc") },
    light: { label: t("newBucket.safety_light_label"), desc: t("newBucket.safety_light_desc") },
    recommended: { label: t("newBucket.safety_recommended_label"), desc: t("newBucket.safety_recommended_desc") },
    extra: { label: t("newBucket.safety_extra_label"), desc: t("newBucket.safety_extra_desc") },
  };
  return (
    <div className="card card-pad">
      <div className="card-title" style={{ marginBottom: 4 }}>
        {t("newBucket.safety_step_title")}
      </div>
      <div className="card-sub" style={{ marginBottom: 18 }}>
        {t("newBucket.safety_step_sub")}
      </div>
      <div className="safety-grid">
        {presets.map((p) => (
          <button key={p.id} className="safety-card" aria-pressed={safetyId === p.id} onClick={() => onSelect(p.id)}>
            <div className="safety-card-label">{copy[p.id].label}</div>
            <div className="safety-card-desc">{copy[p.id].desc}</div>
            <div className="safety-card-amount">
              +{fmt(p.amount)}
              {t("newBucket.per_mo")}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function StepAskCheckin({ value, onYes, onNo }: { value: boolean | null; onYes: () => void; onNo: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="card card-pad">
      <div className="card-title" style={{ marginBottom: 4 }}>
        {t("newBucket.ask_checkin_title")}
      </div>
      <div className="card-sub" style={{ marginBottom: 18 }}>
        {t("newBucket.ask_checkin_sub")}
      </div>
      <div className="yesno-row">
        <button className="yesno-btn" aria-pressed={value === true} onClick={onYes}>
          {t("newBucket.yes")}
        </button>
        <button className="yesno-btn" aria-pressed={value === false} onClick={onNo}>
          {t("newBucket.no")}
        </button>
      </div>
    </div>
  );
}

function StepFirstCheckin({
  expenses,
  onAdd,
  onRemove,
  onUpdate,
}: {
  expenses: CheckinExpenseDraft[];
  onAdd: () => void;
  onRemove: (id: string) => void;
  onUpdate: (id: string, patch: Partial<CheckinExpenseDraft>) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ padding: "20px var(--pad) 14px" }}>
        <div className="card-title">{t("newBucket.first_checkin_title")}</div>
        <div className="card-sub">{t("newBucket.first_checkin_sub")}</div>
      </div>

      {expenses.length === 0 ? (
        <div style={{ padding: "14px var(--pad) 18px", borderTop: "1px solid var(--line-soft)" }}>
          <div className="muted" style={{ fontSize: 13 }}>
            {t("newBucket.first_checkin_empty")}
          </div>
        </div>
      ) : (
        expenses.map((e) => (
          <div
            key={e.id}
            className="cost-row"
            style={{ gridTemplateColumns: "1fr 130px 32px", alignItems: "end" }}
          >
            <div className="field">
              <label className="field-label" htmlFor={`checkin-expense-name-${e.id}`}>
                {t("newBucket.first_checkin_name_label")}
              </label>
              <input
                id={`checkin-expense-name-${e.id}`}
                className="input"
                placeholder={t("newBucket.first_checkin_name_ph")}
                value={e.name}
                onChange={(ev) => onUpdate(e.id, { name: ev.target.value })}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor={`checkin-expense-amount-${e.id}`}>
                {t("newBucket.first_checkin_amount_label")}
              </label>
              <input
                id={`checkin-expense-amount-${e.id}`}
                className="input mono"
                type="number"
                value={e.amount}
                onChange={(ev) => onUpdate(e.id, { amount: Number(ev.target.value) })}
              />
            </div>
            <button className="cost-row-x" aria-label={t("newBucket.remove")} onClick={() => onRemove(e.id)}>
              ×
            </button>
          </div>
        ))
      )}

      <div className="add-row" onClick={onAdd}>
        <Icon name="plus" size={14} /> {t("newBucket.first_checkin_add")}
      </div>
    </div>
  );
}

function StepReview({
  type,
  name,
  timeLines,
  usageLines,
  estimate,
  estimateLoading,
  estimateError,
  onRetryEstimate,
  displayedMonthlyTotal,
  safetyId,
  safetyAmount,
  logFirstCheckin,
  checkinExpensesCount,
}: {
  type: TypeOption;
  name: string;
  timeLines: ReviewLine[];
  usageLines: ReviewLine[];
  estimate: AllocationEstimate | null;
  estimateLoading: boolean;
  estimateError: string | null;
  onRetryEstimate: () => void;
  displayedMonthlyTotal: number;
  safetyId: SafetyPresetId;
  safetyAmount: number;
  logFirstCheckin: boolean | null;
  checkinExpensesCount: number;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  return (
    <div className="stack">
      <div className="allocation-callout">
        <div>
          <div className="label">{t("newBucket.estimated_monthly")}</div>
          <div className="num">{estimate ? fmt(displayedMonthlyTotal) : "—"}</div>
          {estimate && (
            <div className="sub">
              {t("newBucket.est_sub", {
                perDay: fmt(estimate.daily_total),
                yearly: fmt(estimate.yearly_total),
              })}
            </div>
          )}
          {estimateLoading && (
            <div className="sub">
              {estimate ? t("newBucket.estimate_updating") : t("newBucket.estimate_loading")}
            </div>
          )}
        </div>
        <div style={{ width: 140, height: 100, background: "rgba(255,255,255,.12)", borderRadius: 12, padding: 8 }}>
          <div style={{ background: type.bg, borderRadius: 10, width: "100%", height: "100%", display: "grid", placeItems: "center" }}>
            <Illo kind={type.kind} />
          </div>
        </div>
      </div>

      {estimateError && (
        <div className="error-banner">
          <div>{estimateError}</div>
          <button className="btn btn-outline btn-sm" onClick={onRetryEstimate}>
            {t("newBucket.retry")}
          </button>
        </div>
      )}

      <div className="card">
        <div style={{ padding: "20px var(--pad) 14px" }}>
          <div className="card-title">{t("newBucket.review_suffix", { name: name || t("newBucket.untitled") })}</div>
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
              {fmt(c.monthly ?? 0)}
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

        <div className="review-row">
          <div>{t("newBucket.review_safety_buffer_label")}</div>
          <div className="review-row-amt">
            {safetyId === "none" ? (
              t("newBucket.review_safety_none")
            ) : (
              <>
                +{fmt(safetyAmount)}
                <span className="muted" style={{ fontSize: 11.5, fontWeight: 400 }}>
                  {t("newBucket.per_mo")}
                </span>
              </>
            )}
          </div>
        </div>

        {logFirstCheckin === true && checkinExpensesCount > 0 && (
          <div className="review-row">
            <div>{t("newBucket.review_first_checkin_label")}</div>
            <div className="review-row-amt">
              {t("newBucket.review_first_checkin_count", { count: checkinExpensesCount })}
            </div>
          </div>
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
              <strong style={{ color: "var(--ink)" }}>
                {estimate ? `${fmt(estimate.daily_total)}/day` : "—"}
              </strong>{" "}
              {t("newBucket.accruing_suffix")}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
