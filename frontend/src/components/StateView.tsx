import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

// Shared explicit loading / error / empty states, per the frontend rule that
// user-facing flows make each state explicit.

export function LoadingState({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="state-wrap">
      <div className="spinner" />
      <div className="state-msg">{label ?? t("common.loading")}</div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="state-wrap">
      <div className="state-title">{t("states.something_wrong")}</div>
      <div className="state-msg">{message}</div>
      {onRetry && (
        <button className="btn btn-outline btn-sm" onClick={onRetry}>
          {t("states.try_again")}
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, message, action }: { title: string; message: string; action?: ReactNode }) {
  return (
    <div className="state-wrap">
      <div className="state-title">{title}</div>
      <div className="state-msg">{message}</div>
      {action}
    </div>
  );
}
