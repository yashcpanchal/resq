"use client";

import { useState, useMemo } from "react";
import { Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchFundingScores } from "@/lib/api";
import { allCountryCodes, iso3ToName } from "@/lib/countryCodeMap";

interface SearchBarProps {
    onSelect: (countryCode: string) => void;
}

export default function SearchBar({ onSelect }: SearchBarProps) {
    const [query, setQuery] = useState("");
    const [open, setOpen] = useState(false);

    const { data: scores = {} } = useQuery({
        queryKey: ["funding-scores"],
        queryFn: fetchFundingScores,
    });

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return allCountryCodes.slice(0, 8);

        return allCountryCodes
            .filter((code) => {
                const name = (iso3ToName[code] ?? "").toLowerCase();
                return (
                    code.toLowerCase().includes(q) ||
                    name.includes(q)
                );
            })
            .slice(0, 8);
    }, [query]);

    return (
        <div className="absolute top-5 left-1/2 -translate-x-1/2 z-20 w-80">
            <div className="relative">
                <Search
                    size={16}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                />
                <input
                    type="text"
                    value={query}
                    suppressHydrationWarning
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setOpen(true);
                    }}
                    onFocus={() => setOpen(true)}
                    onBlur={() => setTimeout(() => setOpen(false), 150)}
                    placeholder="Search by country name or code…"
                    className="w-full rounded-xl bg-black/60 backdrop-blur-md border border-white/10 pl-10 pr-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                />
            </div>

            {open && filtered.length > 0 && (
                <div className="mt-1 rounded-xl bg-gray-950/90 backdrop-blur-md border border-white/10 overflow-hidden shadow-xl max-h-72 overflow-y-auto">
                    {filtered.map((code) => {
                        const name = iso3ToName[code] ?? code;
                        const score = scores[code];
                        const hasScore = score !== undefined && score >= 0;
                        return (
                            <button
                                key={code}
                                onMouseDown={() => {
                                    onSelect(code);
                                    setQuery(name);
                                    setOpen(false);
                                }}
                                className="w-full px-4 py-2 text-left text-sm text-gray-200 hover:bg-white/10 transition flex items-center justify-between gap-2"
                            >
                                <span className="truncate">
                                    {name}{" "}
                                    <span className="text-gray-500 font-mono text-xs">
                                        {code}
                                    </span>
                                </span>
                                <span className="text-gray-500 text-xs whitespace-nowrap">
                                    {hasScore
                                        ? `${(score * 100).toFixed(1)}%`
                                        : "No data"}
                                </span>
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
