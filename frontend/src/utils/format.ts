// Formatting + small domain helpers shared across screens.
//
// Money rendering lives in `utils/currency.tsx` (the `useCurrency()` hook), which owns the
// currency symbol and its placement. This module keeps only currency-agnostic number/date helpers;
// there is intentionally no `fmtMoney` here so a second, divergent money formatter can't drift.

export function fmtNumber(n: number, decimals = 0): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function fmtDateShort(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function fmtMonthYear(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

export function daysBetween(aIso: string, bIso: string): number {
  return Math.round((new Date(bIso).getTime() - new Date(aIso).getTime()) / 86400000);
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

// Approximate days for a time-based interval so we can show a per-day equivalent.
export function intervalDays(value: number, unit: "months" | "years"): number {
  return value * (unit === "years" ? 365 : 30);
}

// MOCK — the backend intentionally omits allocation cadence (see GitHub issue).
// Until a real cadence lands, the dashboard treats allocations as landing on the
// 1st of each month. This is a placeholder, not a backend-derived value.
export function mockNextAllocation(): { dateIso: string; daysUntil: number } {
  const now = new Date();
  const next = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  const daysUntil = Math.max(0, Math.round((next.getTime() - now.getTime()) / 86400000));
  return { dateIso: next.toISOString().slice(0, 10), daysUntil };
}
