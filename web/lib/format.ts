// Small display helpers shared by every page.

// Rupees with Indian digit grouping: 135000 -> "₹1,35,000".
export function inr(n: number | null | undefined): string {
  if (n === null || n === undefined) return "-";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

// Percentage change between two numbers, with a sign: (200000, 135000) -> "-32.5%".
export function pct(prev: number, curr: number): string {
  if (!prev) return "";
  const v = ((curr - prev) / prev) * 100;
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

// The diagnosis engine's cause keys (see agent/brain/diagnosis.py) as words for the screen.
export const CAUSE_LABEL: Record<string, string> = {
  stockouts: "Stockouts",
  pricing: "Pricing",
  service_quality: "Cancellations and service",
  traffic: "Low visibility",
};

export function causeLabel(key: string | null | undefined): string {
  return key ? CAUSE_LABEL[key] ?? key : "No decline";
}

// A timestamp as "10 Nov, 01:56 pm", always in India time whatever the server's time zone.
export function shortDate(d: string | Date | null | undefined): string {
  if (!d) return "-";
  return new Date(d).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" });
}

// "2026-11-17" -> "17 Nov"
export function day(d: string | null | undefined): string {
  if (!d) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  if (!m) return d;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(m[3])} ${months[Number(m[2]) - 1]}`;
}

// The agent sometimes reports the same step twice in a row (for example "Ended the call").
// Show it once.
export function withoutRepeats<T extends Record<string, any>>(turns: T[]): T[] {
  return turns.filter((turn, i) => !(i > 0 && turn.role === "tool" && turns[i - 1].role === "tool" && turns[i - 1].text === turn.text));
}
