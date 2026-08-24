import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useCurrency } from "../utils/currency";
import { useMutation } from "../utils/useMutation";
import { markManualExtraRecommendationApplied } from "../utils/manualExtraRecommendation";
import { EditActions, LabeledMoney } from "./EditFormControls";

interface ManualExtraEditorProps {
  assetId: string;
  current: number;
  recommended: number;
  onChanged: () => void;
  renderTrigger: (props: { ref: React.Ref<HTMLButtonElement>; onClick: () => void }) => React.ReactNode;
}

interface Snapshot {
  current: number;
  recommended: number;
  top: number;
  left: number;
}

// Free-form manual-extra editor, opened as a small popover anchored to a trigger. `recommended` is
// already the full target manual_extra_monthly should reach (average_actual_monthly_cost minus
// average_allocation, which itself excludes manual extra) — not an incremental top-up on top of
// `current` — so the amount field prefills with `recommended` directly, and accepting it is just
// hitting Save. `current`/`recommended` are frozen into a snapshot at popover-open time (mirrors the
// old ManualExtraRecommendation confirm-popover), so a save that fulfills the frozen target can be
// marked applied even if the live props haven't caught up yet.
export function ManualExtraEditor({ assetId, current, recommended, onChanged, renderTrigger }: ManualExtraEditorProps) {
  const { t } = useTranslation();
  const fmt = useCurrency();
  const [amount, setAmount] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const { error, busy, run } = useMutation(onChanged);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const open = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setAmount(recommended > 0 ? recommended.toFixed(2) : String(current));
    setSnapshot({ current, recommended, top: rect.bottom + 8, left: rect.left });
  };
  const close = () => setSnapshot(null);
  const save = () =>
    run(
      () => api.updateManualExtra(assetId, Number(amount)),
      () => {
        if (snapshot && snapshot.recommended > 0 && Number(amount) >= snapshot.recommended - 0.01) {
          markManualExtraRecommendationApplied(assetId, snapshot.recommended, snapshot.recommended);
        }
        close();
      },
    );

  useEffect(() => {
    if (!snapshot) return;
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!triggerRef.current?.contains(target) && !popoverRef.current?.contains(target)) close();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [snapshot]);

  return (
    <>
      {renderTrigger({ ref: triggerRef, onClick: open })}
      {snapshot &&
        createPortal(
          <div
            ref={popoverRef}
            className="confirm-popover"
            style={{ position: "fixed", top: snapshot.top, left: snapshot.left, width: 260 }}
          >
            <LabeledMoney label={t("costs.field_extra_per_month")} value={amount} onChange={setAmount} />
            {snapshot.recommended > 0 && (
              <div className="confirm-popover-breakdown" style={{ marginTop: 8 }}>
                {t("costs.manual_extra_recommended_context", {
                  recommended: fmt(snapshot.recommended),
                  current: fmt(snapshot.current),
                })}
              </div>
            )}
            {error && <div className="confirm-popover-error">{error}</div>}
            <div style={{ marginTop: 12 }}>
              <EditActions busy={busy} onCancel={close} onSave={save} />
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
