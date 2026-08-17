import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api/client";

export function useMutation(onChanged: () => void) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>, done: () => void) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      done();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("costs.save_failed"));
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, run };
}
