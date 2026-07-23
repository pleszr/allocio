import { api } from "../api/client";
import type { AssetSummary, CurrentUser } from "../api/types";
import { illoKind } from "../utils/assetType";
import { fmtNumber } from "../utils/format";
import type { Route } from "../routes";
import { Icon } from "./Icon";

interface SidebarProps {
  assets: AssetSummary[];
  route: Route;
  onNavigate: (route: Route) => void;
  user: CurrentUser;
}

export function Sidebar({ assets, route, onNavigate, user }: SidebarProps) {
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
        <div className="avatar">{initials(user)}</div>
        <div className="sidebar-user">
          <div className="user-name">{user.name || user.email}</div>
          <div className="user-email">{user.email}</div>
        </div>
        <button className="logout-btn" title="Sign out" onClick={logout}>
          Sign out
        </button>
      </div>
    </aside>
  );
}

// Best-effort logout: clear the session server-side, then reload so the auth gate re-checks and
// shows the sign-in screen. Reload even if the call fails — a failed logout must not trap the user.
async function logout(): Promise<void> {
  try {
    await api.logout();
  } finally {
    window.location.reload();
  }
}

// Initials from the first letters of the first two name words, uppercased; falls back to the first
// two chars of the email local-part when the name is empty.
function initials(user: CurrentUser): string {
  const words = user.name.trim().split(/\s+/).filter(Boolean);
  if (words.length > 0) {
    return words.slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  }
  return user.email.split("@")[0].slice(0, 2).toUpperCase();
}
