import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { CheckInHistoryRow } from "../api/types";
import { Icon } from "../components/Icon";
import { ErrorState, LoadingState } from "../components/StateView";
import { useCurrency } from "../utils/currency";
import { fmtDate, fmtNumber } from "../utils/format";
import { useAsync } from "../utils/useAsync";

interface HistoryScreenProps {
  assetId: string;
  onEditCheckIn: (checkInId: string) => void;
}

export function HistoryScreen({ assetId, onEditCheckIn }: HistoryScreenProps) {
  const { t } = useTranslation();
  const asset = useAsync(() => api.getAsset(assetId), [assetId]);
  const history = useAsync(() => api.getCheckInHistory(assetId), [assetId]);

  if (asset.loading || history.loading) return <LoadingState label={t("history.loading")} />;
  if (asset.error || history.error || !asset.data || !history.data) {
    return (
      <ErrorState
        message={asset.error ?? history.error ?? t("history.not_found")}
        onRetry={() => {
          asset.reload();
          history.reload();
        }}
      />
    );
  }

  const rows = history.data.rows;
  const avgRate = averageKmPerDay(rows);

  return (
    <div className="content fade-in">
      <div className="section-head">
        <div>
          <h1 className="h1">{t("history.title")}</h1>
          <div className="muted" style={{ marginTop: 6, fontSize: 14 }}>
            {t("history.subtitle", { name: asset.data.name, avgRate: avgRate.toFixed(1) })}
          </div>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="muted">{t("history.empty")}</div>
      ) : (
        <div className="card">
          <div className="table-scroll">
            <table className="table history-table">
              <thead>
                <tr>
                  <th>{t("history.th_date")}</th>
                  <th className="col-num">{t("history.th_odometer")}</th>
                  <th className="col-num">{t("history.th_since_last")}</th>
                  <th className="col-num">{t("history.th_km_per_day")}</th>
                  <th className="col-num">{t("history.th_allocated")}</th>
                  <th className="col-num">{t("history.th_expense")}</th>
                  <th className="col-num">{t("history.th_bucket_expense")}</th>
                  <th className="col-num">{t("history.th_paid_out_of_pocket")}</th>
                  <th className="col-num">{t("history.th_net")}</th>
                  <th className="col-num">{t("history.th_balance")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <HistoryRow key={row.check_in_id} row={row} avgRate={avgRate} onEdit={onEditCheckIn} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// Mean km/day across rows with both a usage delta and a positive elapsed period; 0 when no row
// qualifies (e.g. a non-usage asset, or an all-baseline history), guarding the divide-by-zero the
// per-row heat coloring below depends on.
function averageKmPerDay(rows: CheckInHistoryRow[]): number {
  const rates = rows
    .map((row) => kmPerDay(row))
    .filter((rate): rate is number => rate !== null);
  if (rates.length === 0) return 0;
  return rates.reduce((sum, rate) => sum + rate, 0) / rates.length;
}

function kmPerDay(row: CheckInHistoryRow): number | null {
  if (row.usage_since_last == null || row.elapsed_days <= 0) return null;
  return row.usage_since_last / row.elapsed_days;
}

// Heat color for km/day vs the asset's average: green = below average (less wear), red = above
// average (more wear). Ported from the Claude Design mockup's `usageHeat` (screens/history.jsx).
function usageHeat(rate: number | null, avg: number): string | null {
  if (rate == null || !avg) return null;
  const ratio = rate / avg;
  const dev = Math.min(1, Math.abs(ratio - 1));
  if (ratio >= 1.15) return `rgba(192,59,59,${0.08 + dev * 0.35})`;
  if (ratio <= 0.85) return `rgba(31,139,90,${0.08 + dev * 0.3})`;
  return null;
}

function HistoryRow({
  row,
  avgRate,
  onEdit,
}: {
  row: CheckInHistoryRow;
  avgRate: number;
  onEdit: (checkInId: string) => void;
}) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [expanded, setExpanded] = useState(false);
  const rate = kmPerDay(row);
  const heat = usageHeat(rate, avgRate);
  const irregularCadence = row.elapsed_days !== 0 && (row.elapsed_days < 27 || row.elapsed_days > 32);
  const hasExpenses = row.expenses.length > 0;

  return (
    <>
      <tr>
        <td className="col-name">
          {hasExpenses && (
            <button
              type="button"
              className={`history-row-toggle${expanded ? " history-row-toggle-open" : ""}`}
              aria-expanded={expanded}
              aria-label={t(expanded ? "history.collapse_expenses" : "history.expand_expenses")}
              onClick={() => setExpanded((v) => !v)}
            >
              <Icon name="chevronRight" />
            </button>
          )}
          <button
            type="button"
            className="history-row-toggle"
            aria-label={t("history.edit_check_in")}
            title={t("history.edit_check_in")}
            onClick={() => onEdit(row.check_in_id)}
          >
            <Icon name="edit" size={14} />
          </button>
          {fmtDate(row.period_end)}
          {irregularCadence && (
            <span
              title={t("history.irregular_cadence", { days: row.elapsed_days })}
              style={{ marginLeft: 6, color: "var(--warn)", fontSize: 11, verticalAlign: "middle" }}
            >
              ●
            </span>
          )}
        </td>
        <td className="col-num">{row.usage_end != null ? fmtNumber(row.usage_end) : "—"}</td>
        <td className="col-num row-meta">
          {row.usage_since_last != null ? `+${fmtNumber(row.usage_since_last)} km` : "—"}
        </td>
        <td
          className="col-num"
          style={{ background: heat ?? "transparent", fontWeight: heat ? 600 : 400, borderRadius: 6 }}
        >
          {rate != null ? rate.toFixed(1) : "—"}
        </td>
        <td className="col-num row-meta">{fmt(row.allocated, { decimals: 2, sign: true })}</td>
        <td className="col-num row-meta">{fmt(-row.expense, { decimals: 2 })}</td>
        <td className="col-num row-meta">{fmt(-row.bucket_expense, { decimals: 2 })}</td>
        <td className="col-num row-meta">{fmt(row.paid_out_of_pocket, { decimals: 2 })}</td>
        <td className="col-num" style={{ fontWeight: 500, color: row.net >= 0 ? "var(--good)" : "var(--bad)" }}>
          {fmt(row.net, { decimals: 2, sign: true })}
        </td>
        <td className="col-num" style={{ fontWeight: 600 }}>
          {fmt(row.balance, { decimals: 2 })}
        </td>
      </tr>
      {expanded && (
        <tr className="history-detail-row">
          <td colSpan={10}>
            <ul className="history-expense-list">
              {row.expenses.map((line, index) => (
                <li key={index} className="history-expense-line">
                  <span className="history-expense-comment">{line.label}</span>
                  <span className="history-expense-amount">{fmt(-line.amount, { decimals: 2 })}</span>
                  {line.paid_out_of_pocket > 0 && (
                    <span className="history-expense-split">
                      {t("history.th_bucket_expense")}: {fmt(line.bucket_amount, { decimals: 2 })} ·{" "}
                      {t("history.th_paid_out_of_pocket")}: {fmt(line.paid_out_of_pocket, { decimals: 2 })}
                    </span>
                  )}
                  <span className="history-expense-date">{fmtDate(line.event_date)}</span>
                </li>
              ))}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}
