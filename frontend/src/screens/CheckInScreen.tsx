import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api/client";
import type {
  CheckInPreview,
  EditCheckInPreview,
  ExpenseDraft,
  ExpenseLine,
  ExpenseSourceType,
  MaintenanceItem,
  TimeBasedCost,
  TireType,
} from "../api/types";
import { Icon } from "../components/Icon";
import { ErrorState, LoadingState } from "../components/StateView";
import { useCurrency } from "../utils/currency";
import { daysBetween, fmtDate, fmtNumber, todayIso } from "../utils/format";
import { maintenancePill } from "../utils/maintenanceStatus";
import { useAsync } from "../utils/useAsync";

// Either preview shape renders through the same review step and confirm button below; only the
// extra edit-only validity fields (is_valid/first_invalid_*) are edit-mode-specific.
type AnyPreview = CheckInPreview | EditCheckInPreview;

const TIRE_TYPES: TireType[] = ["summer", "winter", "all_season"];
const PREVIEW_DEBOUNCE_MS = 300;
// Guided-wizard steps. The live preview effect runs independent of the visible step, so by the time
// the user reaches "review" the preview reflects everything entered on the earlier steps.
const STEP_KEYS = ["period", "expenses", "review"] as const;

interface DraftExpense {
  key: number;
  kind: "other" | "modeled";
  amount: string;
  pocketOverride: string;
  comment: string;
  sourceType: ExpenseSourceType | null;
  sourceId: string;
  excludedFromAverage: boolean;
}

function isDraftExpenseInvalid(draft: DraftExpense): boolean {
  const amount = Number(draft.amount);
  if (draft.amount === "" || !Number.isFinite(amount) || amount <= 0) return true;
  if (draft.kind === "modeled" && (draft.sourceType === null || draft.sourceId === "")) return true;
  if (draft.pocketOverride !== "") {
    const override = Number(draft.pocketOverride);
    if (!Number.isFinite(override) || override < 0 || override > amount) return true;
  }
  return false;
}

// True when at least one row's paid-out-of-pocket amount was floored by the bucket shortfall
// rather than reflecting the user's own choice — i.e. the row's pocketOverride was left blank
// (backend derived the whole amount from the shortfall) or the backend raised a typed override
// above what was entered because the bucket couldn't cover the rest.
function pocketOverrideWasClamped(drafts: DraftExpense[], preview: AnyPreview): boolean {
  return drafts.some((draft, index) => {
    const line = preview.expense_lines[index];
    if (!line) return false;
    if (draft.pocketOverride === "") return line.paid_out_of_pocket > 0;
    return line.paid_out_of_pocket > Number(draft.pocketOverride);
  });
}

function toExpenseDrafts(drafts: DraftExpense[]): ExpenseDraft[] {
  return drafts
    .filter((d) => d.amount !== "")
    .map((d) => ({
      kind: d.kind,
      amount: Number(d.amount),
      paid_out_of_pocket_override: d.pocketOverride === "" ? null : Number(d.pocketOverride),
      comment: d.kind === "other" ? d.comment || null : null,
      source_type: d.kind === "modeled" ? d.sourceType : null,
      source_id: d.kind === "modeled" ? d.sourceId || null : null,
      excluded_from_average: d.excludedFromAverage,
    }));
}

// Seeds edit mode's draft rows from a stored check-in's posted expense lines. The stored split is
// treated as the caller's override: re-saving the draft unchanged reproduces the same numbers, since
// `paid_out_of_pocket` is passed through as-is instead of being re-derived from scratch.
function draftsFromExpenseLines(lines: ExpenseLine[]): DraftExpense[] {
  return lines.map((line, index) => ({
    key: index,
    kind: line.kind,
    amount: String(line.amount),
    pocketOverride: String(line.paid_out_of_pocket),
    comment: line.comment ?? "",
    sourceType: line.source_type as ExpenseSourceType | null,
    sourceId: line.source_type && line.source_id ? line.source_id : "",
    excludedFromAverage: line.excluded_from_average,
  }));
}

interface CheckInScreenProps {
  assetId: string;
  editCheckInId?: string;
  onSaved: () => void;
  onEditSaved: () => void;
}

