import type { ReactNode } from "react";

// Shared explicit loading / error / empty states, per the frontend rule that
// user-facing flows make each state explicit.

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state-wrap">
      <div className="spinner" />
      <div className="state-msg">{label}</div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-wrap">
      <div className="state-title">Something went wrong</div>
      <div className="state-msg">{message}</div>
      {onRetry && (
        <button className="btn btn-outline btn-sm" onClick={onRetry}>
          Try again
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
