import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useCurrency } from "../utils/currency";
import { useMutation } from "../utils/useMutation";
import { EditActions, LabeledMoney } from "./EditFormControls";
import { ManualExtraRecommendation } from "./ManualExtraRecommendation";

interface ManualExtraEditorProps {
  assetId: string;
  current: number;
  recommended: number;
  averageAllocation: number | null;
  averageActualCost: number;
  onClose: () => void;
  onChanged: () => void;
}

// Free-form manual-extra editor plus its "apply the recommendation" quick action. Formerly lived on
// the Costs screen; now opened inline (via a pencil trigger) from the Dashboard, since manual extra
// is a dashboard-level decision — the required-allocation figure on the Costs screen already folds
// in whatever value is saved here.
export function ManualExtraEditor({
  assetId,
  current,
  recommended,
  averageAllocation,
  averageActualCost,
  onClose,
  onChanged,
}: ManualExtraEditorProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [amount, setAmount] = useState(String(current));
  const { error, busy, run } = useMutation(onChanged);

  const save = () => run(() => api.updateManualExtra(assetId, Number(amount)), onClose);

  return (
    <div className="card card-pad" style={{ marginBottom: 20, background: "var(--surface-sunk)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 24, flexWrap: "wrap" }}>
        <div style={{ maxWidth: 380 }}>
          <div className="card-title" style={{ marginBottom: 6 }}>
            {t("costs.manual_extra_panel_title")}
          </div>
          <div className="muted" style={{ fontSize: 12.5, lineHeight: 1.5, marginBottom: 12 }}>
            {t("costs.manual_extra_panel_desc")}
          </div>
          <LabeledMoney label={t("costs.field_extra_per_month")} value={amount} onChange={setAmount} />
        </div>
        {recommended > 0 && (
          <div style={{ minWidth: 240, borderLeft: "1px solid var(--line)", paddingLeft: 24 }}>
            <div className="card-title" style={{ marginBottom: 6 }}>
              {t("costs.manual_extra_recommendation_title")}
            </div>
            {averageAllocation !== null && (
              <div className="muted" style={{ fontSize: 12.5, lineHeight: 1.6 }}>
                <div>{t("dashboard.extra_context_allocation", { amount: fmt(averageAllocation, { decimals: 0 }) })}</div>
                <div>{t("dashboard.extra_context_cost", { amount: fmt(averageActualCost, { decimals: 0 }) })}</div>
              </div>
            )}
            <div style={{ marginTop: 10, display: "flex", alignItems: "baseline", gap: 8 }}>
              <span className="num-md">
                {fmt(recommended, { decimals: 0 })}
                <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
                  {t("costs.per_mo")}
                </span>
              </span>
              <ManualExtraRecommendation
                assetId={assetId}
                current={current}
                recommended={recommended}
                onApplied={() => {
                  onChanged();
                  onClose();
                }}
                renderTrigger={({ ref, onClick }) => (
                  <button ref={ref} className="btn btn-sm btn-primary" onClick={onClick}>
                    {t("costs.use_this")}
                  </button>
                )}
              />
            </div>
          </div>
        )}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <EditActions busy={busy} onCancel={onClose} onSave={save} />
      </div>
      {error && (
        <div className="error-banner" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
    </div>
  );
}
