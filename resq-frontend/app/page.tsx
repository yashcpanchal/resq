"use client";

import { useState, useCallback } from "react";
import dynamic from "next/dynamic";
import HeatmapLegend from "@/components/Globe/HeatmapLegend";
import SidePanel from "@/components/Dashboard/SidePanel";
import SearchBar from "@/components/Dashboard/SearchBar";
import { useQuery } from "@tanstack/react-query";
import { fetchFundingScores } from "@/lib/api";
import { m49ToIso3 } from "@/lib/countryCodeMap";

// Globe is heavy + needs window — load only on client
const MainGlobe = dynamic(() => import("@/components/Globe/MainGlobe"), {
  ssr: false,
  loading: () => (
    <div className="flex h-screen w-screen items-center justify-center bg-gray-950">
      <div className="flex flex-col items-center gap-3">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-500/30 border-t-blue-500" />
        <p className="text-sm text-gray-400">Loading globe…</p>
      </div>
    </div>
  ),
});

interface SelectedCountry {
  name: string;
  code: string;
  score: number;
}

export default function Home() {
  const [selected, setSelected] = useState<SelectedCountry | null>(null);

  const { data: scores = {} } = useQuery({
    queryKey: ["funding-scores"],
    queryFn: fetchFundingScores,
  });

  const handleCountryClick = useCallback(
    (
      country: { properties: { name: string;[key: string]: unknown }; id?: string | number },
      score: number
    ) => {
      // Map numeric M49 id → ISO-3 code
      const numericId = typeof country.id === "number"
        ? String(country.id).padStart(3, "0")
        : String(country.id ?? "");
      const code = m49ToIso3[numericId] ?? numericId;
      setSelected({
        name: country.properties?.name ?? "Unknown",
        code,
        score,
      });
    },
    []
  );

  const handleSearchSelect = useCallback(
    (code: string) => {
      setSelected({
        name: code, // country codes are what we have
        code,
        score: scores[code] ?? -1,
      });
    },
    [scores]
  );

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-gray-950">
      {/* Title overlay */}
      <div className="absolute top-5 left-5 z-20">
        <h1 className="text-lg font-bold tracking-tight text-white/90">
          ResQ-Capital
        </h1>
        <p className="text-xs text-gray-400">
          Humanitarian Funding Heatmap
        </p>
      </div>

      <SearchBar onSelect={handleSearchSelect} />

      <MainGlobe
        focusCountryCode={selected?.code ?? null}
        onCountryClick={handleCountryClick}
      />

      <HeatmapLegend />

      <SidePanel
        country={selected?.name ?? null}
        score={selected?.score ?? -1}
        onClose={() => setSelected(null)}
      />
    </main>
  );
}
