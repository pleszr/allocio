// Maps a free-form backend asset `type` string onto the design's three
// illustration families. The backend type is type-agnostic (any string), so
// this is a display-only heuristic with a generic fallback.

export type IlloKind = "car" | "house" | "pet";

export function illoKind(type: string): IlloKind {
  const t = type.toLowerCase();
  if (/(vehicle|car|auto|motor|truck|van|bike)/.test(t)) return "car";
  if (/(pet|dog|cat|animal|horse)/.test(t)) return "pet";
  // House is the neutral default for property and anything unrecognized.
  return "house";
}

export function illoBg(kind: IlloKind): string {
  return kind === "car" ? "#EAF1FB" : kind === "pet" ? "#FBF1E5" : "#FBEEEC";
}

// Whether this asset tracks a usage counter (odometer-like). Drives whether the
// dashboard/check-in show usage fields.
export function tracksUsage(type: string, currentUsage: number | null): boolean {
  return currentUsage !== null || illoKind(type) === "car";
}
