import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { scaleSequential } from "d3-scale";
import { interpolateRdYlGn } from "d3-scale-chromatic";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Maps a funding score (0 → 1) to a color on the Red-Yellow-Green spectrum.
 *   0.0 = deep red   (severely underfunded)
 *   0.5 = yellow     (halfway funded)
 *   1.0 = deep green (fully funded)
 */
const fundingColorScale = scaleSequential(interpolateRdYlGn).domain([0, 1]);

export function scoreToColor(score: number): string {
  return fundingColorScale(Math.min(Math.max(score, 0), 1)) as unknown as string;
}

/** Same color at reduced alpha for polygon sides. */
export function scoreToSideColor(score: number): string {
  const base = scoreToColor(score);
  // interpolateRdYlGn returns "rgb(r, g, b)", convert to rgba
  return base.replace("rgb(", "rgba(").replace(")", ", 0.25)");
}
