"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import { fetchTacticalAnalysis, type TacticalAnalysisResult } from "@/lib/api";
import type { FeatureCollection } from "geojson";

const TacticalGrid = dynamic(() => import("@/components/TacticalGrid"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center bg-gray-950">
      <div className="flex flex-col items-center gap-3">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-green-500/30 border-t-green-500" />
        <p className="text-sm text-gray-400">Loading Tactical Grid...</p>
      </div>
    </div>
  ),
});

const FALLBACK_CENTER = { lat: 15.5007, lng: 32.5599 };
const FALLBACK_ANALYSIS = `
[NW] Open flat clearing suitable for staging and helicopter landing.
[N] Dense urban layout with multiple structures and buildings.
[NE] Road access from the east; vehicle entry point.
[W] Rubble and debris; hazard zone, avoid.
[C] Central courtyard, partially clear, suitable for staging.
[E] Main access road leading to highway.
[SW] Collapse damage and obstacle; risk area.
[S] Empty field, flat terrain.
[SE] Building structure intact; possible facility.
`.trim();

function TacticalContent() {
  const params = useSearchParams();
  const paramLat = params.get("lat");
  const paramLng = params.get("lng");
  const paramName = params.get("name") ?? "Location";
  const isEmbed = params.get("embed") === "true";

  const hasParams = paramLat !== null && paramLng !== null;
  const center = hasParams
    ? { lat: parseFloat(paramLat), lng: parseFloat(paramLng) }
    : FALLBACK_CENTER;
  const name = hasParams ? paramName : "Khartoum (demo)";

  const [state, setState] = useState<"idle" | "loading" | "done" | "error">(
    hasParams ? "idle" : "done",
  );
  const [result, setResult] = useState<TacticalAnalysisResult | null>(null);
  const [error, setError] = useState("");

  const runAnalysis = useCallback(async () => {
    setState("loading");
    setError("");
    try {
      const data = await fetchTacticalAnalysis(center.lat, center.lng, name);
      setResult(data);
      setState("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
      setState("error");
    }
  }, [center.lat, center.lng, name]);

  useEffect(() => {
    if (hasParams && state === "idle") {
      runAnalysis();
    }
  }, [hasParams, state, runAnalysis]);

  const analysis = result?.analysis ?? (hasParams ? "" : FALLBACK_ANALYSIS);
  const sectors = result?.sectors;
  const geojson = result?.geojson as FeatureCollection | undefined;

  return (
    <>
      {!isEmbed && (
        <header className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-2">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-sm text-gray-400 hover:text-white transition"
            >
              &larr; Globe
            </Link>
            <h1 className="text-base font-bold text-white/90 tracking-tight">
              Tactical Grid
            </h1>
            <span className="text-xs text-gray-500">
              {name} &middot; {center.lat.toFixed(4)}&deg;N {center.lng.toFixed(4)}&deg;E
            </span>
          </div>
          {state === "loading" && (
            <div className="flex items-center gap-2 text-green-400">
              <Loader2 size={14} className="animate-spin" />
              <span className="text-xs">Analyzing...</span>
            </div>
          )}
        </header>
      )}

      <div className="relative flex-1 min-h-0">
        {state === "error" && (
          <div className="absolute inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-gray-950/90">
            <p className="text-sm text-red-400">{error}</p>
            <button
              onClick={runAnalysis}
              className="rounded-lg bg-green-500/10 border border-green-500/20 px-6 py-2 text-sm text-green-400 hover:bg-green-500/20 transition"
            >
              Retry
            </button>
          </div>
        )}
        {(state === "done" || !hasParams) && (
          <div className="absolute inset-0 z-0 flex bg-gray-950">
            <div className="flex-1 relative h-full">
              <TacticalGrid
                center={center}
                analysis={analysis}
                sectors={sectors}
                geojson={geojson}
              />
            </div>
            {/* Sidebar for Sector Descriptions */}
            {!isEmbed && (
              <div className="w-[340px] shrink-0 border-l border-white/10 bg-gray-950/95 backdrop-blur overflow-y-auto [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-white/10 hover:[&::-webkit-scrollbar-thumb]:bg-white/20 [&::-webkit-scrollbar-thumb]:rounded-full p-4 shadow-[inset_1px_0_10px_rgba(0,0,0,0.5)] z-[1001]">
                <h2 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-400 shadow-[0_0_6px_rgba(0,255,136,0.6)] animate-pulse" />
                  SECTOR INTELLIGENCE
                </h2>
                <div className="space-y-3">
                  {sectors && Object.keys(sectors).length > 0 ? (
                    Object.entries(sectors).map(([tag, desc]) => (
                      <div key={tag} className="bg-white/5 border border-white/10 rounded-lg p-3">
                        <div className="text-[11px] font-bold text-green-400 mb-1">[{tag}] SECTOR</div>
                        <div className="text-xs text-gray-300 leading-relaxed font-sans">{desc}</div>
                      </div>
                    ))
                  ) : (
                    analysis.split('\n').filter(Boolean).map((line, i) => {
                      const match = line.match(/^\[(.*?)\]\s*(.*)$/);
                      if (match) {
                        return (
                          <div key={i} className="bg-white/5 border border-white/10 rounded-lg p-3">
                            <div className="text-[11px] font-bold text-green-400 mb-1">[{match[1]}] SECTOR</div>
                            <div className="text-xs text-gray-300 leading-relaxed font-sans">{match[2]}</div>
                          </div>
                        );
                      }
                      return (
                        <div key={i} className="text-xs text-gray-400 leading-relaxed font-sans">{line}</div>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        )}
        {state === "loading" && (
          <div className="flex h-full items-center justify-center bg-gray-950">
            <div className="flex flex-col items-center gap-3">
              <Loader2 size={32} className="animate-spin text-green-400" />
              <p className="text-sm text-gray-400">
                Running VLM analysis on satellite imagery...
              </p>
              <p className="text-xs text-gray-600">This may take 30-120 seconds</p>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

export default function TacticalPage() {
  return (
    <main className="flex h-screen w-screen flex-col overflow-hidden bg-gray-950">
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center">
            <Loader2 size={32} className="animate-spin text-green-400" />
          </div>
        }
      >
        <TacticalContent />
      </Suspense>
    </main>
  );
}