export function CheckInScreen({ assetId, editCheckInId, onSaved, onEditSaved }: CheckInScreenProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const isEdit = editCheckInId !== undefined;
  const detail = useAsync(() => api.getAsset(assetId), [assetId]);
  const timeBasedCosts = useAsync(() => api.listTimeBasedCosts(assetId), [assetId]);
  const editTarget = useAsync(
    () => (editCheckInId ? api.getCheckIn(assetId, editCheckInId) : Promise.resolve(null)),
    [assetId, editCheckInId],
  );

  const [usageEnd, setUsageEnd] = useState<string>("");
  const [periodEnd, setPeriodEnd] = useState<string>(todayIso());
  const [activeTireType, setActiveTireType] = useState<TireType | null>(null);
  const [draftExpenses, setDraftExpenses] = useState<DraftExpense[]>([]);
  const nextExpenseKey = useRef(0);
  const previewRequestId = useRef(0);
  const initialNewPreviewSucceeded = useRef(false);
  const [formInitialized, setFormInitialized] = useState(false);
  const [preview, setPreview] = useState<AnyPreview | null>(null);
  const [previewIsCurrent, setPreviewIsCurrent] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [postingError, setPostingError] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);
  const [posted, setPosted] = useState(false);
  const [showOutOfPocketDialog, setShowOutOfPocketDialog] = useState(false);
  // Which wizard step is visible: 0 = period, 1 = expenses, 2 = review. The live preview effect
  // below runs independent of the step, so the review step always reads an up-to-date preview.
  const [stepIdx, setStepIdx] = useState(0);

  const usageTracked = detail.data?.tracks_usage ?? false;
  const hasInvalidExpense = draftExpenses.some(isDraftExpenseInvalid);
  const usageValue = Number(usageEnd);
  const hasValidUsage = !usageTracked || (usageEnd.trim() !== "" && Number.isFinite(usageValue));
  const formIsPreviewable =
    formInitialized && periodEnd.trim() !== "" && hasValidUsage && !hasInvalidExpense;

  const runPreview = useCallback(
    async (
      usageValue: number | null,
      endDate: string,
      tireType: TireType | null,
      expenses: ExpenseDraft[],
      seedTireType: boolean,
    ) => {
      const requestId = ++previewRequestId.current;
      setLoadingPreview(true);
      setPreviewError(null);
      try {
        const result = await api.previewCheckIn(assetId, {
          period_end: endDate,
          usage_end: usageValue,
          active_tire_type: tireType,
          expenses,
        });
        if (requestId !== previewRequestId.current) return;
        setPreview(result);
        if (seedTireType) {
          initialNewPreviewSucceeded.current = true;
          setActiveTireType((result.active_tire_type as TireType | null) ?? null);
        }
        setPreviewIsCurrent(true);
      } catch (err) {
        if (requestId !== previewRequestId.current) return;
        setPreview(null);
        setPreviewIsCurrent(false);
        setPreviewError(err instanceof ApiError ? err.message : t("checkin.preview_failed"));
      } finally {
        if (requestId === previewRequestId.current) setLoadingPreview(false);
      }
    },
    [assetId],
  );

  const runEditPreview = useCallback(
    async (expenses: ExpenseDraft[]) => {
      if (!editCheckInId) return;
      const requestId = ++previewRequestId.current;
      setLoadingPreview(true);
      setPreviewError(null);
      try {
        const result = await api.previewEditCheckIn(assetId, editCheckInId, { expenses });
        if (requestId !== previewRequestId.current) return;
        setPreview(result);
        setPreviewIsCurrent(true);
      } catch (err) {
        if (requestId !== previewRequestId.current) return;
        setPreview(null);
        setPreviewIsCurrent(false);
        setPreviewError(err instanceof ApiError ? err.message : t("checkin.preview_failed"));
      } finally {
        if (requestId === previewRequestId.current) setLoadingPreview(false);
      }
    },
    [assetId, editCheckInId],
  );

  // New-check-in mode seeds the form once asset data arrives. The automatic-preview effect below
  // sends the first request after this state settles; its server-resolved tire type seeds the
  // picker without scheduling a duplicate request.
  useEffect(() => {
    if (isEdit) return;
    if (!detail.data) return;
    const seed = detail.data.tracks_usage ? (detail.data.current_usage ?? 0) : null;
    previewRequestId.current += 1;
    initialNewPreviewSucceeded.current = false;
    nextExpenseKey.current = 0;
    setUsageEnd(seed === null ? "" : String(seed));
    setPeriodEnd(todayIso());
    setActiveTireType(null);
    setDraftExpenses([]);
    setPreview(null);
    setPreviewIsCurrent(false);
    setPreviewError(null);
    setLoadingPreview(false);
    setPostingError(null);
    setPosted(false);
    setShowOutOfPocketDialog(false);
    setStepIdx(0);
    setFormInitialized(true);
  }, [isEdit, detail.data]);

  // Edit mode likewise seeds the immutable fields and stored expenses first, then lets the single
  // automatic-preview effect issue the initial edit preview.
  useEffect(() => {
    if (!isEdit) return;
    if (!editTarget.data) return;
    const target = editTarget.data;
    previewRequestId.current += 1;
    nextExpenseKey.current = 0;
    setPeriodEnd(target.period_end);
    setUsageEnd(target.usage_end != null ? String(target.usage_end) : "");
    setActiveTireType((target.active_tire_type as TireType | null) ?? null);
    const seeded = draftsFromExpenseLines(target.expense_lines).map((d) => ({
      ...d,
      key: nextExpenseKey.current++,
    }));
    setDraftExpenses(seeded);
    setPreview(null);
    setPreviewIsCurrent(false);
    setPreviewError(null);
    setLoadingPreview(false);
    setPostingError(null);
    setPosted(false);
    setShowOutOfPocketDialog(false);
    setStepIdx(0);
    setFormInitialized(true);
  }, [isEdit, editTarget.data]);

  useEffect(() => {
    if (!formInitialized || previewIsCurrent || previewError || loadingPreview) return;

    previewRequestId.current += 1;
    if (!formIsPreviewable) {
      setPreview(null);
      return;
    }

    const timer = window.setTimeout(() => {
      const expenses = toExpenseDrafts(draftExpenses);
      if (isEdit) {
        void runEditPreview(expenses);
      } else {
        void runPreview(
          usageTracked ? usageValue : null,
          periodEnd,
          activeTireType,
          expenses,
          !initialNewPreviewSucceeded.current,
        );
      }
    }, PREVIEW_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [
    activeTireType,
    draftExpenses,
    formInitialized,
    formIsPreviewable,
    isEdit,
    loadingPreview,
    periodEnd,
    previewError,
    previewIsCurrent,
    runEditPreview,
    runPreview,
    usageEnd,
    usageTracked,
    usageValue,
  ]);

  if (isEdit) {
    if (editTarget.loading) return <LoadingState label={t("checkin.loading_edit_target")} />;
    if (editTarget.error || !editTarget.data) {
      return <ErrorState message={editTarget.error ?? t("checkin.edit_not_found")} onRetry={editTarget.reload} />;
    }
  }
  if (detail.loading || timeBasedCosts.loading) return <LoadingState label={t("checkin.loading")} />;
  if (detail.error || !detail.data) {
    return <ErrorState message={detail.error ?? t("checkin.not_found")} onRetry={detail.reload} />;
  }
  if (timeBasedCosts.error || !timeBasedCosts.data) {
    return <ErrorState message={timeBasedCosts.error ?? t("checkin.not_found")} onRetry={timeBasedCosts.reload} />;
  }

  const e = detail.data;
  const rawDaysSince = e.last_check_in_date ? daysBetween(e.last_check_in_date, periodEnd) : null;
  // Only meaningful when the period end is after the last check-in.
  const daysSince = rawDaysSince !== null && rawDaysSince > 0 ? rawDaysSince : null;
  const flags = e.maintenance_items.filter((m) => m.status && m.status !== "ok");
  const hasTireItems = e.maintenance_items.some((m) => m.tire_type);
  const activeMaintenanceItems = e.maintenance_items.filter((m) => m.is_active);
  const activeTimeBasedCosts = timeBasedCosts.data.filter((c) => c.is_active);

  const invalidatePreview = () => {
    previewRequestId.current += 1;
    setLoadingPreview(false);
    setPreviewIsCurrent(false);
    setPreviewError(null);
    setPostingError(null);
    setPosted(false);
    setShowOutOfPocketDialog(false);
  };

  const addExpense = () => {
    invalidatePreview();
    setDraftExpenses((rows) => [
      ...rows,
      {
        key: nextExpenseKey.current++,
        kind: "other",
        amount: "",
        pocketOverride: "",
        comment: "",
        sourceType: null,
        sourceId: "",
        excludedFromAverage: false,
      },
    ]);
  };

  const updateExpense = (key: number, changes: Partial<DraftExpense>) => {
    invalidatePreview();
    setDraftExpenses((rows) => rows.map((row) => (row.key === key ? { ...row, ...changes } : row)));
  };

  const removeExpense = (key: number) => {
    invalidatePreview();
    setDraftExpenses((rows) => rows.filter((row) => row.key !== key));
  };

  const retryPreview = () => {
    if (!formIsPreviewable) return;
    const expenses = toExpenseDrafts(draftExpenses);
    setPreviewIsCurrent(false);
    if (isEdit) {
      void runEditPreview(expenses);
    } else {
      void runPreview(
        usageTracked ? usageValue : null,
        periodEnd,
        activeTireType,
        expenses,
        !initialNewPreviewSucceeded.current,
      );
    }
  };

  const post = async () => {
    if (!preview || !previewIsCurrent) return;
    setPosting(true);
    setPostingError(null);
    try {
      if (isEdit && editCheckInId) {
        await api.editCheckIn(assetId, editCheckInId, {
          expenses: toExpenseDrafts(draftExpenses),
        });
      } else {
        await api.postCheckIn(assetId, {
          period_end: periodEnd,
          usage_end: usageTracked ? Number(usageEnd) : null,
          active_tire_type: activeTireType,
          expenses: toExpenseDrafts(draftExpenses),
        });
      }
      setPosted(true);
      setShowOutOfPocketDialog(false);
      onSaved();
      if (isEdit) onEditSaved();
    } catch (err) {
      setPostingError(err instanceof ApiError ? err.message : t("checkin.posting_failed"));
    } finally {
      setPosting(false);
    }
  };

  const editValidity: EditCheckInPreview | null = preview && "is_valid" in preview ? preview : null;
  const editIsInvalid = editValidity !== null && editValidity.is_valid === false;
  const calculatingPreview = formIsPreviewable && !previewIsCurrent && previewError === null;

  // Wizard navigation. A step can only advance once its own inputs are valid; the confirm button on
  // the review step keeps the existing full disabled/guard logic.
  const step = STEP_KEYS[stepIdx];
  const progressPct = ((stepIdx + 1) / STEP_KEYS.length) * 100;
  const canContinueFromPeriod = periodEnd.trim() !== "" && hasValidUsage;
  const canContinue = step === "period" ? canContinueFromPeriod : step === "expenses" ? !hasInvalidExpense : true;
  const goNext = () => {
    if (canContinue) setStepIdx((i) => Math.min(STEP_KEYS.length - 1, i + 1));
  };
  const goBack = () => setStepIdx((i) => Math.max(0, i - 1));
  const confirmDisabled =
    !preview ||
    !previewIsCurrent ||
    calculatingPreview ||
    loadingPreview ||
    previewError !== null ||
    posting ||
    posted ||
    !formIsPreviewable ||
    editIsInvalid;
  const onConfirmClick = () => {
    if (preview && previewIsCurrent && pocketOverrideWasClamped(draftExpenses, preview)) {
      setShowOutOfPocketDialog(true);
    } else {
      void post();
    }
  };

  // Posted confirmation. Edit mode navigates away via onEditSaved, so this only shows for a new
  // check-in; "Done" reloads the asset so a follow-up check-in starts from the fresh balance.
  if (posted && !isEdit && preview) {
    return (
      <PostedState
        name={e.name}
        netChange={preview.net_bucket_change}
        balanceAfter={preview.balance_after}
        onDone={() => detail.reload()}
      />
    );
  }

  const periodColumns =
    [usageTracked, hasTireItems].filter(Boolean).length === 2
      ? "1fr 1fr 1fr"
      : usageTracked || hasTireItems
        ? "1fr 1fr"
        : "1fr";

  return (
    <div className="content fade-in">
      <div className="section-head">
        <div>
          <div className="eyebrow">
            {e.last_check_in_date
              ? t("checkin.eyebrow_last", { date: fmtDate(e.last_check_in_date) })
              : t("checkin.eyebrow_first")}
          </div>
          <h1 className="h1" style={{ marginTop: 4 }}>
            {daysSince !== null
              ? t("checkin.heading_days", { days: daysSince })
              : e.last_check_in_date
                ? t("checkin.heading_period")
                : t("checkin.heading_first")}
          </h1>
        </div>
        <span className="month-pill" style={{ height: 32 }}>
          <Icon name="calendar" size={12} /> {e.name}
        </span>
      </div>

      <div className="wizard">
        <div className="wizard-progress">
          <div className="wizard-progress-fill" style={{ width: `${progressPct}%` }} />
        </div>

        <div key={step} className="fade-in">
          {/* Step 1 — period, usage, tire type, maintenance flags */}
          {step === "period" && (
            <div className="card">
              <div className="card-hd">
                <div>
                  <span className="card-title">{t("checkin.step1_title")}</span>
                </div>
                <span className="pill pill-accent">{t("checkin.required")}</span>
              </div>
              <div style={{ padding: "16px var(--pad) 20px" }}>
                {isEdit && (
                  <div className="error-banner" style={{ marginBottom: 14, background: "var(--warn-bg, #fff7e6)" }}>
                    {t("checkin.editing_past_period", { date: fmtDate(periodEnd) })}
                  </div>
                )}
                <div style={{ display: "grid", gridTemplateColumns: periodColumns, gap: 16 }}>
                  <div className="field">
                    <label className="field-label" htmlFor="checkin-period-end">
                      {t("checkin.period_end")}
                    </label>
                    {isEdit ? (
                      <div className="input" id="checkin-period-end">
                        {fmtDate(periodEnd)}
                      </div>
                    ) : (
                      <input
                        id="checkin-period-end"
                        className="input"
                        type="date"
                        max={todayIso()}
                        value={periodEnd}
                        onChange={(ev) => {
                          invalidatePreview();
                          setPeriodEnd(ev.target.value);
                        }}
                      />
                    )}
                  </div>
                  {usageTracked && (
                    <div className="field">
                      <label className="field-label" htmlFor="checkin-usage-end">
                        {t("checkin.current_usage")}
                      </label>
                      {isEdit ? (
                        <div className="input mono" id="checkin-usage-end">
                          {fmtNumber(Number(usageEnd || 0))} km
                        </div>
                      ) : (
                        <div className="input-prefix-wrap">
                          <input
                            id="checkin-usage-end"
                            className="input mono"
                            type="number"
                            value={usageEnd}
                            onChange={(ev) => {
                              invalidatePreview();
                              setUsageEnd(ev.target.value);
                            }}
                          />
                          <span className="input-suffix">km</span>
                        </div>
                      )}
                    </div>
                  )}
                  {hasTireItems && (
                    <div className="field">
                      <label className="field-label" htmlFor="checkin-tire-type">
                        {t("checkin.tire_type_label")}
                      </label>
                      {isEdit ? (
                        <div className="input" id="checkin-tire-type">
                          {activeTireType ? t(`checkin.tire_${activeTireType}`) : t("checkin.tire_type_placeholder")}
                        </div>
                      ) : (
                        <select
                          id="checkin-tire-type"
                          className="input"
                          value={activeTireType ?? ""}
                          onChange={(ev) => {
                            invalidatePreview();
                            setActiveTireType((ev.target.value || null) as TireType | null);
                          }}
                        >
                          <option value="">{t("checkin.tire_type_placeholder")}</option>
                          {TIRE_TYPES.map((tire) => (
                            <option key={tire} value={tire}>
                              {t(`checkin.tire_${tire}`)}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  )}
                </div>
                {!isEdit && (
                  <div className="row-meta" style={{ marginTop: 8 }}>
                    {t("checkin.period_end_hint")}
                  </div>
                )}
                {usageTracked && e.current_usage !== null && (
                  <div className="row-meta" style={{ marginTop: 14 }}>
                    {t("checkin.last_recorded", { usage: fmtNumber(e.current_usage) })}
                  </div>
                )}
                {flags.length > 0 && (
                  <>
                    <hr className="hr" style={{ margin: "16px 0" }} />
                    <div style={{ fontSize: 13.5, fontWeight: 500, marginBottom: 10 }}>
                      {t("checkin.step3_title")}{" "}
                      <span className="pill pill-warn" style={{ marginLeft: 6 }}>
                        {t("checkin.attention", { n: flags.length })}
                      </span>
                    </div>
                    {flags.map((m, i) => (
                      <FlagRow key={m.id} item={m} last={i === flags.length - 1} />
                    ))}
                  </>
                )}
              </div>
            </div>
          )}

          {/* Step 2 — expenses this period */}
          {step === "expenses" && (
            <div className="card">
              <div className="card-hd">
                <div>
                  <span className="card-title">{t("checkin.expenses_step_title")}</span>
                </div>
              </div>
              <div style={{ padding: "16px var(--pad) 20px" }}>
                <div className="stack" style={{ gap: 10 }}>
                  {draftExpenses.map((row, index) => (
                    <ExpenseRow
                      key={row.key}
                      row={row}
                      index={index}
                      preview={preview}
                      maintenanceItems={activeMaintenanceItems}
                      timeBasedCosts={activeTimeBasedCosts}
                      onChange={(changes) => updateExpense(row.key, changes)}
                      onRemove={() => removeExpense(row.key)}
                    />
                  ))}
                </div>
                {draftExpenses.length === 0 && (
                  <div className="row-meta" style={{ marginBottom: 4 }}>{t("checkin.expenses_empty")}</div>
                )}
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ marginTop: draftExpenses.length > 0 ? 10 : 4 }}
                  onClick={addExpense}
                >
                  <Icon name="plus" size={12} /> {t("checkin.add_expense")}
                </button>
                {hasInvalidExpense && (
                  <div className="row-meta" style={{ color: "var(--bad)", marginTop: 8 }}>
                    {t("checkin.expense_invalid")}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Step 3 — review & confirm */}
          {step === "review" &&
            (previewError ? (
              <div className="card">
                <div className="checkin-preview-error" style={{ padding: "16px var(--pad)" }}>
                  <div className="error-banner">{previewError}</div>
                  <button className="btn btn-outline btn-sm" onClick={retryPreview}>
                    {t("checkin.retry_preview")}
                  </button>
                </div>
              </div>
            ) : !preview ? (
              <div className="card">
                <div style={{ padding: "16px var(--pad)" }} className="row-meta">
                  {calculatingPreview ? t("checkin.calculating") : t("checkin.review_hint")}
                </div>
              </div>
            ) : (
              <>
                <div className="allocation-callout" style={{ marginBottom: 16 }}>
                  <div>
                    <div className="label">{t("checkin.net_change")}</div>
                    <div className="num">{fmt(preview.net_bucket_change, { decimals: 2, sign: true })}</div>
                    <div className="sub">
                      {t("checkin.from_to", {
                        from: fmt(preview.balance_before, { decimals: 2 }),
                        to: fmt(preview.balance_after, { decimals: 2 }),
                      })}
                    </div>
                  </div>
                </div>
                <div className="card">
                  {preview.elapsed_days === 0 && !e.last_check_in_date && (
                    <div className="row-meta" style={{ padding: "16px var(--pad) 0" }}>
                      {t("checkin.baseline_note")}
                    </div>
                  )}
                  <div className="checkin-line">
                    <div>
                      <div>{t("checkin.allocations")}</div>
                      <div className="checkin-line-detail">
                        {t("checkin.allocations_detail", {
                          days: preview.elapsed_days,
                          count: preview.allocation_lines.length,
                        })}
                      </div>
                    </div>
                    <span></span>
                    <span className="checkin-line-amt" style={{ color: "var(--good)" }}>
                      {fmt(preview.total_allocation, { decimals: 2, sign: true })}
                    </span>
                  </div>
                  <div className="checkin-line">
                    <div>
                      <div>{t("checkin.expenses")}</div>
                      <div className="checkin-line-detail">
                        {t("checkin.expenses_detail", { count: preview.expense_lines.length })}
                      </div>
                    </div>
                    <span></span>
                    <span className="checkin-line-amt" style={{ color: "var(--bad)" }}>
                      {fmt(-preview.total_expense, { decimals: 2 })}
                    </span>
                  </div>
                  <div className="checkin-line">
                    <div>{t("checkin.covered_by_bucket")}</div>
                    <span></span>
                    <span className="checkin-line-amt">{fmt(-preview.total_bucket_expense, { decimals: 2 })}</span>
                  </div>
                  <div className="checkin-line">
                    <div>{t("checkin.paid_out_of_pocket")}</div>
                    <span></span>
                    <span className="checkin-line-amt">{fmt(preview.paid_out_of_pocket, { decimals: 2 })}</span>
                  </div>
                </div>
                {editIsInvalid && editValidity?.first_invalid_period_end && (
                  <div className="error-banner" style={{ marginTop: 12 }}>
                    {t("checkin.edit_would_break_balance", { date: fmtDate(editValidity.first_invalid_period_end) })}
                  </div>
                )}
                {postingError && (
                  <div className="error-banner" style={{ marginTop: 12 }}>
                    {postingError}
                  </div>
                )}
                <div className="muted" style={{ fontSize: 12, lineHeight: 1.5, marginTop: 14 }}>
                  {t("checkin.confirm_desc", { name: e.name })}
                </div>
              </>
            ))}
        </div>

        <div className="wizard-footer">
          <button className="btn btn-outline" onClick={goBack} disabled={stepIdx === 0}>
            ← {t("checkin.back")}
          </button>
          {step !== "review" ? (
            <button className="btn btn-primary" disabled={!canContinue} onClick={goNext}>
              {t("checkin.continue")} <Icon name="arrowRight" size={13} />
            </button>
          ) : (
            <button className="btn btn-primary" disabled={confirmDisabled} onClick={onConfirmClick}>
              {posting ? (
                t("checkin.posting")
              ) : (
                <>
                  {t("checkin.confirm_post")} <Icon name="arrowRight" size={13} />
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {showOutOfPocketDialog && preview && previewIsCurrent && (
        <div className="modal-backdrop">
          <div
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="paid-out-of-pocket-title"
            aria-describedby="paid-out-of-pocket-description"
          >
            <h2 id="paid-out-of-pocket-title" className="h2">
              {t("checkin.out_of_pocket_dialog_title")}
            </h2>
            <p id="paid-out-of-pocket-description" className="muted" style={{ lineHeight: 1.6, marginTop: 12 }}>
              {t("checkin.out_of_pocket_dialog_body", {
                amount: fmt(preview.paid_out_of_pocket, { decimals: 2 }),
              })}
            </p>
            <div className="modal-actions">
              <button className="btn btn-outline" disabled={posting} onClick={() => setShowOutOfPocketDialog(false)}>
                {t("checkin.out_of_pocket_back")}
              </button>
              <button className="btn btn-primary" disabled={posting} autoFocus onClick={() => void post()}>
                {posting ? t("checkin.posting") : t("checkin.out_of_pocket_confirm")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function PostedState({
  name,
  netChange,
  balanceAfter,
  onDone,
}: {
  name: string;
  netChange: number;
  balanceAfter: number;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  return (
    <div className="content fade-in" style={{ display: "flex", justifyContent: "center" }}>
      <div className="card card-pad ci-posted" style={{ maxWidth: 440, width: "100%", textAlign: "center" }}>
        <div className="ci-posted-check">
          <Icon name="check" size={26} />
        </div>
        <div className="h2" style={{ marginTop: 16 }}>
          {t("checkin.posted_title")}
        </div>
        <div className="muted" style={{ fontSize: 13.5, marginTop: 6 }}>
          {t("checkin.posted_sub", { name })}
        </div>
        <div className="num-xl" style={{ marginTop: 18, color: netChange >= 0 ? "var(--good)" : "var(--bad)" }}>
          {fmt(netChange, { decimals: 2, sign: true })}
        </div>
        <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>
          {t("checkin.posted_new_balance", { amount: fmt(balanceAfter, { decimals: 2 }) })}
        </div>
        <button className="btn btn-primary" style={{ marginTop: 22 }} onClick={onDone}>
          {t("checkin.posted_done")}
        </button>
      </div>
    </div>
  );
}

function ExpenseRow({
  row,
  index,
  preview,
  maintenanceItems,
  timeBasedCosts,
  onChange,
  onRemove,
}: {
  row: DraftExpense;
  index: number;
  preview: AnyPreview | null;
  maintenanceItems: MaintenanceItem[];
  timeBasedCosts: TimeBasedCost[];
  onChange: (changes: Partial<DraftExpense>) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const kindId = `checkin-expense-kind-${row.key}`;
  const commentId = `checkin-expense-comment-${row.key}`;
  const amountId = `checkin-expense-amount-${row.key}`;
  const pocketId = `checkin-expense-pocket-${row.key}`;
  const isOther = row.kind === "other";
  const selectedValue = isOther ? "other" : row.sourceType && row.sourceId ? `${row.sourceType}:${row.sourceId}` : "";
  const previewLine = preview?.expense_lines[index] ?? null;
  const adjustedAmount =
    row.pocketOverride !== "" && previewLine && previewLine.paid_out_of_pocket > Number(row.pocketOverride)
      ? previewLine.paid_out_of_pocket
      : null;

  const handleKindChange = (value: string) => {
    if (value === "other") {
      onChange({ kind: "other", sourceType: null, sourceId: "" });
    } else {
      const [sourceType, sourceId] = value.split(":", 2) as [ExpenseSourceType, string];
      onChange({ kind: "modeled", sourceType, sourceId, comment: "" });
    }
  };

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div style={{ display: "grid", gridTemplateColumns: isOther ? "1fr 1fr 1fr auto" : "1fr 1fr auto", gap: 10, alignItems: "end" }}>
        <div className="field">
          <label className="field-label" htmlFor={kindId}>
            {t("checkin.expense_kind_label")}
          </label>
          <select id={kindId} className="input" value={selectedValue} onChange={(ev) => handleKindChange(ev.target.value)}>
            <option value="other">{t("checkin.expense_kind_other")}</option>
            {maintenanceItems.length > 0 && (
              <optgroup label={t("checkin.expense_kind_maintenance")}>
                {maintenanceItems.map((item) => (
                  <option key={item.id} value={`maintenance_item:${item.id}`}>
                    {item.label}
                  </option>
                ))}
              </optgroup>
            )}
            {timeBasedCosts.length > 0 && (
              <optgroup label={t("checkin.expense_kind_time_based")}>
                {timeBasedCosts.map((cost) => (
                  <option key={cost.id} value={`time_based_cost:${cost.id}`}>
                    {cost.label}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </div>
        {isOther && (
          <div className="field">
            <label className="field-label" htmlFor={commentId}>
              {t("checkin.expense_comment")}
            </label>
            <input
              id={commentId}
              className="input"
              type="text"
              maxLength={2000}
              value={row.comment}
              onChange={(ev) => onChange({ comment: ev.target.value })}
            />
          </div>
        )}
        <div className="field">
          <label className="field-label" htmlFor={amountId}>
            {t("checkin.expense_amount")}
          </label>
          <input
            id={amountId}
            className="input mono"
            type="number"
            value={row.amount}
            onChange={(ev) => onChange({ amount: ev.target.value })}
          />
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onRemove}>
          {t("checkin.remove_expense")}
        </button>
      </div>
      <div className="field">
        <label className="field-label" htmlFor={pocketId}>
          {t("checkin.expense_pocket_label")}
        </label>
        <input
          id={pocketId}
          className="input mono"
          type="number"
          min={0}
          placeholder={t("checkin.expense_pocket_placeholder")}
          value={row.pocketOverride}
          onChange={(ev) => onChange({ pocketOverride: ev.target.value })}
        />
        {adjustedAmount !== null && (
          <div className="row-meta">{t("checkin.expense_pocket_adjusted", { amount: fmt(adjustedAmount, { decimals: 2 }) })}</div>
        )}
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
        <input
          type="checkbox"
          checked={row.excludedFromAverage}
          onChange={(ev) => onChange({ excludedFromAverage: ev.target.checked })}
        />
        <span className="row-meta">{t("checkin.expense_excluded_from_average_label")}</span>
      </label>
    </div>
  );
}

function FlagRow({ item, last }: { item: MaintenanceItem; last: boolean }) {
  const { t } = useTranslation();
  const pill = maintenancePill(item.status);
  const iconColor = item.status === "overdue" ? "var(--bad)" : "var(--warn)";
  const detail =
    item.status === "overdue"
      ? t("checkin.flag_overdue")
      : item.remaining_km !== null
        ? t("checkin.flag_km", { km: fmtNumber(item.remaining_km) })
        : item.remaining_months !== null
          ? t("checkin.flag_months", { months: item.remaining_months })
          : t("checkin.flag_approaching");
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "24px 1fr auto",
        gap: 12,
        padding: "10px 0",
        borderBottom: last ? "none" : "1px solid var(--line-soft)",
        alignItems: "start",
      }}
    >
      <div style={{ color: iconColor, marginTop: 1 }}>
        <Icon name="alert" size={16} />
      </div>
      <div>
        <div style={{ fontSize: 13.5, fontWeight: 500 }}>{item.label}</div>
        <div className="muted" style={{ fontSize: 12.5, marginTop: 2, lineHeight: 1.5 }}>
          {detail}
        </div>
      </div>
      <span className={`pill ${pill.cls}`}>{pill.label}</span>
    </div>
  );
}
