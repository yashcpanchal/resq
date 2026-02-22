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
          <TacticalGrid
            center={center}
            analysis={analysis}
            sectors={sectors}
            geojson={geojson}
          />
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