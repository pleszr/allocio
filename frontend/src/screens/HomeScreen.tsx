import { useTranslation } from "react-i18next";
import type { AssetSummary, WorkspaceOverview } from "../api/types";
import { Icon } from "../components/Icon";
import { Illo } from "../components/Illustrations";
import { illoBg, illoKind } from "../utils/assetType";
import { useCurrency } from "../utils/currency";
import { healthBand } from "../utils/health";

interface HomeScreenProps {
  overview: WorkspaceOverview;
  onOpenAsset: (id: string) => void;
  onNew: () => void;
}

export function HomeScreen({ overview, onOpenAsset, onNew }: HomeScreenProps) {
  const { t } = useTranslation();
  const { assets, totals } = overview;
  const fmt = useCurrency();
  const underfunded = assets.filter((a) => a.health === "underfunded");

  return (
    <div className="content fade-in">
      <div className="section-head">
        <div>
          <h1 className="h1">{t("home.title")}</h1>
          <div className="muted" style={{ marginTop: 6, fontSize: 14 }}>
            {assets.length > 0
              ? t("home.subtitle", { count: assets.length })
              : t("home.subtitle_empty")}
          </div>
        </div>
        <button className="btn btn-primary" onClick={onNew}>
          <Icon name="plus" size={14} /> {t("home.new_bucket")}
        </button>
      </div>

      <div className="bucket-grid" style={{ marginBottom: 36 }}>
        {assets.map((a) => (
          <BucketCard key={a.id} asset={a} onOpen={() => onOpenAsset(a.id)} />
        ))}
        <button className="bucket-add" onClick={onNew}>
          <span className="bucket-add-icon">
            <Icon name="plus" size={20} stroke={2} />
          </span>
          {t("home.add_bucket")}
        </button>
      </div>

      {assets.length > 0 && (
        <>
          <div className="section-head">
            <h2 className="h2">{t("home.monthly_overview")}</h2>
          </div>
          <div className="summary">
            <div className="summary-cell">
              <div className="summary-label">{t("home.total_to_allocate")}</div>
              <div className="num-lg">{fmt(totals.total_recommended_monthly_allocation, { decimals: 0 })}</div>
              <div className="row-meta" style={{ marginTop: 4 }}>
                {t("home.recommended_across")}
              </div>
            </div>
            <div className="summary-cell">
              <div className="summary-label">{t("home.combined_balance")}</div>
              <div className="num-lg">{fmt(totals.total_balance, { decimals: 0 })}</div>
              <div className="row-meta" style={{ marginTop: 4 }}>
                {t("home.across_buckets", { count: assets.length })}
              </div>
            </div>
            <div className="summary-cell">
              <div className="summary-label">{t("home.alerts")}</div>
              {totals.alert_count > 0 ? (
                <>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
                    <span className="band-icon" style={{ background: "var(--bad)", width: 26, height: 26 }}>
                      <Icon name="alert" size={14} stroke={2.4} />
                    </span>
                    <span className="num-md" style={{ color: "var(--bad)" }}>
                      {t("home.issues", { count: totals.alert_count })}
                    </span>
                  </div>
                  <div className="row-meta" style={{ marginTop: 6 }}>
                    {underfunded.length === 1
                      ? t("home.underfunded_one", { name: underfunded[0].name })
                      : t("home.underfunded_many", { n: totals.alert_count })}
                  </div>
                </>
              ) : (
                <>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
                    <span className="band-icon" style={{ background: "var(--good)", width: 26, height: 26 }}>
                      <Icon name="check" size={14} stroke={2.4} />
                    </span>
                    <span className="num-md" style={{ color: "var(--good)" }}>
                      {t("home.all_clear")}
                    </span>
                  </div>
                  <div className="row-meta" style={{ marginTop: 6 }}>
                    {t("home.all_on_track")}
                  </div>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function BucketCard({ asset, onOpen }: { asset: AssetSummary; onOpen: () => void }) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const kind = illoKind(asset.type);
  const band = healthBand(asset.health);
  const decimals = asset.balance < 1000 ? 2 : 0;

  return (
    <div className="bucket-card" onClick={onOpen}>
      <div className="bucket-illo" style={{ background: illoBg(kind) }}>
        <Illo kind={kind} />
      </div>
      <div className="bucket-body">
        <div>
          <div className="bucket-name">{asset.name}</div>
          <div className="bucket-sub">{asset.subtitle ?? asset.type}</div>
        </div>
        <div className="bucket-stats">
          <div className="bucket-row">
            <span className="bucket-row-label">{t("home.balance")}</span>
            <span className="bucket-row-val">{fmt(asset.balance, { decimals })}</span>
          </div>
          <div className="bucket-row">
            <span className="bucket-row-label">{t("home.next_allocation")}</span>
            <span className="bucket-row-val">{fmt(asset.recommended_monthly_allocation, { decimals: 0 })}</span>
          </div>
        </div>
      </div>
      <div className={`bucket-band ${band.cls}`}>
        <span className="band-icon">
          <Icon name={band.icon} size={12} stroke={2.6} />
        </span>
        {band.label}
      </div>
    </div>
  );
}
