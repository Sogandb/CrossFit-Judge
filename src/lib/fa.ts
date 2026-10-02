/** Persian digit/time helpers for the UI. */

const FA_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

export function toFa(value: number | string): string {
  return String(value).replace(/[0-9]/g, (d) => FA_DIGITS[Number(d)]);
}

export function faClock(totalSec: number | null | undefined): string {
  if (totalSec == null || !isFinite(totalSec)) return "—";
  const neg = totalSec < 0;
  const s = Math.abs(Math.round(totalSec));
  const mm = Math.floor(s / 60);
  const ss = s % 60;
  return (neg ? "−" : "") + toFa(`${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`);
}

export function faInt(n: number | null | undefined): string {
  if (n == null) return "—";
  return toFa(n.toLocaleString("en-US")).replace(/,/g, "٬");
}

export function faDateTime(epochSec: number): string {
  try {
    return new Intl.DateTimeFormat("fa-IR", {
      dateStyle: "short", timeStyle: "short",
    }).format(new Date(epochSec * 1000));
  } catch {
    return "—";
  }
}
