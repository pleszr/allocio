import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { MaintenanceItem } from "../api/types";
import { fmtNumber } from "../utils/format";

// An anatomical "where does this live" overlay: maintenance items glow over a side-profile car
// schematic when hovered. Region coordinates are a frontend-static map keyed by the built-in
// vehicle template's technical_key, expressed as percentages/units over the SVG's own viewBox.
// They are approximate, illustrative placements — not a precise mechanical diagram — and only the
// built-in vehicle template rows are mapped. Assets whose maintenance rows carry no mapped
// technical_key (custom vehicle rows, houses, pets) produce no items and the map renders nothing.
const CAR_VIEWBOX = "0 0 240 120";

interface Region {
  cx: number;
  cy: number;
  rx: number;
  ry: number;
}

const FRONT_WHEEL: Region = { cx: 64, cy: 100, rx: 13, ry: 13 };
const REAR_WHEEL: Region = { cx: 176, cy: 100, rx: 13, ry: 13 };
const BOTH_WHEELS: Region[] = [
  { cx: 64, cy: 100, rx: 15, ry: 15 },
  { cx: 176, cy: 100, rx: 15, ry: 15 },
];

const CAR_REGIONS: Record<string, Region[]> = {
  annual_service: [{ cx: 48, cy: 74, rx: 15, ry: 11 }],
  timing_system: [{ cx: 40, cy: 76, rx: 8, ry: 8 }],
  water_pump: [{ cx: 57, cy: 78, rx: 7, ry: 7 }],
  automatic_transmission_fluid: [{ cx: 72, cy: 84, rx: 8, ry: 7 }],
  fuel_filter: [{ cx: 150, cy: 88, rx: 8, ry: 7 }],
  battery: [{ cx: 34, cy: 70, rx: 7, ry: 6 }],
  front_brake_pad: [FRONT_WHEEL],
  front_brake_disc: [FRONT_WHEEL],
  rear_brake_pad: [REAR_WHEEL],
  rear_brake_disc: [REAR_WHEEL],
  all_season_tires: BOTH_WHEELS,
  winter_tires: BOTH_WHEELS,
  summer_tires: BOTH_WHEELS,
};

interface SpatialItem {
  id: string;
  label: string;
  status: MaintenanceItem["status"];
  regions: Region[];
  item: MaintenanceItem;
}

// The active maintenance items that have a mapped region, in template order. Exported so a screen
// can decide whether to render the map section at all (header + component) without duplicating the
// filter logic.
export function spatialItems(maintenanceItems: MaintenanceItem[]): SpatialItem[] {
  return maintenanceItems
    .filter((m) => m.is_active && m.technical_key !== null && CAR_REGIONS[m.technical_key] !== undefined)
    .map((m) => ({
      id: m.id,
      label: m.label,
      status: m.status,
      regions: CAR_REGIONS[m.technical_key as string],
      item: m,
    }));
}

function dotClass(status: MaintenanceItem["status"]): string {
  if (status === "overdue") return "bad";
  if (status === "due" || status === "soon") return "warn";
  return "good";
}

interface SpatialMapProps {
  maintenanceItems: MaintenanceItem[];
}

export function SpatialMap({ maintenanceItems }: SpatialMapProps) {
  const { t } = useTranslation();
  const items = useMemo(() => spatialItems(maintenanceItems), [maintenanceItems]);
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const activeId = hovered ?? selected;
  const active = items.find((i) => i.id === activeId);

  if (items.length === 0) return null;

  const subText = (item: MaintenanceItem): string => {
    if (item.status === "overdue") return t("spatialMap.overdue");
    if (item.remaining_km !== null) return t("spatialMap.km_left", { km: fmtNumber(item.remaining_km) });
    if (item.remaining_months !== null) return t("spatialMap.months_left", { months: item.remaining_months });
    return "";
  };

  const focusText = active ? [active.label, subText(active.item)].filter(Boolean).join(" · ") : t("spatialMap.focus_hint");

  return (
    <div className="spatial-map" onClick={() => setSelected(null)}>
      <div className="spatial-stage">
        <div className="spatial-focus">{focusText}</div>
        <div className={`spatial-hero-wrap${activeId ? " dimmed" : ""}`}>
          <CarSchematic />
          <svg className="spatial-overlay" viewBox={CAR_VIEWBOX} preserveAspectRatio="xMidYMid meet">
            {items.flatMap((it) =>
              it.regions.map((r, ri) => (
                <g key={it.id + ri}>
                  <ellipse
                    className={`spatial-region${activeId === it.id ? " active" : ""}`}
                    cx={r.cx}
                    cy={r.cy}
                    rx={r.rx}
                    ry={r.ry}
                  />
                  <ellipse
                    className={`spatial-region-core${activeId === it.id ? " active" : ""}`}
                    cx={r.cx}
                    cy={r.cy}
                    rx={r.rx * 0.5}
                    ry={r.ry * 0.5}
                  />
                </g>
              )),
            )}
          </svg>
        </div>
      </div>
      <div className="spatial-list">
        {items.map((it) => {
          const sub = subText(it.item);
          return (
            <div
              key={it.id}
              className={`spatial-item${selected === it.id ? " selected" : ""}${hovered === it.id ? " hovered" : ""}`}
              onMouseEnter={(ev) => {
                ev.stopPropagation();
                setHovered(it.id);
              }}
              onMouseLeave={() => setHovered(null)}
              onClick={(ev) => {
                ev.stopPropagation();
                setSelected((s) => (s === it.id ? null : it.id));
              }}
            >
              <span className={`spatial-dot ${dotClass(it.status)}`} />
              <span className="spatial-item-body">
                <span className="spatial-item-name">{it.label}</span>
                {sub && <span className="spatial-item-sub">{sub}</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Side-profile car outline. Purely decorative stroke art (no fill) so it reads in both themes via
// the shared line-color vars; the overlay regions above are positioned against this viewBox.
function CarSchematic() {
  return (
    <svg className="hero-img hero-svg" viewBox={CAR_VIEWBOX} aria-hidden="true">
      <line x1="10" y1="100" x2="230" y2="100" stroke="var(--line)" strokeWidth="2" />
      <path
        d="M28 88 L40 66 Q44 60 52 60 L96 60 L120 44 L160 44 Q170 44 176 54 L196 66 L212 70 Q220 72 220 82 L220 88"
        fill="none"
        stroke="var(--line-strong)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <path d="M28 88 L52 88 M76 88 L164 88 M188 88 L220 88" stroke="var(--line-strong)" strokeWidth="2" strokeLinecap="round" />
      <path d="M100 58 L120 46 L150 46 L150 58 Z" fill="none" stroke="var(--line-strong)" strokeWidth="1.5" strokeLinejoin="round" />
      <line x1="126" y1="47" x2="126" y2="58" stroke="var(--line-strong)" strokeWidth="1.5" />
      <circle cx="64" cy="100" r="13" fill="none" stroke="var(--line-strong)" strokeWidth="2.5" />
      <circle cx="64" cy="100" r="5" fill="none" stroke="var(--line-strong)" strokeWidth="1.5" />
      <circle cx="176" cy="100" r="13" fill="none" stroke="var(--line-strong)" strokeWidth="2.5" />
      <circle cx="176" cy="100" r="5" fill="none" stroke="var(--line-strong)" strokeWidth="1.5" />
    </svg>
  );
}
