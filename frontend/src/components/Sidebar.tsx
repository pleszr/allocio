import type { AssetSummary } from "../api/types";
import { illoKind } from "../utils/assetType";
import { fmtNumber } from "../utils/format";
import type { Route } from "../routes";
import { Icon } from "./Icon";

interface SidebarProps {
  assets: AssetSummary[];
  route: Route;
  onNavigate: (route: Route) => void;
}

export function Sidebar({ assets, route, onNavigate }: SidebarProps) {
  const activeAssetId = route.kind === "asset" ? route.assetId : null;
  const onOverview = route.kind === "home";
  const onCheckin = route.kind === "asset" && route.tab === "checkin";
  // "Monthly check-in" opens the check-in tab of the active asset, else the first.
  const checkinTarget = activeAssetId ?? assets[0]?.id ?? null;

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">α</div>
        <div className="brand-name">allocio</div>
      </div>

      <div>
        <div className="side-section-label">Workspace</div>
        <div className="side-nav">
          <button className="side-item" aria-current={onOverview} onClick={() => onNavigate({ kind: "home" })}>
            <Icon name="home" className="side-item-icon" /> Overview
          </button>
          <button
            className="side-item"
            aria-current={onCheckin}
            disabled={!checkinTarget}
            onClick={() => checkinTarget && onNavigate({ kind: "asset", assetId: checkinTarget, tab: "checkin" })}
          >
            <Icon name="calendar" className="side-item-icon" /> Monthly check-in
          </button>
        </div>
      </div>

      <div>
        <div className="side-section-label">Tracked items</div>
        <div className="side-entities">
          {assets.map((a) => (
            <button
              key={a.id}
              className="side-entity"
              aria-current={activeAssetId === a.id && !onCheckin}
              onClick={() => onNavigate({ kind: "asset", assetId: a.id, tab: "dashboard" })}
            >
              <span className="entity-glyph">
                <Icon name={illoKind(a.type)} size={13} />
              </span>
              <span>
                <span className="entity-name">{a.name}</span>
              </span>
              <span className="entity-balance">${fmtNumber(a.balance)}</span>
            </button>
          ))}
          <button className="side-item" onClick={() => onNavigate({ kind: "new" })}>
            <Icon name="plus" className="side-item-icon" /> Add item
          </button>
        </div>
      </div>

      <div className="sidebar-footer">
        <div className="avatar">AL</div>
        <div>
          <div className="user-name">Allocio</div>
          <div className="user-email">local workspace</div>
        </div>
      </div>
    </aside>
  );
}
