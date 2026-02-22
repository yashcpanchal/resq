import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Linearly interpolate between two RGB colors. */
function lerpRgb(
  [r1, g1, b1]: [number, number, number],
  [r2, g2, b2]: [number, number, number],
  t: number,
): string {
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

// Color anchors
const YELLOW: [number, number, number] = [255, 220, 50];
const RED: [number, number, number] = [220, 38, 38];
const GREEN: [number, number, number] = [34, 197, 94];
const DARK_GREEN: [number, number, number] = [5, 80, 20];

/**
 * Maps a scaled funding score to a color.
 *
 * Scores have already been multiplied by -10,000:
 *   negative  → underfunded → yellow (near 0) to red (most negative)
 *   positive  → well-funded → green  (near 0) to dark green (most positive)
 *
 * `domain` is [min, max] of the dataset so colours spread evenly.
 */
export function scoreToColor(
  score: number,
  domain: [number, number] = [-1, 1],
): string {
  const [lo, hi] = domain;
  if (score < 0) {
    // Underfunded half: 0 → yellow, min → red
    const t = lo < 0 ? Math.min(score / lo, 1) : 0; // 0..1 where 1 = most negative
    return lerpRgb(YELLOW, RED, t);
  }
  // Well-funded half: 0 → green, max → dark green
  const t = hi > 0 ? Math.min(score / hi, 1) : 0;
  return lerpRgb(GREEN, DARK_GREEN, t);
}

/** Same color at reduced alpha for polygon sides. */
export function scoreToSideColor(
  score: number,
  domain: [number, number] = [-1, 1],
): string {
  const base = scoreToColor(score, domain);
  return base.replace("rgb(", "rgba(").replace(")", ", 0.25)");
}
