import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api/client";
import type { CheckInPreview, MaintenanceItem } from "../api/types";
import { Icon } from "../components/Icon";
import { ErrorState, LoadingState } from "../components/StateView";
import { tracksUsage } from "../utils/assetType";
import { useCurrency } from "../utils/currency";
import { daysBetween, fmtDate, fmtNumber, todayIso } from "../utils/format";
import { maintenancePill } from "../utils/health";
import { useAsync } from "../utils/useAsync";

interface CheckInScreenProps {
  assetId: string;
  onPosted: () => void;
}

export function CheckInScreen({ assetId, onPosted }: CheckInScreenProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const detail = useAsync(() => api.getAsset(assetId), [assetId]);

  const [usageEnd, setUsageEnd] = useState<string>("");
  const [periodEnd, setPeriodEnd] = useState<string>(todayIso());
  const [preview, setPreview] = useState<CheckInPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [posting, setPosting] = useState(false);
  const [posted, setPosted] = useState(false);

  const usageTracked = detail.data ? tracksUsage(detail.data.type, detail.data.current_usage) : false;

  const runPreview = useCallback(
    async (usageValue: number, endDate: string) => {
      setLoadingPreview(true);
      setPreviewError(null);
      try {
        const result = await api.previewCheckIn(assetId, { period_end: endDate, usage_end: usageValue });
        setPreview(result);
      } catch (err) {
        setPreview(null);
        setPreviewError(err instanceof ApiError ? err.message : t("checkin.preview_failed"));
      } finally {
        setLoadingPreview(false);
      }
    },
    [assetId],
  );

  // Seed the usage field from the asset's current usage, then run the first preview.
  useEffect(() => {
    if (!detail.data) return;
    const seed = detail.data.current_usage ?? 0;
    setUsageEnd(String(seed));
    void runPreview(seed, todayIso());
  }, [detail.data, runPreview]);

  if (detail.loading) return <LoadingState label={t("checkin.loading")} />;
  if (detail.error || !detail.data) {
    return <ErrorState message={detail.error ?? t("checkin.not_found")} onRetry={detail.reload} />;
  }

  const e = detail.data;
  const rawDaysSince = e.last_check_in_date ? daysBetween(e.last_check_in_date, periodEnd) : null;
  // Only meaningful when the period end is after the last check-in.
  const daysSince = rawDaysSince !== null && rawDaysSince > 0 ? rawDaysSince : null;
  const flags = e.maintenance_items.filter((m) => m.status && m.status !== "ok");

  const post = async () => {
    setPosting(true);
    setPreviewError(null);
    try {
      await api.postCheckIn(assetId, { period_end: periodEnd, usage_end: Number(usageEnd) });
      setPosted(true);
      onPosted();
    } catch (err) {
      setPreviewError(err instanceof ApiError ? err.message : t("checkin.posting_failed"));
    } finally {
      setPosting(false);
    }
  };

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

      <div className="col-3-2">
        {/* Left — steps */}
        <div className="stack">
          {/* Step 1: period + usage */}
          <div className="card">
            <div className="card-hd">
              <div>
                <span className="card-title">{t("checkin.step1")}</span>{" "}
                <span style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)" }}>{t("checkin.step1_title")}</span>
              </div>
              <span className="pill pill-accent">{t("checkin.required")}</span>
            </div>
            <div style={{ padding: "16px var(--pad) 20px" }}>
              <div style={{ display: "grid", gridTemplateColumns: usageTracked ? "1fr 1fr" : "1fr", gap: 16 }}>
                <div className="field">
                  <label className="field-label">{t("checkin.period_end")}</label>
                  <input
                    className="input"
                    type="date"
                    value={periodEnd}
                    onChange={(ev) => setPeriodEnd(ev.target.value)}
                  />
                </div>
                {usageTracked && (
                  <div className="field">
                    <label className="field-label">{t("checkin.current_usage")}</label>
                    <div className="input-prefix-wrap">
                      <input
                        className="input mono"
                        type="number"
                        value={usageEnd}
                        onChange={(ev) => setUsageEnd(ev.target.value)}
                      />
                      <span className="input-suffix">km</span>
                    </div>
                  </div>
                )}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14 }}>
                <button
                  className="btn btn-outline btn-sm"
                  disabled={loadingPreview}
                  onClick={() => runPreview(Number(usageEnd || 0), periodEnd)}
                >
                  {loadingPreview ? t("checkin.calculating") : t("checkin.update_preview")}
                </button>
                {usageTracked && e.current_usage !== null && (
                  <span className="row-meta">{t("checkin.last_recorded", { usage: fmtNumber(e.current_usage) })}</span>
                )}
              </div>
            </div>
          </div>

          {/* Step 2: review */}
          <div className="card">
            <div className="card-hd">
              <div>
                <span className="card-title">{t("checkin.step2")}</span>{" "}
                <span style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)" }}>{t("checkin.step2_title")}</span>
              </div>
            </div>
            {previewError ? (
              <div style={{ padding: "16px var(--pad)" }}>
                <div className="error-banner">{previewError}</div>
              </div>
            ) : !preview ? (
              <div style={{ padding: "16px var(--pad)" }} className="row-meta">
                {t("checkin.review_hint")}
              </div>
            ) : (
              <div style={{ marginTop: 8 }}>
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
                <div className="totals-row">
                  <div>
                    <div className="label">{t("checkin.net_change")}</div>
                    <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>
                      {t("checkin.from_to", {
                        from: fmt(preview.balance_before, { decimals: 2 }),
                        to: fmt(preview.balance_after, { decimals: 2 }),
                      })}
                    </div>
                  </div>
                  <div className="num-lg" style={{ color: preview.net_bucket_change >= 0 ? "var(--good)" : "var(--bad)" }}>
                    {fmt(preview.net_bucket_change, { decimals: 2, sign: true })}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Step 3: maintenance flags */}
          <div className="card">
            <div className="card-hd">
              <div>
                <span className="card-title">{t("checkin.step3")}</span>{" "}
                <span style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)" }}>{t("checkin.step3_title")}</span>
              </div>
              {flags.length > 0 && <span className="pill pill-warn">{t("checkin.attention", { n: flags.length })}</span>}
            </div>
            <div style={{ padding: "14px var(--pad) 18px" }}>
              {flags.length === 0 ? (
                <div className="row-meta">{t("checkin.nothing_flagged")}</div>
              ) : (
                flags.map((m, i) => <FlagRow key={m.id} item={m} last={i === flags.length - 1} />)
              )}
            </div>
          </div>
        </div>

        {/* Right — confirm panel */}
        <div className="card" style={{ position: "sticky", top: 120, alignSelf: "start" }}>
          <div className="card-pad">
            <div className="eyebrow">{t("checkin.confirm_allocation")}</div>
            <div
              className="num-xl"
              style={{ marginTop: 12, color: preview && preview.net_bucket_change < 0 ? "var(--bad)" : "var(--good)" }}
            >
              {preview ? fmt(preview.net_bucket_change, { decimals: 2, sign: true }) : "—"}
            </div>
            <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>
              {t("checkin.net_change_desc")}
            </div>
            <hr className="hr" />
            <div className="stack" style={{ gap: 8 }}>
              <RowKV k={t("checkin.allocations")} v={preview ? fmt(preview.total_allocation, { decimals: 2, sign: true }) : "—"} />
              <RowKV k={t("checkin.expenses")} v={preview ? fmt(-preview.total_expense, { decimals: 2 }) : "—"} />
              <RowKV k={t("checkin.bucket_before")} v={preview ? fmt(preview.balance_before, { decimals: 2 }) : "—"} />
              <RowKV k={t("checkin.bucket_after")} v={preview ? fmt(preview.balance_after, { decimals: 2 }) : "—"} bold />
            </div>
            <hr className="hr" />
            <div className="muted" style={{ fontSize: 12, lineHeight: 1.5 }}>
              {t("checkin.confirm_desc", { name: e.name })}
            </div>
            <button
              className="btn btn-primary"
              style={{ width: "100%", marginTop: 14, height: 38, justifyContent: "center" }}
              disabled={!preview || posting || posted}
              onClick={post}
            >
              {posted ? (
                <>
                  <Icon name="check" size={14} /> {t("checkin.posted")}
                </>
              ) : posting ? (
                t("checkin.posting")
              ) : (
                <>
                  {t("checkin.confirm_post")} <Icon name="arrowRight" size={13} />
                </>
              )}
            </button>
          </div>
        </div>
      </div>
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

function RowKV({ k, v, bold }: { k: string; v: string; bold?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
      <span className="muted" style={{ fontSize: 12.5 }}>
        {k}
      </span>
      <span className="num" style={{ fontSize: bold ? 15 : 13, fontWeight: bold ? 500 : 400 }}>
        {v}
      </span>
    </div>
  );
}
