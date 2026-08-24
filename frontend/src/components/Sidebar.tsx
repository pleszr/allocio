import { useTranslation } from "react-i18next";
import type { AssetSummary, CurrentUser, UserSettings } from "../api/types";
import { illoKind } from "../utils/assetType";
import { useCurrency } from "../utils/currency";
import type { Route } from "../routes";
import { Icon } from "./Icon";
import { UserMenu } from "./UserMenu";

interface SidebarProps {
  assets: AssetSummary[];
  route: Route;
  onNavigate: (route: Route) => void;
  user: CurrentUser;
  settings: UserSettings;
  onSettingsSaved: (next: UserSettings) => void;
}

export function Sidebar({ assets, route, onNavigate, user, settings, onSettingsSaved }: SidebarProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
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
        <div className="side-section-label">{t("sidebar.workspace")}</div>
        <div className="side-nav">
          <button className="side-item" aria-current={onOverview} onClick={() => onNavigate({ kind: "home" })}>
            <Icon name="home" className="side-item-icon" /> {t("sidebar.overview")}
          </button>
          <button
            className="side-item"
            aria-current={onCheckin}
            disabled={!checkinTarget}
            onClick={() => checkinTarget && onNavigate({ kind: "asset", assetId: checkinTarget, tab: "checkin" })}
          >
            <Icon name="calendar" className="side-item-icon" /> {t("sidebar.monthly_checkin")}
          </button>
        </div>
      </div>

      <div className="side-entities-section">
        <div className="side-section-label">{t("sidebar.tracked_items")}</div>
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
              <span className="entity-balance">{fmt(a.balance)}</span>
            </button>
          ))}
          <button className="side-item" onClick={() => onNavigate({ kind: "new" })}>
            <Icon name="plus" className="side-item-icon" /> {t("sidebar.add_item")}
          </button>
        </div>
      </div>

      <div className="sidebar-footer">
        <div className="avatar">{initials(user)}</div>
        <UserMenu user={user} settings={settings} onSettingsSaved={onSettingsSaved} />
      </div>
    </aside>
  );
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
