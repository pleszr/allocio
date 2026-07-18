import type { AssetSummary, WorkspaceOverview } from "../api/types";
import { Icon } from "../components/Icon";
import { Illo } from "../components/Illustrations";
import { illoBg, illoKind } from "../utils/assetType";
import { fmtNumber } from "../utils/format";
import { healthBand } from "../utils/health";

interface HomeScreenProps {
  overview: WorkspaceOverview;
  onOpenAsset: (id: string) => void;
  onNew: () => void;
}

export function HomeScreen({ overview, onOpenAsset, onNew }: HomeScreenProps) {
  const { assets, totals } = overview;
  const underfunded = assets.filter((a) => a.health === "underfunded");

  return (
    <div className="content fade-in">
      <div className="section-head">
        <div>
          <h1 className="h1">Your buckets</h1>
          <div className="muted" style={{ marginTop: 6, fontSize: 14 }}>
            {assets.length > 0
              ? `${assets.length} tracked ${assets.length === 1 ? "item" : "items"} — here's how they're doing today.`
              : "Set up your first tracked item and Allocio will smooth its costs into a steady monthly allocation."}
          </div>
        </div>
        <button className="btn btn-primary" onClick={onNew}>
          <Icon name="plus" size={14} /> New bucket
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
          Add a new bucket
        </button>
      </div>

      {assets.length > 0 && (
        <>
          <div className="section-head">
            <h2 className="h2">Monthly overview</h2>
          </div>
          <div className="summary">
            <div className="summary-cell">
              <div className="summary-label">Total to allocate</div>
              <div className="num-lg">${fmtNumber(totals.total_recommended_monthly_allocation)}</div>
              <div className="row-meta" style={{ marginTop: 4 }}>
                recommended across all buckets
              </div>
            </div>
            <div className="summary-cell">
              <div className="summary-label">Combined balance</div>
              <div className="num-lg">${fmtNumber(totals.total_balance)}</div>
              <div className="row-meta" style={{ marginTop: 4 }}>
                across {assets.length} {assets.length === 1 ? "bucket" : "buckets"}
              </div>
            </div>
            <div className="summary-cell">
              <div className="summary-label">Alerts</div>
              {totals.alert_count > 0 ? (
                <>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
                    <span className="band-icon" style={{ background: "var(--bad)", width: 26, height: 26 }}>
                      <Icon name="alert" size={14} stroke={2.4} />
                    </span>
                    <span className="num-md" style={{ color: "var(--bad)" }}>
                      {totals.alert_count} {totals.alert_count === 1 ? "issue" : "issues"}
                    </span>
                  </div>
                  <div className="row-meta" style={{ marginTop: 6 }}>
                    {underfunded.length === 1
                      ? `${underfunded[0].name} is underfunded`
                      : `${totals.alert_count} buckets are underfunded`}
                  </div>
                </>
              ) : (
                <>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
                    <span className="band-icon" style={{ background: "var(--good)", width: 26, height: 26 }}>
                      <Icon name="check" size={14} stroke={2.4} />
                    </span>
                    <span className="num-md" style={{ color: "var(--good)" }}>
                      All clear
                    </span>
                  </div>
                  <div className="row-meta" style={{ marginTop: 6 }}>
                    Every bucket is on track
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
            <span className="bucket-row-label">Balance</span>
            <span className="bucket-row-val">${fmtNumber(asset.balance, decimals)}</span>
          </div>
          <div className="bucket-row">
            <span className="bucket-row-label">Next allocation</span>
            <span className="bucket-row-val">${fmtNumber(asset.recommended_monthly_allocation)}</span>
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
