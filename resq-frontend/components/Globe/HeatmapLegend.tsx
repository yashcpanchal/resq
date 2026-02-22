"use client";

import { scoreToColor } from "@/lib/utils";
import type { ScoreMode } from "@/app/page";

interface HeatmapLegendProps {
    domain?: [number, number];
    scoreMode?: ScoreMode;
}

export default function HeatmapLegend({ domain = [-1, 1], scoreMode = "funding" }: HeatmapLegendProps) {
    const [lo, hi] = domain;

    // Build 6 evenly-spaced stops across the full signed range
    const STOPS = Array.from({ length: 6 }, (_, i) => lo + (hi - lo) * (i / 5));

    return (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 rounded-xl bg-black/60 px-4 py-3 backdrop-blur-md border border-white/10">
            <span className="text-xs font-medium text-gray-400 mr-1">
                {scoreMode === "funding" ? "Underfunded" : "High Crisis"}
            </span>
            <div className="flex h-3 w-40 rounded-full overflow-hidden">
                {STOPS.slice(0, -1).map((s, i) => (
                    <div
                        key={i}
                        className="flex-1"
                        style={{
                            background: `linear-gradient(to right, ${scoreToColor(s, domain)}, ${scoreToColor(STOPS[i + 1], domain)})`,
                        }}
                    />
                ))}
            </div>
            <span className="text-xs font-medium text-gray-400 ml-1">
                {scoreMode === "funding" ? "Well-funded" : "Low Crisis"}
            </span>
        </div>
    );
}
