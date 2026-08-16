import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TimeBasedCost } from "../api/types";
import { useCurrency } from "../utils/currency";
import { fmtDateShort } from "../utils/format";

interface TimeCostPanelProps {
  costs: TimeBasedCost[];
  // Reference "now" for the timeline. Defaults to the real current date; kept overridable so
  // callers (and future tests) can pin it deterministically.
  today?: Date;
  // Compact mode drops the month axis and the annual-total donut, so the panel fits inside a
  // dashboard card next to other summaries. The full variant (Costs screen) shows both.
  compact?: boolean;
  // When provided, clicking a cost (in the list or on its timeline bar) opens its history instead
  // of just toggling the timeline highlight. The Costs screen passes this; the dashboard omits it.
  onOpenHistory?: (cost: TimeBasedCost) => void;
}

interface TimelineItem extends TimeBasedCost {
  // Days until next_due_date, or null when the cost has no due date set yet.
  days: number | null;
  // Position on the 12-month track in months from "today" (0..12+), or null when undated. Undated
  // costs still appear in the list and donut; they just can't be placed on the timeline.
  frac: number | null;
}

// Timeline + donut view of an asset's recurring time-based costs. Purely presentational: the caller
// passes already-fetched cost rows. Every active cost shows in the list and (full variant) the
// annual-total donut; the timeline plots only the costs that have a resolved next_due_date, since a
// cost with no due date has no position on the calendar.
export function TimeCostPanel({ costs, today = new Date(), compact, onOpenHistory }: TimeCostPanelProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const activeId = hovered ?? selected;

  const items = useMemo<TimelineItem[]>(() => {
    return costs
      .filter((c) => c.is_active)
      .map((c) => {
        const days = c.next_due_date
          ? Math.round((new Date(c.next_due_date).getTime() - today.getTime()) / 86400000)
          : null;
        const frac = days != null ? Math.max(0, (days / 365) * 12) : null;
        return { ...c, days, frac };
      })
      .sort((a, b) => {
        // Dated costs first, soonest-due at the top; undated costs after, in stable order.
        if (a.days == null && b.days == null) return 0;
        if (a.days == null) return 1;
        if (b.days == null) return -1;
        return a.days - b.days;
      });
  }, [costs, today]);

  if (items.length === 0) return null;
  const dated = items.filter((i) => i.frac != null);

  // Donut proportions use each cost's annualized weight (what it costs across a year), while the
  // list shows the per-occurrence amount and its magnitude relative to the largest occurrence.
  const annualTotal = items.reduce((sum, i) => sum + i.annualized_amount, 0);
  const maxAmount = Math.max(...items.map((i) => i.reference_amount));
  const rankedByAnnual = [...items].sort((a, b) => a.annualized_amount - b.annualized_amount);

  const left = 8;
  const right = 97;
  const rowH = compact ? 8 : 9;
  const rowTop = 8;
  const xForFrac = (f: number) => left + (Math.min(f, 12) / 12) * (right - left);
  const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
  const startMonthIdx = today.getMonth();

  // Donut arcs: one stroked circle segment per cost, sized by its share of the annual total.
  const R = 40;
  const C = 2 * Math.PI * R;
  const GAP = 1.2;
  let offsetAcc = 0;
  const arcs = items.map((it) => {
    const share = annualTotal > 0 ? it.annualized_amount / annualTotal : 0;
    const len = Math.max(share * C - GAP, 2);
    const rank = rankedByAnnual.findIndex((x) => x.id === it.id);
    const lightness = items.length > 1 ? 0.4 + (rank / (items.length - 1)) * 0.42 : 0.55;
    const arc = {
      id: it.id,
      dasharray: `${len} ${C - len}`,
      dashoffset: -offsetAcc,
      color: `oklch(${lightness.toFixed(2)} 0.015 260)`,
    };
    offsetAcc += share * C;
    return arc;
  });

  const active = items.find((i) => i.id === activeId);
  const dueLabel = (it: TimelineItem) =>
    it.days == null ? t("timeCostPanel.no_due_date") : it.days < 0 ? t("timeCostPanel.overdue") : t("timeCostPanel.in_days", { days: it.days });
  const focusText = active
    ? t("timeCostPanel.focus", { label: active.label, amount: fmt(active.reference_amount, { decimals: 0 }), due: dueLabel(active) })
    : t("timeCostPanel.hover_hint");

  const hoverHandlers = (id: string) => ({
    onMouseEnter: (ev: React.MouseEvent) => {
      ev.stopPropagation();
      setHovered(id);
    },
    onMouseLeave: () => setHovered(null),
    onClick: (ev: React.MouseEvent) => {
      ev.stopPropagation();
      if (onOpenHistory) {
        const cost = costs.find((c) => c.id === id);
        if (cost) onOpenHistory(cost);
        return;
      }
      setSelected((s) => (s === id ? null : id));
    },
  });

  return (
    <div className="tcp" onClick={() => setSelected(null)}>
      <div className="tcp-stage">
        <div className="tcp-hd">
          <span className="tcp-title">{t("timeCostPanel.next_12_months")}</span>
          <span className="tcp-focus">{focusText}</span>
        </div>
        {dated.length === 0 ? (
          <div className="tcp-no-dates">{t("timeCostPanel.no_dates_hint")}</div>
        ) : (
          <svg
            className="tcp-svg"
            viewBox={`0 0 100 ${rowTop + dated.length * rowH + 8}`}
            preserveAspectRatio="xMidYMid meet"
          >
            {!compact &&
              MONTHS.map((_, i) => {
                const idx = (startMonthIdx + i) % 12;
                return (
                  <text key={i} x={xForFrac(i)} y={4} className="tcp-month" textAnchor="middle">
                    {MONTHS[idx]}
                  </text>
                );
              })}
            <line x1={left} x2={left} y1={rowTop - 4} y2={rowTop + dated.length * rowH + 1} className="tcp-today" />
            {dated.map((it, i) => {
              const y = rowTop + i * rowH;
              const dueX = xForFrac(it.frac as number);
              return (
                <g key={it.id}>
                  <line x1={left} x2={right} y1={y} y2={y} className="tcp-track-bg" />
                  <line x1={left} x2={dueX} y1={y} y2={y} className={`tcp-track-fill${activeId === it.id ? " active" : ""}`} />
                  <circle cx={dueX} cy={y} r="1.5" className={`tcp-dot${activeId === it.id ? " active" : ""}`} />
                  <rect x={left} y={y - rowH / 2} width={right - left} height={rowH} className="tcp-hit" {...hoverHandlers(it.id)} />
                </g>
              );
            })}
          </svg>
        )}
      </div>
      <div className="tcp-right">
        <div className="tcp-list">
          {items.map((it) => (
            <div
              key={it.id}
              className={`tcp-item${selected === it.id ? " selected" : ""}${hovered === it.id ? " hovered" : ""}`}
              {...hoverHandlers(it.id)}
            >
              <span className="tcp-item-body">
                <span className="tcp-item-name">{it.label}</span>
                <span className="tcp-item-sub">
                  {it.next_due_date
                    ? t("timeCostPanel.due_date", { date: fmtDateShort(it.next_due_date) })
                    : t("timeCostPanel.no_due_date")}
                </span>
              </span>
              <span className="tcp-item-amt">
                {fmt(it.reference_amount, { decimals: 0 })}
                <span className="tcp-magnitude">
                  <i style={{ width: `${maxAmount > 0 ? Math.round((it.reference_amount / maxAmount) * 100) : 0}%` }} />
                </span>
              </span>
            </div>
          ))}
        </div>
        {!compact && (
          <div className="tcp-pie-row">
            <svg className="tcp-pie-svg" viewBox="0 0 100 100">
              {arcs.map((a) => (
                <circle
                  key={a.id}
                  cx="50"
                  cy="50"
                  r={R}
                  className={`tcp-pie-slice${activeId === a.id ? " active" : ""}${activeId && activeId !== a.id ? " dimmed" : ""}`}
                  style={{ stroke: a.color }}
                  strokeDasharray={a.dasharray}
                  strokeDashoffset={a.dashoffset}
                  onMouseEnter={() => setHovered(a.id)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={(ev) => {
                    ev.stopPropagation();
                    setSelected((s) => (s === a.id ? null : a.id));
                  }}
                />
              ))}
            </svg>
            <div className="tcp-pie-center">
              <div className="tcp-pie-lbl">{t("timeCostPanel.annual_total")}</div>
              <div className="tcp-pie-total">{fmt(annualTotal, { decimals: 0 })}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
