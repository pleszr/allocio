import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { CostDistributionSlice } from "../api/types";
import { useCurrency } from "../utils/currency";

interface CostDistributionChartProps {
  slices: CostDistributionSlice[];
  total: number;
}

interface DisplaySlice {
  label: string;
  amount: number;
  color: string;
}

interface Arc {
  d: string;
  color: string;
  originalIndex: number;
}

// Donut for the Costs screen's cost-distribution card. Purely presentational — the screen fetches
// `GET /assets/{id}/cost-distribution` and passes the raw, already-sorted (largest-first) slices
// straight through. Bucketing the long tail into "Other" and picking display colors both happen
// here since they're rendering concerns: a pie reads at a glance only up to ~6 segments, so beyond
// the top 5 named cost items the remainder collapses into one "Other" wedge. The bucketed row set
// (`display`) is fixed once from the full unfiltered data — toggling a row's checkbox off only
// removes it from the visible donut/total, so unchecking doesn't reshuffle what counts as "Other".
const MAX_NAMED_SLICES = 5;
const OTHER_SHARE_FLOOR = 0.04;
const SERIES_COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)"];
const OTHER_COLOR = "var(--muted-2)";
const GAP_DEG = 3;

export function CostDistributionChart({ slices, total }: CostDistributionChartProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [isolatedIndex, setIsolatedIndex] = useState<number | null>(null);
  const [excludedLabels, setExcludedLabels] = useState<Set<string>>(() => new Set());

  const display = bucketIntoOther(slices, t("costs.distribution_other"));

  if (total <= 0 || display.length === 0) {
    return (
      <div className="state-wrap" style={{ padding: "32px 24px" }}>
        <div className="state-title">{t("costs.distribution_empty_title")}</div>
        <div className="state-msg">{t("costs.distribution_empty_message")}</div>
      </div>
    );
  }

  const visible = display
    .map((slice, originalIndex) => ({ ...slice, originalIndex }))
    .filter((slice) => !excludedLabels.has(slice.label));
  const visibleTotal = visible.reduce((sum, s) => sum + s.amount, 0);

  const toggleIsolate = (i: number) => setIsolatedIndex((cur) => (cur === i ? null : i));
  const toggleExcluded = (label: string, index: number) => {
    setExcludedLabels((cur) => {
      const next = new Set(cur);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
    if (hoveredIndex === index) setHoveredIndex(null);
    if (isolatedIndex === index) setIsolatedIndex(null);
  };

  const activeIndex = hoveredIndex ?? isolatedIndex;
  const centerSlice = activeIndex != null ? display[activeIndex] : null;

  return (
    <div style={{ display: "flex", gap: 28, alignItems: "center", flexWrap: "wrap" }}>
      <div style={{ position: "relative", width: 200, height: 200, flexShrink: 0 }}>
        {visible.length > 0 ? (
          <svg viewBox="0 0 200 200" width={200} height={200}>
            {buildArcs(visible).map((arc) => (
              <path
                key={arc.originalIndex}
                d={arc.d}
                fill="none"
                stroke={arc.color}
                strokeWidth={hoveredIndex === arc.originalIndex || isolatedIndex === arc.originalIndex ? 30 : 26}
                strokeLinecap="butt"
                opacity={isolatedIndex != null && isolatedIndex !== arc.originalIndex ? 0.3 : 1}
                style={{ transition: "opacity 0.2s ease, stroke-width 0.2s ease", cursor: "pointer" }}
                onMouseEnter={() => setHoveredIndex(arc.originalIndex)}
                onMouseLeave={() => setHoveredIndex(null)}
                onClick={() => toggleIsolate(arc.originalIndex)}
              />
            ))}
          </svg>
        ) : (
          <div
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: "50%",
              border: "2px dashed var(--line-strong)",
            }}
          />
        )}
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
            pointerEvents: "none",
            padding: 12,
          }}
        >
          {visible.length > 0 ? (
            <>
              <div className="muted" style={{ fontSize: 11.5 }}>
                {centerSlice ? centerSlice.label : t("costs.distribution_total")}
              </div>
              <div style={{ fontSize: 20, fontWeight: 600, color: "var(--ink)", lineHeight: 1.2 }}>
                {fmt(centerSlice ? centerSlice.amount : visibleTotal, { decimals: 0 })}
              </div>
              {centerSlice && (
                <div className="muted" style={{ fontSize: 11.5 }}>
                  {Math.round((centerSlice.amount / visibleTotal) * 100)}%
                </div>
              )}
            </>
          ) : (
            <div className="muted" style={{ fontSize: 12, lineHeight: 1.4 }}>
              {t("costs.distribution_all_hidden")}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 200, flex: 1 }}>
        {display.map((slice, i) => {
          const excluded = excludedLabels.has(slice.label);
          const pct = !excluded && visibleTotal > 0 ? Math.round((slice.amount / visibleTotal) * 100) : null;
          const dimmed = !excluded && isolatedIndex != null && isolatedIndex !== i;
          return (
            <div key={slice.label + i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={!excluded}
                onChange={() => toggleExcluded(slice.label, i)}
                aria-label={t("costs.distribution_toggle", { label: slice.label })}
                style={{ flexShrink: 0, cursor: "pointer" }}
              />
              <button
                type="button"
                disabled={excluded}
                onMouseEnter={() => setHoveredIndex(i)}
                onMouseLeave={() => setHoveredIndex(null)}
                onFocus={() => setHoveredIndex(i)}
                onBlur={() => setHoveredIndex(null)}
                onClick={() => toggleIsolate(i)}
                aria-pressed={isolatedIndex === i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  flex: 1,
                  padding: "6px 8px",
                  borderRadius: 8,
                  border: "none",
                  background: hoveredIndex === i ? "var(--surface-sunk)" : "transparent",
                  opacity: excluded ? 0.4 : dimmed ? 0.45 : 1,
                  cursor: excluded ? "default" : "pointer",
                  textAlign: "left",
                  transition: "opacity 0.2s ease, background 0.15s ease",
                }}
              >
                <span style={{ width: 10, height: 10, borderRadius: 3, background: slice.color, flexShrink: 0 }} />
                <span
                  style={{
                    flex: 1,
                    fontSize: 13,
                    color: "var(--ink)",
                    textDecoration: excluded ? "line-through" : "none",
                  }}
                >
                  {slice.label}
                </span>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>
                  {fmt(slice.amount, { decimals: 0 })}
                </span>
                <span className="muted" style={{ fontSize: 12, minWidth: 34, textAlign: "right" }}>
                  {pct != null ? `${pct}%` : "—"}
                </span>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function bucketIntoOther(slices: CostDistributionSlice[], otherLabel: string): DisplaySlice[] {
  const total = slices.reduce((sum, s) => sum + s.amount, 0);
  if (total <= 0) return [];
  const named = slices.filter((s) => s.amount / total >= OTHER_SHARE_FLOOR).slice(0, MAX_NAMED_SLICES);
  const namedLabels = new Set(named.map((s) => s.label));
  const otherAmount = slices.filter((s) => !namedLabels.has(s.label)).reduce((sum, s) => sum + s.amount, 0);
  const display = named.map((s, i) => ({ label: s.label, amount: s.amount, color: SERIES_COLORS[i] }));
  if (otherAmount > 0) display.push({ label: otherLabel, amount: otherAmount, color: OTHER_COLOR });
  return display;
}

function buildArcs(visible: (DisplaySlice & { originalIndex: number })[]): Arc[] {
  const total = visible.reduce((sum, s) => sum + s.amount, 0);
  let cursor = -90; // 12 o'clock; increasing degrees sweeps clockwise in SVG's y-down coordinates
  return visible.map((slice) => {
    const sweep = (slice.amount / total) * 360;
    const gap = Math.min(GAP_DEG, sweep * 0.3);
    const start = cursor + gap / 2;
    const end = cursor + sweep - gap / 2;
    cursor += sweep;
    return { d: arcPath(100, 100, 74, start, end), color: slice.color, originalIndex: slice.originalIndex };
  });
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const start = polarToCartesian(cx, cy, r, startDeg);
  const end = polarToCartesian(cx, cy, r, endDeg);
  const largeArc = endDeg - startDeg <= 180 ? 0 : 1;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
}

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number): { x: number; y: number } {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}
