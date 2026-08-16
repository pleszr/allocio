import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { MaintenanceItem, MaintenanceStatus } from "../api/types";
import { fmtNumber } from "../utils/format";
import { Icon, type IconName } from "./Icon";
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

// Which glyph represents each built-in maintenance technical_key. A custom row (technical_key
// null) or any key not listed here falls back to a generic wrench.
const MAINT_ICON_BY_KEY: Record<string, IconName> = {
  annual_service: "calendar",
  timing_system: "gear",
  water_pump: "droplet",
  battery: "battery",
  automatic_transmission_fluid: "droplet",
  fuel_filter: "droplet",
  front_brake_pad: "padBrake",
  front_brake_disc: "discBrake",
  rear_brake_pad: "padBrake",
  rear_brake_disc: "discBrake",
  all_season_tires: "tire",
  winter_tires: "tire",
  summer_tires: "tire",
};

export function maintenanceIcon(item: MaintenanceItem): IconName {
  if (item.technical_key !== null) {
    const icon = MAINT_ICON_BY_KEY[item.technical_key];
    if (icon) return icon;
  }
  return "wrench";
}

// The worse of an item's two progress ratios — the one driving the combined bar's fill and
// colour, and the sort order (most-overdue first). Null when neither dimension has an interval
// and a service anchor to measure from.
export function maintenanceRatio(item: MaintenanceItem): number | null {
  if (item.km_progress === null && item.month_progress === null) return null;
  return Math.max(item.km_progress ?? -Infinity, item.month_progress ?? -Infinity);
}

function statusRank(status: MaintenanceStatus | null): number {
  if (status === "overdue") return 0;
  if (status === "due") return 1;
  if (status === "soon") return 2;
  if (status === "ok") return 3;
  return 4;
}

// Most urgent first: overdue, then due, then soon, then ok, each group ordered by how close to
// (or past) its interval the item is. Items without a ratio sort last within their group.
export function sortByUrgency(items: MaintenanceItem[]): MaintenanceItem[] {
  return [...items].sort((a, b) => {
    const rankDiff = statusRank(a.status) - statusRank(b.status);
    if (rankDiff !== 0) return rankDiff;
    const ratioA = maintenanceRatio(a) ?? -Infinity;
    const ratioB = maintenanceRatio(b) ?? -Infinity;
    if (ratioA !== ratioB) return ratioB - ratioA;
    return a.label.localeCompare(b.label);
  });
}

export type MaintenanceFilter = "all" | "good" | "attention" | "overdue";

export function matchesMaintenanceFilter(item: MaintenanceItem, filter: MaintenanceFilter): boolean {
  if (filter === "all") return true;
  if (filter === "overdue") return item.status === "overdue";
  if (filter === "attention") return item.status === "due" || item.status === "soon";
  return item.status === "ok" || item.status === null;
}

// The remaining-figure text for a card's meta line or the talk-box: just the overdue word once
// an item is past due (a negative "remaining" reads as nonsense), otherwise every dimension that
// has a figure, joined.
export function maintenanceRemainingText(item: MaintenanceItem, t: TFunction): string {
  if (item.status === "overdue") return t("spatialMap.overdue");
  const parts: string[] = [];
  if (item.remaining_km !== null) parts.push(t("spatialMap.km_left", { km: fmtNumber(item.remaining_km) }));
  if (item.remaining_months !== null) parts.push(t("spatialMap.months_left", { months: item.remaining_months }));
  return parts.join(" · ");
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

// Fixed 0-100 overlay-space anchor the talk-box's connecting line starts from — chosen to sit
// roughly at the box's own bottom-right corner given its fixed top/left CSS position, so the line
// reads as coming out of the box rather than floating independently.
const TALKBOX_ANCHOR = { x: 19, y: 22 };

// The car x-ray with the glowing region overlay and the hover/selection talk-box, driven by an
// externally-controlled `focusItem`. Shared by SpatialMap (Costs screen, with its own list) and
// MaintenancePanel (dashboard, with the unified maintenance list). `items` are the mapped rows
// only — the ones that have a car region; `focusItem` may be any maintenance item, mapped or not,
// so the talk-box still shows info for an unmapped hover, just without a connecting line.
export function CarDiagram({ items, focusItem }: { items: SpatialItem[]; focusItem: MaintenanceItem | null }) {
  const { t } = useTranslation();
  const activeItem = focusItem ? items.find((i) => i.id === focusItem.id) : undefined;
  const activeId = activeItem?.id ?? null;
  const region = activeItem?.regions[0] ?? null;
  const tone = focusItem ? dotClass(focusItem.status) : null;

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
        {region && (
          <g className={`spatial-line ${tone ?? ""}`}>
            <line x1={TALKBOX_ANCHOR.x} y1={TALKBOX_ANCHOR.y} x2={region.cx} y2={region.cy} />
            <circle cx={region.cx} cy={region.cy} r={1.2} />
          </g>
        )}
      </svg>
      <div className={`maint-talkbox${tone ? ` ${tone}` : ""}`}>
        {focusItem ? (
          <>
            <div className="maint-talkbox-head">
              <span className={`maint-talkbox-icon ${tone}`}>
                <Icon name={maintenanceIcon(focusItem)} size={16} />
              </span>
              <span className="maint-talkbox-name">{focusItem.label}</span>
              {focusItem.status === "overdue" && <span className="maint-talkbox-badge">{t("spatialMap.overdue")}</span>}
            </div>
            {focusItem.status !== "overdue" && (
              <div className="maint-talkbox-meta">{maintenanceRemainingText(focusItem, t)}</div>
            )}
          </>
        ) : (
          <div className="maint-talkbox-hint">{t("spatialMap.focus_hint")}</div>
        )}
      </div>
    </div>
  );
}

