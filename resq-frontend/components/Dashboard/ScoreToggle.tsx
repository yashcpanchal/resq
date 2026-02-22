"use client";

interface ScoreToggleProps {
    activeMode: "funding" | "crisis";
    onChange: (mode: "funding" | "crisis") => void;
}

export default function ScoreToggle({ activeMode, onChange }: ScoreToggleProps) {
    const isCrisis = activeMode === "crisis";

    return (
        <div className="absolute top-5 right-5 z-20 flex items-center gap-3 rounded-xl bg-black/60 backdrop-blur-md border border-white/10 px-4 py-2.5">
            <span
                className={`text-xs font-medium transition-colors ${!isCrisis ? "text-white" : "text-gray-500"}`}
            >
                Funding Gap
            </span>

            <button
                onClick={() => onChange(isCrisis ? "funding" : "crisis")}
                className="relative w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                style={{
                    background: isCrisis
                        ? "rgba(59, 130, 246, 0.5)"
                        : "rgba(255, 255, 255, 0.15)",
                }}
                aria-label="Toggle between Funding Gap and Crisis Score"
            >
                <span
                    className="absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-200"
                    style={{
                        transform: isCrisis ? "translateX(20px)" : "translateX(0)",
                    }}
                />
            </button>

            <span
                className={`text-xs font-medium transition-colors ${isCrisis ? "text-white" : "text-gray-500"}`}
            >
                Crisis Score
            </span>
        </div>
    );
}
