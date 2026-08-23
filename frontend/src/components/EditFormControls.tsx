import { useTranslation } from "react-i18next";
import { useCurrencySymbol } from "../utils/currency";

export function LabeledMoney({
  label,
  value,
  onChange,
  step,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  step?: string;
}) {
  const { symbol, position } = useCurrencySymbol();
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <div className="input-prefix-wrap">
        {position === "prefix" && <span className="input-prefix">{symbol}</span>}
        <input className="input mono" type="number" step={step} value={value} onChange={(e) => onChange(e.target.value)} />
        {position === "suffix" && <span className="input-suffix">{symbol}</span>}
      </div>
    </div>
  );
}

export function EditActions({
  busy,
  disabled,
  onCancel,
  onSave,
  saveLabel,
}: {
  busy: boolean;
  disabled?: boolean;
  onCancel: () => void;
  onSave: () => void;
  saveLabel?: string;
}) {
  const { t } = useTranslation();
  return (
    <div style={{ display: "flex", gap: 8 }}>
      <button className="btn btn-sm" onClick={onCancel}>
        {t("costs.cancel")}
      </button>
      <button className="btn btn-primary btn-sm" disabled={busy || disabled} onClick={onSave}>
        {busy ? "…" : (saveLabel ?? t("costs.save"))}
      </button>
    </div>
  );
}