interface MaintenanceFilterTabsProps {
  value: MaintenanceFilter;
  onChange: (filter: MaintenanceFilter) => void;
}

// The All / Good / Attention / Overdue tabs shared by both maintenance lists.
export function MaintenanceFilterTabs({ value, onChange }: MaintenanceFilterTabsProps) {
  const { t } = useTranslation();
  const tabs: { key: MaintenanceFilter; label: string; dot?: string }[] = [
    { key: "all", label: t("spatialMap.filter_all") },
    { key: "good", label: t("spatialMap.filter_good"), dot: "good" },
    { key: "attention", label: t("spatialMap.filter_attention"), dot: "warn" },
    { key: "overdue", label: t("spatialMap.filter_overdue"), dot: "bad" },
  ];
  return (
    <div className="maint-filter-tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={value === tab.key}
          className={`maint-filter-tab${value === tab.key ? " active" : ""}`}
          onClick={() => onChange(tab.key)}
        >
          {tab.dot && <span className={`maint-filter-dot ${tab.dot}`} />}
          {tab.label}
        </button>
      ))}
    </div>
  );
}

interface MaintenanceCardProps extends React.HTMLAttributes<HTMLDivElement> {
  item: MaintenanceItem;
}

// One maintenance item as a card: type icon, name, a single urgency bar (driven by the worse of
// its two progress ratios), and the remaining-figure meta line. Owns only the visual structure —
// each parent spreads whatever interaction props it needs (click-to-open-history vs.
// click-to-select, hover, keyboard) onto the same shape.
export function MaintenanceCard({ item, className, ...rowProps }: MaintenanceCardProps) {
  const { t } = useTranslation();
  const tone = dotClass(item.status);
  const ratio = maintenanceRatio(item);
  const pct = ratio !== null ? Math.round(Math.min(1, ratio) * 100) : null;

  return (
    <div className={`maint-card${className ?? ""}`} {...rowProps}>
      <span className={`maint-card-dot ${tone}`} />
      <span className={`maint-card-icon ${tone}`}>
        <Icon name={maintenanceIcon(item)} size={16} />
      </span>
      <span className="maint-card-body">
        <span className="maint-card-head">
          <span className="maint-card-name">{item.label}</span>
          {pct !== null && <span className={`maint-card-pct ${tone}`}>{pct}%</span>}
        </span>
        {pct !== null && (
          <span className="bar-track">
            <span className={`bar-fill ${tone}`} style={{ ["--pct" as string]: `${pct}%` }} />
          </span>
        )}
        {pct !== null && (
          <span className="maint-card-meta">
            {item.status === "overdue" ? (
              <span className="maint-card-meta-item bad">{t("spatialMap.overdue")}</span>
            ) : (
              <>
                {item.remaining_km !== null && (
                  <span className="maint-card-meta-item">
                    <Icon name="odometer" size={11} />
                    {t("spatialMap.km_left", { km: fmtNumber(item.remaining_km) })}
                  </span>
                )}
                {item.remaining_months !== null && (
                  <span className="maint-card-meta-item">
                    <Icon name="clock" size={11} />
                    {t("spatialMap.months_left", { months: item.remaining_months })}
                  </span>
                )}
              </>
            )}
          </span>
        )}
      </span>
      <Icon name="chevronRight" size={14} className="maint-card-chevron" />
    </div>
  );
}

interface SpatialMapProps {
  maintenanceItems: MaintenanceItem[];
}

export function SpatialMap({ maintenanceItems }: SpatialMapProps) {
  const items = useMemo(() => spatialItems(maintenanceItems), [maintenanceItems]);
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<MaintenanceFilter>("all");
  const activeId = hovered ?? selected;
  const active = items.find((i) => i.id === activeId);
  const filteredSorted = useMemo(
    () => sortByUrgency(items.map((i) => i.item).filter((it) => matchesMaintenanceFilter(it, filter))),
    [items, filter],
  );

  if (items.length === 0) return null;

  return (
    <div className="spatial-map" onClick={() => setSelected(null)}>
      <div className="spatial-stage">
        <CarDiagram items={items} focusItem={active?.item ?? null} />
      </div>
      <div className="spatial-list-wrap">
        <div className="spatial-list-head">
          <MaintenanceFilterTabs value={filter} onChange={setFilter} />
        </div>
        <div className="spatial-list">
          {filteredSorted.map((it) => (
            <MaintenanceCard
              key={it.id}
              item={it}
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
    </div>
  );
}
