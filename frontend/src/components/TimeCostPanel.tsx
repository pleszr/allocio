import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TimeBasedCost } from "../api/types";
import { useCurrency } from "../utils/currency";
import { fmtDateShort } from "../utils/format";
import { Icon, type IconName } from "./Icon";

interface TimeCostPanelProps {
  costs: TimeBasedCost[];
  // Reference "now" for the timeline. Defaults to the real current date; kept overridable so
  // callers (and future tests) can pin it deterministically.
  today?: Date;
  // When provided, clicking a cost (in the list or on its strip marker) opens its history instead
  // of just toggling the highlight.
  onOpenHistory?: (cost: TimeBasedCost) => void;
}

interface TimelineItem extends TimeBasedCost {
  // Days until next_due_date, or null when the cost has no due date set yet.
  days: number | null;
  // Position on the 12-month strip in months from "today" (0..12+), or null when undated.
  frac: number | null;
}

type Tone = "bad" | "warn" | "good" | null;

function tone(days: number | null): Tone {
  if (days === null) return null;
  if (days < 0) return "bad";
  if (days <= 30) return "warn";
  return "good";
}

// technical_key -> glyph, covering every built-in time-based cost template (vehicle, house, pet).
// A custom row (technical_key null) or any key not listed here falls back to a generic receipt.
const TIME_COST_ICON: Record<string, IconName> = {
  seasonal_tire_change: "tire",
  vehicle_inspection: "clipboardCheck",
  mandatory_liability_insurance: "shield",
  comprehensive_insurance: "shieldCheck",
  vehicle_tax: "receipt",
  motorway_vignette: "ticket",
  building_tax: "receipt",
  home_insurance: "shield",
  boiler_cleaning: "flame",
  air_conditioner_cleaning: "wind",
  pet_insurance: "shieldCheck",
  annual_vaccinations: "syringe",
};

export function timeCostIcon(cost: TimeBasedCost): IconName {
  if (cost.technical_key !== null) {
    const icon = TIME_COST_ICON[cost.technical_key];
    if (icon) return icon;
  }
  return "receipt";
}

const left = 3;
const right = 97;
const xForFrac = (f: number) => left + (Math.min(f, 12) / 12) * (right - left);
const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

