import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Unit scale factors - maps unit types to their multiplier to get base values.
 * For example, "millions_usd" means the raw value is in millions, so multiply by 1e6 to get dollars.
 */
export const UNIT_SCALES: Record<string, number> = {
  millions_usd: 1e6,
  millions_eur: 1e6,
  millions_gbp: 1e6,
  millions_jpy: 1e6,
  billions_usd: 1e9,
  billions_eur: 1e9,
  // Index/percent/rate values don't need scaling
  percent: 1,
  index: 1,
  percent_gdp: 1,
  local_currency: 1,  // BIS data - already normalized
};

/**
 * Format a currency value with appropriate suffix (K, M, B, T).
 * Expects values in base currency (e.g., dollars, not millions of dollars).
 *
 * @param value - The value in base currency
 * @param decimals - Number of decimal places (default 2)
 * @param prefix - Currency prefix (default "$")
 */
export function formatCurrency(value: number, decimals: number = 2, prefix: string = "$"): string {
  const absValue = Math.abs(value);
  const sign = value < 0 ? "-" : "";

  if (absValue >= 1e12) return `${sign}${prefix}${(absValue / 1e12).toFixed(decimals)}T`;
  if (absValue >= 1e9) return `${sign}${prefix}${(absValue / 1e9).toFixed(decimals)}B`;
  if (absValue >= 1e6) return `${sign}${prefix}${(absValue / 1e6).toFixed(decimals)}M`;
  if (absValue >= 1e3) return `${sign}${prefix}${(absValue / 1e3).toFixed(decimals)}K`;
  return `${sign}${prefix}${absValue.toLocaleString(undefined, { maximumFractionDigits: decimals })}`;
}
