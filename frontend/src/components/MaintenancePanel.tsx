import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { MaintenanceItem } from "../api/types";
import {
  CarDiagram,
  MaintenanceCard,
  MaintenanceFilterTabs,
  matchesMaintenanceFilter,
  sortByUrgency,
  spatialItems,
  type MaintenanceFilter,
} from "./SpatialMap";
import { Icon } from "./Icon";

interface MaintenancePanelProps {
  // The asset's active maintenance items (the dashboard already filters on is_active).
  maintenanceItems: MaintenanceItem[];
  // Navigate to the Costs → maintenance tab.
  onManage: () => void;
  // Open the maintenance history popup for a clicked row.
  onOpenHistory: (item: MaintenanceItem) => void;
}

// Full-width dashboard maintenance section: the car x-ray diagram on the left and a single unified
// maintenance list on the right. Hovering a mapped row glows its car region; clicking any row (mapped
// or not) opens its history popup. When no rows map to a car region (houses, pets, custom rows) the
// list renders full width with no diagram.
export function MaintenancePanel({ maintenanceItems, onManage, onOpenHistory }: MaintenancePanelProps) {
  const { t } = useTranslation();
  const mapped = useMemo(() => spatialItems(maintenanceItems), [maintenanceItems]);
  const [hovered, setHovered] = useState<string | null>(null);
  const [filter, setFilter] = useState<MaintenanceFilter>("all");
  const filteredSorted = useMemo(
    () => sortByUrgency(maintenanceItems.filter((it) => matchesMaintenanceFilter(it, filter))),
    [maintenanceItems, filter],
  );

  if (maintenanceItems.length === 0) return null;

  const dueSoon = maintenanceItems.filter((m) => m.status && m.status !== "ok");
  // CarDiagram only glows a region for items present in `mapped`, so passing the raw hovered item
  // (even when unmapped) still shows the talk-box without lighting up the car.
  const hoveredItem = maintenanceItems.find((m) => m.id === hovered) ?? null;

  const list = (
    <div className="spatial-list-wrap">
      <div className="spatial-list-head">
        <MaintenanceFilterTabs value={filter} onChange={setFilter} />
      </div>
      <div className="spatial-list">
        {filteredSorted.map((m) => (
          <MaintenanceCard
            key={m.id}
            item={m}
            className={hovered === m.id ? " hovered" : ""}
            role="button"
            tabIndex={0}
            title={t("costHistory.open_hint")}
            onMouseEnter={() => setHovered(m.id)}
            onMouseLeave={() => setHovered(null)}
            onClick={() => onOpenHistory(m)}
            onKeyDown={(ev) => {
              if (ev.key === "Enter" || ev.key === " ") {
                ev.preventDefault();
                onOpenHistory(m);
              }
            }}
          />
        ))}
      </div>
    </div>
  );

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div className="card-hd">
        <div>
          <div className="card-title">{t("dashboard.maintenance")}</div>
          <div className="card-sub">
            {dueSoon.length > 0
              ? t("dashboard.items_need_attention", { count: dueSoon.length })
              : t("dashboard.everything_current")}
          </div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onManage}>
          {t("dashboard.manage")} <Icon name="chevronRight" size={12} />
        </button>
      </div>
      {mapped.length > 0 ? (
        <div className="maint-panel-body">
          <div className="maint-panel-stage">
            <CarDiagram items={mapped} focusItem={hoveredItem} />
          </div>
          {list}
        </div>
      ) : (
        list
      )}
    </div>
  );
}
