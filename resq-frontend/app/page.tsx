"use client";

import { useState, useCallback, useMemo, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import HeatmapLegend from "@/components/Globe/HeatmapLegend";
import SidePanel from "@/components/Dashboard/SidePanel";
import LeftPanel from "@/components/Dashboard/LeftPanel";
import SearchBar from "@/components/Dashboard/SearchBar";
import { useQuery } from "@tanstack/react-query";
import { fetchFundingScores, fetchCountryCrises, triggerIngest } from "@/lib/api";
import type { CityCrisis } from "@/lib/api";
import { m49ToIso3, iso3ToName } from "@/lib/countryCodeMap";
import type { RegionMarker } from "@/data/majorCities";

// Globe is heavy + needs window — load only on client
const MainGlobe = dynamic(() => import("@/components/Globe/MainGlobe"), {
  ssr: false,
  loading: () => (
    <div className="h-screen w-screen flex items-center justify-center bg-gray-950">
      <div className="flex flex-col items-center gap-3">
        <div className="h-10 w-10 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
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
  const [selectedRegion, setSelectedRegion] = useState<(RegionMarker | CityCrisis) | null>(null);
  const [discoveredCrises, setDiscoveredCrises] = useState<CityCrisis[]>([]);
  const [loadingCrises, setLoadingCrises] = useState(false);

  // Cache: country name -> { cities: CityCrisis[], ts: number }
  useEffect(() => {
    // Sync localStorage to cache on mount
    const saved = localStorage.getItem("resq_discovery_cache");
    if (saved) {
      try {
        cacheRef.current = JSON.parse(saved);
      } catch (e) {
        console.error("Failed to parse discovery cache:", e);
      }
    }
  }, []);

  const cacheRef = useRef<Record<string, { cities: CityCrisis[]; ts: number }>>({});

  // Only show discovered crisis markers — no static defaults
  const regionMarkers = useMemo(() => {
    return discoveredCrises.map((dc) => ({
      lat: dc.lat,
      lng: dc.lng,
      name: dc.name,
      countryCode: selected?.code ?? "",
      needs: dc.needs,
      crises: dc.crises,
    } as RegionMarker & Partial<CityCrisis>));
  }, [discoveredCrises, selected?.code]);

  const { data: scores = {} } = useQuery({
    queryKey: ["funding-scores"],
    queryFn: fetchFundingScores,
  });

  const loadCrises = useCallback(async (countryName: string) => {
    // Check frontend cache first
    const key = countryName.toLowerCase();
    const cached = cacheRef.current[key];

    // 1 hour TTL for discovery results
    if (cached && Date.now() - cached.ts < 3600000) {
      if (!cached.cities.some(c => c.name === "Parse error")) {
        setDiscoveredCrises(cached.cities);
        return;
      }
    }

    setDiscoveredCrises([]);
    setLoadingCrises(true);
    try {
      const resp = await fetchCountryCrises(countryName);
      const cities = resp.cities ?? [];
      setDiscoveredCrises(cities);

      // Update cache + persist to localStorage
      cacheRef.current[key] = { cities, ts: Date.now() };
      localStorage.setItem("resq_discovery_cache", JSON.stringify(cacheRef.current));
    } catch (err) {
      console.error("Discovery failed:", err);
    } finally {
      setLoadingCrises(false);
    }
  }, []);

  const handleCountryClick = useCallback(
    (
      country: { properties: { name: string;[key: string]: unknown }; id?: string | number },
      score: number
    ) => {
      setSelectedRegion(null);
      // Map numeric M49 id → ISO-3 code
      const numericId = typeof country.id === "number"
        ? String(country.id).padStart(3, "0")
        : String(country.id ?? "");
      const code = m49ToIso3[numericId] ?? numericId;
      const name = country.properties?.name ?? "Unknown";
      setSelected({
        name,
        code,
        score,
      });
      loadCrises(name);
    },
    [loadCrises]
  );

  const handleSearchSelect = useCallback(
    (code: string) => {
      setSelectedRegion(null);
      const name = iso3ToName[code] ?? code;
      setSelected({
        name,
        code,
        score: scores[code] ?? -1,
      });
      loadCrises(name);
    },
    [scores, loadCrises]
  );

  const ingestCacheRef = useRef<Record<string, number>>({});

  const handleRegionClick = useCallback((region: RegionMarker | CityCrisis) => {
    setSelectedRegion(region);
    // Silent background ingest to warm up Actian Layer 3 for this country
    if (selected?.name) {
      const now = Date.now();
      const lastIngest = ingestCacheRef.current[selected.name] || 0;
      if (now - lastIngest > 3600000) {
        ingestCacheRef.current[selected.name] = now;
        triggerIngest(selected.name).catch((e) => console.warn("Background ingest failed:", e));
      }
    }
  }, [selected?.name]);

  const handleCloseLeftPanel = useCallback(() => {
    setSelected(null);
    setSelectedRegion(null);
    setDiscoveredCrises([]);
  }, []);

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-gray-950 text-white">
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
        regionMarkers={regionMarkers}
        onRegionClick={handleRegionClick}
      />

      <HeatmapLegend />

      <LeftPanel
        countryName={selected?.name ?? null}
        selectedRegion={selectedRegion as any}
        discoveredCrises={discoveredCrises}
        loadingCrises={loadingCrises}
        onClose={handleCloseLeftPanel}
        onClearRegion={() => setSelectedRegion(null)}
      />

      <SidePanel
        country={selected?.name ?? null}
        score={selected?.score ?? -1}
        lat={selectedRegion?.lat}
        lng={selectedRegion?.lng}
        onClose={handleCloseLeftPanel}
      />
    </main>
  );
}