// Horizon strip + stats rail + due-soonest-first list for an asset's recurring time-based costs.
// Purely presentational: the caller passes already-fetched cost rows. The strip plots only costs
// with a resolved next_due_date (an undated cost has no position on the calendar); the rail and
// list cover every active cost regardless of date.
export function TimeCostPanel({ costs, today = new Date(), onOpenHistory }: TimeCostPanelProps) {
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

  // Markers whose strip position falls within 4% of the previous one alternate onto a second row
  // so two costs due close together (or on the same day) don't render as one hidden icon.
  let lastX: number | null = null;
  let stackLevel = 0;
  const markerPositions = dated.map((it) => {
    const x = xForFrac(it.frac as number);
    stackLevel = lastX !== null && x - lastX < 4 ? (stackLevel === 0 ? 1 : 0) : 0;
    lastX = x;
    return { it, x, stackLevel };
  });

  const annualTotal = items.reduce((sum, i) => sum + i.annualized_amount, 0);
  const monthlyTotal = annualTotal / 12;

  // Share bar / legend use a monochrome lightness ramp keyed by each cost's annualized weight —
  // avoids inventing a new categorical palette for what is otherwise a single-series breakdown.
  const rankedByAnnual = [...items].sort((a, b) => a.annualized_amount - b.annualized_amount);
  const shareColor = (id: string) => {
    const rank = rankedByAnnual.findIndex((x) => x.id === id);
    const lightness = items.length > 1 ? 0.4 + (rank / (items.length - 1)) * 0.42 : 0.55;
    return `oklch(${lightness.toFixed(2)} 0.015 260)`;
  };
  const legendItems = [...items].sort((a, b) => b.annualized_amount - a.annualized_amount);

  const startMonthIdx = today.getMonth();

  const dueLabel = (it: TimelineItem) => {
    if (it.days == null) return t("timeCostPanel.no_due_date");
    if (it.days < 0) return t("timeCostPanel.overdue");
    return t("timeCostPanel.in_days", { count: it.days });
  };

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
      <div className="tcp-strip-wrap">
        <div className="tcp-strip-lbl">{t("timeCostPanel.next_12_months")}</div>
        {dated.length === 0 ? (
          <div className="tcp-no-dates">{t("timeCostPanel.no_dates_hint")}</div>
        ) : (
          <div className="tcp-strip">
            {MONTHS.map((_, i) => (
              <span key={i} className="tcp-tick" style={{ left: `${xForFrac(i)}%` }}>
                {MONTHS[(startMonthIdx + i) % 12]}
              </span>
            ))}
            <div className="tcp-axis" />
            <div className="tcp-today" style={{ left: `${left}%` }} />
            {markerPositions.map(({ it, x, stackLevel }) => (
              <span
                key={it.id}
                className={`tcp-marker${tone(it.days) ? ` tone-${tone(it.days)}` : ""}${activeId === it.id ? " active" : ""}`}
                style={{ left: `${x}%`, top: `${34 - stackLevel * 16}px` }}
                {...hoverHandlers(it.id)}
              >
                <Icon name={timeCostIcon(it)} size={12} />
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="tcp-body">
        <div className="tcp-rail">
          <div className="tcp-stat-lbl">{t("timeCostPanel.this_month")}</div>
          <div className="tcp-stat-big">{fmt(monthlyTotal, { decimals: 0 })}</div>
          <div className="tcp-stat-lbl" style={{ marginTop: 14 }}>
            {t("timeCostPanel.this_year")}
          </div>
          <div className="tcp-stat-mid">{fmt(annualTotal, { decimals: 0 })}</div>

          <div className="tcp-divider" />
          <div className="tcp-stat-lbl">{t("timeCostPanel.share_of_total")}</div>
          <div className="tcp-share-bar">
            {legendItems.map((it) => (
              <i
                key={it.id}
                style={{
                  flexBasis: `${annualTotal > 0 ? (it.annualized_amount / annualTotal) * 100 : 0}%`,
                  background: shareColor(it.id),
                  opacity: activeId && activeId !== it.id ? 0.45 : 1,
                }}
              />
            ))}
          </div>
          <div className="tcp-legend">
            {legendItems.map((it) => (
              <span key={it.id} className={activeId === it.id ? "active" : ""}>
                <i style={{ background: shareColor(it.id) }} />
                {it.label} &middot; {annualTotal > 0 ? Math.round((it.annualized_amount / annualTotal) * 100) : 0}%
              </span>
            ))}
          </div>
        </div>

        <div className="tcp-list">
          {items.map((it) => {
            const rowTone = tone(it.days);
            return (
              <div
                key={it.id}
                className={`tcp-item${selected === it.id ? " selected" : ""}${hovered === it.id ? " hovered" : ""}`}
                {...hoverHandlers(it.id)}
              >
                <span className={`tcp-ico${rowTone ? ` tone-${rowTone}` : ""}`}>
                  <Icon name={timeCostIcon(it)} size={16} />
                </span>
                <span className="tcp-item-body">
                  <span className="tcp-item-head">
                    <span className="tcp-item-name">{it.label}</span>
                    <span className="tcp-item-amt">{fmt(it.reference_amount, { decimals: 0 })}</span>
                  </span>
                  <span className="tcp-item-meta">
                    {it.next_due_date && (
                      <>
                        {t("timeCostPanel.due_date", { date: fmtDateShort(it.next_due_date) })} &middot;{" "}
                      </>
                    )}
                    {dueLabel(it)}
                  </span>
                </span>
                <Icon name="chevronRight" size={14} className="tcp-chev" />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
