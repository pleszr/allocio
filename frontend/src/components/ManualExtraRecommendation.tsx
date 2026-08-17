import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../api/client";
import { useCurrency } from "../utils/currency";
import { isManualExtraRecommendationApplied, markManualExtraRecommendationApplied } from "../utils/manualExtraRecommendation";

interface ManualExtraRecommendationProps {
  assetId: string;
  current: number;
  recommended: number;
  onApplied: () => void;
  renderTrigger: (props: { ref: React.Ref<HTMLButtonElement>; onClick: () => void }) => React.ReactNode;
}

interface Snapshot {
  current: number;
  recommended: number;
  target: number;
  top: number;
  left: number;
}

// Shared "apply the recommended manual-extra top-up" trigger + confirm popover, used by both the
// Dashboard KPI hint and the Costs screen's manual-extra editor. `recommended` is a delta on top of
// `current` (see asset_detail_service.py's `_manual_extra_recommendation`), so the applied value is
// their sum, not a replacement — the popover spells that breakdown out before saving.
//
// The current/recommended/target shown and saved are frozen into a snapshot at the moment the
// popover opens, rather than recomputed from live props at save time, so what the user confirms is
// exactly what gets written. After a successful save, the applied `recommended` value is remembered
// (see manualExtraRecommendation.ts) and the trigger stops rendering — `recommended` is a snapshot
// of past history that won't shrink just because `current` went up, so re-showing it after it's been
// acted on would let a user click it again and add the same delta a second time.
export function ManualExtraRecommendation({
  assetId,
  current,
  recommended,
  onApplied,
  renderTrigger,
}: ManualExtraRecommendationProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const open = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setSnapshot({ current, recommended, target: current + recommended, top: rect.bottom + 8, left: rect.left });
    setError(null);
  };

  const confirm = async () => {
    if (!snapshot) return;
    setBusy(true);
    setError(null);
    try {
      await api.updateManualExtra(assetId, snapshot.target);
      markManualExtraRecommendationApplied(assetId, snapshot.recommended);
      setSnapshot(null);
      onApplied();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("costs.save_failed"));
    } finally {
      setBusy(false);
    }
  };

  // Click-outside/Escape to dismiss. The popover is portaled to <body> (below) so containment must
  // be checked against both the trigger and the portaled popover node, not a shared DOM ancestor.
  useEffect(() => {
    if (!snapshot) return;
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!triggerRef.current?.contains(target) && !popoverRef.current?.contains(target)) {
        setSnapshot(null);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSnapshot(null);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [snapshot]);

  if (isManualExtraRecommendationApplied(assetId, recommended)) return null;

  return (
    <>
      {renderTrigger({ ref: triggerRef, onClick: open })}
      {snapshot &&
        createPortal(
          <div
            ref={popoverRef}
            className="confirm-popover"
            style={{ position: "fixed", top: snapshot.top, left: snapshot.left }}
          >
            <div className="confirm-popover-title">
              {t("costs.manual_extra_confirm_title", { target: fmt(snapshot.target, { decimals: 0 }) })}
            </div>
            <div className="confirm-popover-breakdown">
              {t("costs.manual_extra_confirm_breakdown", {
                current: fmt(snapshot.current, { decimals: 0 }),
                recommended: fmt(snapshot.recommended, { decimals: 0 }),
              })}
            </div>
            {error && <div className="confirm-popover-error">{error}</div>}
            <div className="confirm-popover-actions">
              <button className="btn btn-sm" disabled={busy} onClick={() => setSnapshot(null)}>
                {t("costs.cancel")}
              </button>
              <button className="btn btn-sm btn-primary" disabled={busy} onClick={confirm}>
                {busy ? "…" : t("costs.confirm")}
              </button>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
