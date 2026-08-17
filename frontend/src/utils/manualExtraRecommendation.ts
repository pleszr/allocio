const STORAGE_KEY_PREFIX = "allocio:manualExtraRecommendationApplied:";

// The backend's `manual_extra_recommended` (see asset_detail_service.py's
// `_manual_extra_recommendation`) is a snapshot of a historical funding gap over the trailing 365
// days — it does not shrink just because the user raises `manual_extra_monthly` today, since it's
// derived from already-posted allocation events. Once a given recommended amount has been applied,
// remember it per asset so the same stale snapshot isn't re-offered (and re-added on top) on every
// render. A future check-in period naturally produces a different recommended amount, which no
// longer matches the stored marker, so the recommendation reappears on its own.
export function isManualExtraRecommendationApplied(assetId: string, recommended: number): boolean {
  return localStorage.getItem(STORAGE_KEY_PREFIX + assetId) === String(recommended);
}

export function markManualExtraRecommendationApplied(assetId: string, recommended: number): void {
  localStorage.setItem(STORAGE_KEY_PREFIX + assetId, String(recommended));
}
