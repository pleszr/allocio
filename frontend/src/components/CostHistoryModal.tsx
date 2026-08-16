import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { ExpenseEvent, TimeBasedCost } from "../api/types";
import { Icon } from "../components/Icon";
import { ErrorState, LoadingState } from "../components/StateView";
import { Sparkline } from "../components/Sparkline";
import { useCurrency } from "../utils/currency";
import { fmtDate, fmtDateShort } from "../utils/format";
import { useAsync } from "../utils/useAsync";

// Which cost table opened the popup — picks the matching per-cost expense endpoint.
export type CostKind = "time" | "usage" | "maint";

// One key/value line rendered above the payment history (e.g. "Every: 1 year", "Next due: …"). Built
// by the caller so each cost type shows only the fields that make sense for it.
export interface CostHistoryMeta {
  label: string;
  value: string;
}

// A cost row the user clicked to open its history popup. `meta` is the type-specific summary
// (interval, next due, rate…) built by whichever table or panel owns the row.
export interface HistoryTarget {
  kind: CostKind;
  costId: string;
  label: string;
  meta: CostHistoryMeta[];
}

// The history-popup descriptor for a time-based cost. Shared by the Costs-screen table, the
// TimeCostPanel, and the dashboard so every entry point shows the same interval/next-due summary.
export function timeCostHistoryTarget(
  row: TimeBasedCost,
  t: ReturnType<typeof useTranslation>["t"],
  fmt: ReturnType<typeof useCurrency>,
): HistoryTarget {
  return {
    kind: "time",
    costId: row.id,
    label: row.label,
    meta: [
      { label: t("costs.th_amount"), value: fmt(row.reference_amount, { decimals: 0 }) },
      {
        label: t("costs.th_every"),
        value: t("costs.every_interval", { value: row.interval_value, unit: t(`costs.unit_${row.interval_unit}`) }),
      },
      { label: t("costs.th_next_due"), value: row.next_due_date ? fmtDate(row.next_due_date) : "—" },
    ],
  };
}

interface CostHistoryModalProps {
  assetId: string;
  kind: CostKind;
  costId: string;
  label: string;
  meta: CostHistoryMeta[];
  onClose: () => void;
}

const LISTERS: Record<CostKind, (assetId: string, costId: string) => Promise<ExpenseEvent[]>> = {
  time: api.listTimeBasedCostExpenses,
  usage: api.listUsageBasedCostExpenses,
  maint: api.listMaintenanceItemExpenses,
};

// Popup showing a single cost's interval/next-due summary plus its recorded payment history (each
// posted expense linked to the cost). Fetches on open; closes on backdrop click or Escape.
export function CostHistoryModal({ assetId, kind, costId, label, meta, onClose }: CostHistoryModalProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const expenses = useAsync(() => LISTERS[kind](assetId, costId), [assetId, kind, costId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const rows = expenses.data ?? [];
  // Ascending by event_date (backend order): amounts feed the trend, dates label its hover.
  const amounts = rows.map((r) => r.amount);
  const dates = rows.map((r) => fmtDateShort(r.event_date));

  // Portal to <body>: the Costs screen's `.content.fade-in` keeps a `transform` (animation
  // fill-mode `both`), which would otherwise make this fixed backdrop a child of that tall,
  // scrollable box and center the dialog within it (appearing low) instead of the viewport.
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-card cost-history-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cost-history-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="cost-history-hd">
          <h2 id="cost-history-title" className="h2">
            {label}
          </h2>
          <button className="btn btn-ghost btn-sm" aria-label={t("costHistory.close")} onClick={onClose}>
            <Icon name="close" size={16} />
          </button>
        </div>

        {meta.length > 0 && (
          <dl className="cost-history-meta">
            {meta.map((m) => (
              <div key={m.label} className="cost-history-meta-row">
                <dt>{m.label}</dt>
                <dd>{m.value}</dd>
              </div>
            ))}
          </dl>
        )}

        <div className="cost-history-title">{t("costHistory.past_payments")}</div>

        {expenses.loading ? (
          <LoadingState label={t("costHistory.loading")} />
        ) : expenses.error ? (
          <ErrorState message={expenses.error} onRetry={expenses.reload} />
        ) : rows.length === 0 ? (
          <div className="cost-history-empty muted">{t("costHistory.empty")}</div>
        ) : (
          <>
            {amounts.length >= 2 && (
              <div className="cost-history-spark">
                <Sparkline
                  data={amounts}
                  months={dates}
                  height={90}
                  fmtValue={(v) => fmt(v, { decimals: 0 })}
                />
              </div>
            )}
            <ul className="cost-history-list">
              {[...rows].reverse().map((r) => (
                <li key={r.id} className="cost-history-line">
                  <span className="cost-history-date">{fmtDate(r.event_date)}</span>
                  <span className="cost-history-comment">{r.comment ?? ""}</span>
                  <span className="cost-history-amount">{fmt(r.amount, { decimals: 0 })}</span>
                  {r.paid_out_of_pocket > 0 && (
                    <span className="cost-history-split">
                      {t("costHistory.split", {
                        bucket: fmt(r.bucket_amount, { decimals: 0 }),
                        pocket: fmt(r.paid_out_of_pocket, { decimals: 0 }),
                      })}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}
