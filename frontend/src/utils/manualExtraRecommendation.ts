// The backend's manual-extra recommendation is a trailing-window shortfall that only shrinks once
// enough new allocations have posted — saving a value that fulfills it does not make it disappear
// on the next load. This localStorage marker remembers "the user already reached this exact
// recommended figure's target" per asset, so the UI can hide a stale recommendation instead of
// re-offering (and re-adding) the same top-up indefinitely. It self-invalidates either when the
// backend produces a different recommended amount (compared exactly), or when the live current
// amount later drops back below the target that was fulfilled — e.g. the user dials the manual
// extra back down after applying the recommendation, which should bring the banner back.
const STORAGE_KEY = "allocio.manualExtraRecommendationApplied";

interface AppliedRecord {
  recommended: number;
  target: number;
}

function readStore(): Record<string, AppliedRecord> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

export function isManualExtraRecommendationApplied(assetId: string, recommended: number, current: number): boolean {
  const record = readStore()[assetId];
  return !!record && record.recommended === recommended && current >= record.target - 0.01;
}

export function markManualExtraRecommendationApplied(assetId: string, recommended: number, target: number): void {
  const store = readStore();
  store[assetId] = { recommended, target };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}
