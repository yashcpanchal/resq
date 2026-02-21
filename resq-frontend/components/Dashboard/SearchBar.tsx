"use client";

import { useState, useMemo } from "react";
import { Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchFundingScores } from "@/lib/api";

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

    const countryCodes = useMemo(() => Object.keys(scores).sort(), [scores]);

    const filtered = useMemo(() => {
        if (!query.trim()) return countryCodes.slice(0, 8);
        const q = query.toUpperCase();
        return countryCodes.filter((c) => c.includes(q)).slice(0, 8);
    }, [query, countryCodes]);

    return (
        <div className="absolute top-5 left-1/2 -translate-x-1/2 z-20 w-72">
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
                    placeholder="Search country code…"
                    className="w-full rounded-xl bg-black/60 backdrop-blur-md border border-white/10 pl-10 pr-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                />
            </div>

            {open && filtered.length > 0 && (
                <div className="mt-1 rounded-xl bg-gray-950/90 backdrop-blur-md border border-white/10 overflow-hidden shadow-xl">
                    {filtered.map((code) => (
                        <button
                            key={code}
                            onMouseDown={() => {
                                onSelect(code);
                                setQuery(code);
                                setOpen(false);
                            }}
                            className="w-full px-4 py-2 text-left text-sm text-gray-200 hover:bg-white/10 transition flex justify-between"
                        >
                            <span className="font-mono">{code}</span>
                            <span className="text-gray-500">
                                {(scores[code] * 100).toFixed(1)}%
                            </span>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
