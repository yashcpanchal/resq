"use client";

import { scoreToColor } from "@/lib/utils";

const STOPS = [0, 0.2, 0.4, 0.6, 0.8, 1.0];

export default function HeatmapLegend() {
    return (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 rounded-xl bg-black/60 px-4 py-3 backdrop-blur-md border border-white/10">
            <span className="text-xs font-medium text-gray-400 mr-1">
                Underfunded
            </span>
            <div className="flex h-3 w-40 rounded-full overflow-hidden">
                {STOPS.slice(0, -1).map((s, i) => (
                    <div
                        key={i}
                        className="flex-1"
                        style={{
                            background: `linear-gradient(to right, ${scoreToColor(s)}, ${scoreToColor(STOPS[i + 1])})`,
                        }}
                    />
                ))}
            </div>
            <span className="text-xs font-medium text-gray-400 ml-1">
                Well-funded
            </span>
        </div>
    );
}
