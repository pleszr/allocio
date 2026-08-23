import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { CurrencyCode } from "../api/types";

// Currency display context. Money is rendered in ~49 places across 6 screens; threading a
// `currency` prop through every screen and child would be noisy and error-prone, so instead the
// chosen display currency lives in a Context and any component reads it with one `useCurrency()`
// call. This is display-only relabeling: the same number, grouping, and decimals as before — only
// the symbol and its position change. There is no FX conversion (single-currency MVP).

interface CurrencyMeta {
  symbol: string;
  position: "prefix" | "suffix";
}

// Relabel map: symbol + placement per currency. HUF suffixes "Ft"; EUR/USD prefix their glyph.
const CURRENCY_META: Record<CurrencyCode, CurrencyMeta> = {
  HUF: { symbol: "Ft", position: "suffix" },
  EUR: { symbol: "€", position: "prefix" },
  USD: { symbol: "$", position: "prefix" },
};

export interface MoneyOptions {
  // Decimal places to show; preserve each call site's existing count (0 or 2, sometimes 3).
  decimals?: number;
  // When true, prefix a non-negative value with "+". Negatives always show the "−" glyph.
  sign?: boolean;
}

// A formatter bound to the current display currency. Mirrors the old `fmtMoney` number handling
// (grouped `toLocaleString`, "−" for negatives, optional "+") but with a currency-aware symbol.
export type MoneyFormatter = (n: number, opts?: MoneyOptions) => string;

const CurrencyContext = createContext<CurrencyCode | null>(null);

export function CurrencyProvider({ currency, children }: { currency: CurrencyCode; children: ReactNode }) {
  return <CurrencyContext.Provider value={currency}>{children}</CurrencyContext.Provider>;
}

// Returns a `fmt(n, opts)` bound to the current currency. Throws when used outside a
// `CurrencyProvider` — a common React mistake worth guarding with a clear message.
export function useCurrency(): MoneyFormatter {
  const currency = useContext(CurrencyContext);
  if (currency === null) {
    throw new Error("useCurrency() must be used inside a <CurrencyProvider>.");
  }
  return useMemo(() => makeFormatter(currency), [currency]);
}

// Returns the raw current `CurrencyCode` (not a formatter) — for callers that need to pick the
// matching entry out of a per-currency value (e.g. a template catalog row's `amounts` map).
export function useCurrencyCode(): CurrencyCode {
  const currency = useContext(CurrencyContext);
  if (currency === null) {
    throw new Error("useCurrencyCode() must be used inside a <CurrencyProvider>.");
  }
  return currency;
}

// Returns just the glyph + placement (e.g. for a money `<input>`'s prefix/suffix label), without
// formatting a specific number.
export function useCurrencySymbol(): CurrencyMeta {
  const currency = useContext(CurrencyContext);
  if (currency === null) {
    throw new Error("useCurrencySymbol() must be used inside a <CurrencyProvider>.");
  }
  return CURRENCY_META[currency];
}

function makeFormatter(currency: CurrencyCode): MoneyFormatter {
  const { symbol, position } = CURRENCY_META[currency];
  return (n, opts = {}) => {
    const { decimals = 2, sign = false } = opts;
    const abs = Math.abs(n).toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    const signGlyph = n < 0 ? "−" : sign ? "+" : "";
    const body = position === "prefix" ? `${symbol}${abs}` : `${abs} ${symbol}`;
    return `${signGlyph}${body}`;
  };
}
