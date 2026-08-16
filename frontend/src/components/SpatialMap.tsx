import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { MaintenanceItem } from "../api/types";
import { fmtNumber } from "../utils/format";
import { Icon } from "./Icon";
import carXray from "../assets/car-xray.webp";

// An anatomical "where does this live" overlay: maintenance items glow over a side-profile car
// schematic when hovered. Region coordinates are a frontend-static map keyed by the built-in
// vehicle template's technical_key, expressed as percentages/units over the SVG's own viewBox.
// They are approximate, illustrative placements — not a precise mechanical diagram — and only the
// built-in vehicle template rows are mapped. Assets whose maintenance rows carry no mapped
// technical_key (custom vehicle rows, houses, pets) produce no items and the map renders nothing.
// Overlay coordinates are percentages of the x-ray image: the overlay SVG uses viewBox 0 0 100 100
// with preserveAspectRatio="none", so it maps linearly onto the full image box in both axes and
// (cx, cy) reads as (x%, y%) of the photo. Placements were verified visually against the render.
const CAR_VIEWBOX = "0 0 100 100";

interface Region {
  cx: number;
  cy: number;
  rx: number;
  ry: number;
}

const FRONT_WHEEL: Region[] = [{ cx: 44, cy: 76, rx: 5.5, ry: 8.5 }];
const REAR_WHEEL: Region[] = [{ cx: 87.5, cy: 53, rx: 4.5, ry: 6.5 }];
const BOTH_WHEELS: Region[] = [
  { cx: 43, cy: 79, rx: 7.5, ry: 11 },
  { cx: 90.5, cy: 57.5, rx: 6.5, ry: 10 },
];

const CAR_REGIONS: Record<string, Region[]> = {
  annual_service: [{ cx: 21.5, cy: 52, rx: 8.5, ry: 11 }],
  timing_system: [{ cx: 17.5, cy: 50.5, rx: 4.5, ry: 6 }],
  water_pump: [{ cx: 18.5, cy: 58.5, rx: 4.5, ry: 6 }],
  battery: [{ cx: 30, cy: 47, rx: 4.5, ry: 5.5 }],
  automatic_transmission_fluid: [{ cx: 35, cy: 58.5, rx: 4.5, ry: 6 }],
  fuel_filter: [{ cx: 57.5, cy: 63, rx: 5, ry: 6 }],
  front_brake_pad: FRONT_WHEEL,
  front_brake_disc: FRONT_WHEEL,
  rear_brake_pad: REAR_WHEEL,
  rear_brake_disc: REAR_WHEEL,
  all_season_tires: BOTH_WHEELS,
  winter_tires: BOTH_WHEELS,
  summer_tires: BOTH_WHEELS,
};

// Mirrors backend/app/domain/calculator.py: a ratio at or past _SOON_RATIO is approaching its
// interval, at or past _OVERDUE_RATIO it is past due. Per-bar colouring uses these directly so
// each dimension shows its own state, unlike item.status which is the max of the two.
export const MAINT_WARN_RATIO = 0.8;
export const MAINT_OVERDUE_RATIO = 1.05;

// A single progress bar's colour comes from its own ratio, not the row's combined status.
export function barTone(ratio: number): string {
  if (ratio >= MAINT_OVERDUE_RATIO) return "bad";
  if (ratio >= MAINT_WARN_RATIO) return "warn";
  return "";
}

export interface SpatialItem {
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

export function dotClass(status: MaintenanceItem["status"]): string {
  if (status === "overdue") return "bad";
  if (status === "due" || status === "soon") return "warn";
  return "good";
}

// The car x-ray with the glowing region overlay, driven by an externally-controlled `activeId`.
// Shared by SpatialMap (Costs screen, with its own list) and MaintenancePanel (dashboard, with the
// unified maintenance list). `items` are the mapped rows only — the ones that have a car region.
export function CarDiagram({ items, activeId }: { items: SpatialItem[]; activeId: string | null }) {
  const { t } = useTranslation();
  return (
    <div className={`spatial-hero-wrap${activeId ? " dimmed" : ""}`}>
      <img className="hero-img" src={carXray} alt={t("spatialMap.car_alt")} />
      <svg className="spatial-overlay" viewBox={CAR_VIEWBOX} preserveAspectRatio="none">
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
  );
}

// The focus line above the car. Shows the hovered item's label plus every dimension that has a
// remaining figure, because the per-row text was replaced by bars and this is now the only
// place the actual numbers are readable.
export function maintenanceFocusText(item: MaintenanceItem, t: TFunction): string {
  if (item.status === "overdue") return `${item.label} · ${t("spatialMap.overdue")}`;
  const parts = [item.label];
  if (item.remaining_km !== null) parts.push(t("spatialMap.km_left", { km: fmtNumber(item.remaining_km) }));
  if (item.remaining_months !== null) parts.push(t("spatialMap.months_left", { months: item.remaining_months }));
  return parts.join(" · ");
}

interface MaintenanceRowProps extends React.HTMLAttributes<HTMLDivElement> {
  item: MaintenanceItem;
}

export function MaintenanceRow({ item, className, ...rowProps }: MaintenanceRowProps) {
  const { t } = useTranslation();
  const hasBars = item.km_progress !== null || item.month_progress !== null;
  return (
    <div className={`spatial-item${className ?? ""}`} {...rowProps}>
      <span className={`spatial-dot ${dotClass(item.status)}`} />
      <span className="spatial-item-body">
        <span className="spatial-item-name">{item.label}</span>
        {hasBars && (
          <span className="maint-bars">
            {item.km_progress !== null && (
              <span
                className="maint-bar"
                aria-label={t("spatialMap.km_left", { km: fmtNumber(item.remaining_km ?? 0) })}
              >
                <Icon name="odometer" size={12} className="maint-bar-icon" />
                <span className="bar-track">
                  <span
                    className={`bar-fill ${barTone(item.km_progress)}`}
                    style={{ ["--pct" as string]: `${Math.min(1, item.km_progress) * 100}%` }}
                  />
                </span>
              </span>
            )}
            {item.month_progress !== null && (
              <span
                className="maint-bar"
                aria-label={t("spatialMap.months_left", { months: item.remaining_months ?? 0 })}
              >
                <Icon name="clock" size={12} className="maint-bar-icon" />
                <span className="bar-track">
                  <span
                    className={`bar-fill ${barTone(item.month_progress)}`}
                    style={{ ["--pct" as string]: `${Math.min(1, item.month_progress) * 100}%` }}
                  />
                </span>
              </span>
            )}
          </span>
        )}
      </span>
    </div>
  );
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

  const focusText = active ? maintenanceFocusText(active.item, t) : t("spatialMap.focus_hint");

  return (
    <div className="spatial-map" onClick={() => setSelected(null)}>
      <div className="spatial-stage">
        <div className="spatial-focus">{focusText}</div>
        <CarDiagram items={items} activeId={activeId} />
      </div>
      <div className="spatial-list">
        {items.map((it) => (
          <MaintenanceRow
            key={it.id}
            item={it.item}
            className={`${selected === it.id ? " selected" : ""}${hovered === it.id ? " hovered" : ""}`}
            onMouseEnter={(ev) => {
              ev.stopPropagation();
              setHovered(it.id);
            }}
            onMouseLeave={() => setHovered(null)}
            onClick={(ev) => {
              ev.stopPropagation();
              setSelected((s) => (s === it.id ? null : it.id));
            }}
          />
        ))}
      </div>
    </div>
  );
}
