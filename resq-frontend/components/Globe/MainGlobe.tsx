"use client";

import dynamic from "next/dynamic";
import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { feature } from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";
import type { FeatureCollection, Feature, Geometry } from "geojson";
import { geoCentroid } from "d3-geo";
import { fetchFundingScores, fetchCrisisScores } from "@/lib/api";
import { scoreToColor, scoreToSideColor } from "@/lib/utils";
import { m49ToIso3 } from "@/lib/countryCodeMap";
import type { RegionMarker } from "@/data/majorCities";
import type { ScoreMode } from "@/app/page";

const Globe = dynamic(() => import("react-globe.gl"), { ssr: false });

const WORLD_TOPO_URL =
    "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

const DEFAULT_ALTITUDE = 2.5;
const FOCUS_ALTITUDE = 1.6;
const TRANSITION_MS = 1000;

interface CountryFeature extends Feature<Geometry> {
    properties: {
        name: string;
        iso_a3?: string;
        ISO_A3?: string;
        [key: string]: unknown;
    };
}

interface GlobeInstance {
    controls: () => { autoRotate: boolean; autoRotateSpeed: number };
    pointOfView: (
        pov: { lat?: number; lng?: number; altitude?: number },
        transitionMs?: number
    ) => void;
}

interface MainGlobeProps {
    focusCountryCode?: string | null;
    onCountryClick?: (country: CountryFeature, score: number) => void;
    onCountryHover?: (country: CountryFeature | null) => void;
    regionMarkers?: RegionMarker[];
    onRegionClick?: (region: RegionMarker) => void;
    scoreMode?: ScoreMode;
}

/* Severity → soft color for the ring highlight */
function markerColor(marker: any): string {
    const needs = marker.needs ?? [];
    if (needs.some((n: any) => n.severity === "critical"))
        return "rgba(239, 68, 68, 0.7)";   // soft red
    if (needs.some((n: any) => n.severity === "high"))
        return "rgba(249, 115, 22, 0.65)";  // soft orange
    return "rgba(96, 165, 250, 0.6)";       // soft blue
}

export default function MainGlobe({
    focusCountryCode,
    onCountryClick,
    onCountryHover,
    regionMarkers = [],
    onRegionClick,
    scoreMode = "funding",
}: MainGlobeProps) {
    const globeRef = useRef<GlobeInstance | undefined>(undefined);
    const [countries, setCountries] = useState<CountryFeature[]>([]);
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
    const [selectedIso, setSelectedIso] = useState<string | null>(null);

    const { data: rawFundingScores = {} } = useQuery({
        queryKey: ["funding-scores"],
        queryFn: fetchFundingScores,
    });

    const { data: rawCrisisScores = {} } = useQuery({
        queryKey: ["crisis-scores"],
        queryFn: fetchCrisisScores,
    });

    /* Scale and pick active dataset based on scoreMode */
    const scores = useMemo(() => {
        const raw = scoreMode === "funding" ? rawFundingScores : rawCrisisScores;
        const scaled: Record<string, number> = {};
        for (const [k, v] of Object.entries(raw)) {
            scaled[k] = v * -10000;
        }
        return scaled;
    }, [rawFundingScores, rawCrisisScores, scoreMode]);

    /* Compute the actual [min, max] domain from the scaled scores
       so colours distribute evenly across the real data range. */
    const scoreDomain = useMemo<[number, number]>(() => {
        const vals = Object.values(scores);
        if (vals.length === 0) return [-1, 1];
        return [Math.min(...vals), Math.max(...vals)];
    }, [scores]);

    useEffect(() => {
        fetch(WORLD_TOPO_URL)
            .then((r) => r.json())
            .then((topo: Topology<{ countries: GeometryCollection }>) => {
                const geo = feature(
                    topo,
                    topo.objects.countries
                ) as unknown as FeatureCollection;
                setCountries(geo.features as CountryFeature[]);
            });
    }, []);

    useEffect(() => {
        const update = () =>
            setDimensions({ width: window.innerWidth, height: window.innerHeight });
        update();
        window.addEventListener("resize", update);
        return () => window.removeEventListener("resize", update);
    }, []);

    const getIso = useCallback((feat: CountryFeature): string => {
        // 1. Try numeric ID (M49)
        const numericId =
            typeof feat.id === "number"
                ? String(feat.id).padStart(3, "0")
                : String(feat.id ?? "");

        const iso = m49ToIso3[numericId];
        if (iso) return iso;

        // 2. Fallback to properties (common in natural earth / world-atlas)
        const propIso = (feat.properties?.iso_a3 || feat.properties?.ISO_A3) as string;
        if (propIso && propIso !== "-99") return propIso;

        return numericId;
    }, []);

    const getScore = useCallback(
        (feat: CountryFeature): number => {
            const iso = getIso(feat);
            return iso in scores ? scores[iso] : NaN;
        },
        [scores, getIso]
    );

    const featureByIso = useMemo(() => {
        const map = new Map<string, CountryFeature>();
        for (const feat of countries) map.set(getIso(feat), feat);
        return map;
    }, [countries, getIso]);

    const focusOnFeature = useCallback((feat: CountryFeature) => {
        const gl = globeRef.current;
        if (!gl?.pointOfView) return;
        const [lng, lat] = geoCentroid(feat);
        gl.pointOfView({ lat, lng, altitude: FOCUS_ALTITUDE }, TRANSITION_MS);
    }, []);

    useEffect(() => {
        if (!focusCountryCode) {
            setSelectedIso(null);
            const gl = globeRef.current;
            if (gl?.pointOfView)
                gl.pointOfView({ altitude: DEFAULT_ALTITUDE }, TRANSITION_MS);
            return;
        }
        const feat = featureByIso.get(focusCountryCode);
        if (feat) {
            setSelectedIso(focusCountryCode);
            focusOnFeature(feat);
        }
    }, [focusCountryCode, featureByIso, focusOnFeature]);

    /* ---- Polygon rendering ---- */

    const capColor = useCallback(
        (feat: object) => {
            const f = feat as CountryFeature;
            const iso = getIso(f);
            const s = getScore(f);
            if (iso === selectedIso)
                return !isNaN(s) ? scoreToColor(s, scoreDomain) : "rgba(100, 140, 255, 0.8)";
            if (isNaN(s)) return "rgba(30, 30, 50, 0.6)";
            return scoreToColor(s, scoreDomain);
        },
        [getScore, getIso, selectedIso, scoreDomain]
    );

    const sideColor = useCallback(
        (feat: object) => {
            const f = feat as CountryFeature;
            const iso = getIso(f);
            const s = getScore(f);
            if (iso === selectedIso)
                return !isNaN(s) ? scoreToColor(s, scoreDomain) : "rgba(100, 140, 255, 0.6)";
            if (isNaN(s)) return "rgba(30, 30, 50, 0.3)";
            return scoreToSideColor(s, scoreDomain);
        },
        [getScore, getIso, selectedIso, scoreDomain]
    );

    const strokeColor = useCallback(
        (feat: object) => {
            const f = feat as CountryFeature;
            const iso = getIso(f);
            return iso === selectedIso
                ? "rgba(255, 255, 255, 0.8)"
                : "rgba(255, 255, 255, 0.15)";
        },
        [getIso, selectedIso]
    );

    const altitude = useCallback(
        (feat: object) => {
            const f = feat as CountryFeature;
            const iso = getIso(f);
            const s = getScore(f);
            if (iso === selectedIso) return 0.06;
            if (isNaN(s)) return 0.005;
            // Use absolute value for altitude so negative scores still raise
            const absNorm = scoreDomain[1] !== scoreDomain[0]
                ? Math.abs(s) / Math.max(Math.abs(scoreDomain[0]), Math.abs(scoreDomain[1]))
                : 0;
            return 0.01 + absNorm * 0.02;
        },
        [getScore, getIso, selectedIso, scoreDomain]
    );

    const label = useCallback(
        (feat: object) => {
            const f = feat as CountryFeature;
            const iso = getIso(f);
            const s = getScore(f);
            const name = f.properties?.name ?? "Unknown";

            const hasMarkers = regionMarkers.some(m => m.countryCode === iso);
            const modeLabel = scoreMode === "funding" ? "Funding Gap" : "Crisis Score";

            let scoreText = !isNaN(s) ? `${modeLabel}: ${s.toFixed(0)}` : "No data";
            if (isNaN(s) && hasMarkers) {
                scoreText = "Crisis Data Available";
            }

            return `
        <div style="
          background: rgba(10,10,20,0.85);
          backdrop-filter: blur(8px);
          color: white;
          padding: 8px 14px;
          border-radius: 8px;
          font-family: system-ui;
          font-size: 13px;
          line-height: 1.4;
          border: 1px solid rgba(255,255,255,0.1);
        ">
          <strong style="font-size: 14px;">${name}</strong><br/>
          <span style="color: ${!isNaN(s) ? scoreToColor(s, scoreDomain) : (hasMarkers ? "#3b82f6" : "#888")};">
            ${scoreText}
          </span>
        </div>`;
        },
        [getScore, getIso, regionMarkers, scoreDomain, scoreMode]
    );

    /* ---- Marker label tooltip ---- */
    const pointLabel = useCallback((d: object) => {
        const m = d as any;
        const needs = m.needs ?? [];
        const needCount = needs.length;
        const worst = needs.some((n: any) => n.severity === "critical")
            ? "Critical"
            : needs.some((n: any) => n.severity === "high")
                ? "High"
                : "Moderate";
        return `
        <div style="
          background: rgba(10,10,20,0.9);
          backdrop-filter: blur(8px);
          color: white;
          padding: 6px 12px;
          border-radius: 6px;
          font-family: system-ui;
          font-size: 12px;
          line-height: 1.4;
          border: 1px solid rgba(255,255,255,0.12);
        ">
          <strong>${m.name}</strong><br/>
          <span style="color: #9ca3af;">${needCount} sector${needCount !== 1 ? "s" : ""} · ${worst}</span>
        </div>`;
    }, []);

    return (
        <Globe
            ref={globeRef as React.MutableRefObject<undefined>}
            width={dimensions.width}
            height={dimensions.height}
            globeImageUrl="//unpkg.com/three-globe/example/img/earth-dark.jpg"
            backgroundImageUrl="//unpkg.com/three-globe/example/img/night-sky.png"
            polygonsData={countries}
            polygonCapColor={capColor}
            polygonSideColor={sideColor}
            polygonStrokeColor={strokeColor}
            polygonLabel={label}
            polygonAltitude={altitude}
            onPolygonClick={(feat: object) => {
                const f = feat as CountryFeature;
                const s = getScore(f);
                const iso = getIso(f);
                setSelectedIso(iso);
                focusOnFeature(f);
                onCountryClick?.(f, s);
            }}
            onPolygonHover={(feat: object | null) => {
                onCountryHover?.(feat ? (feat as CountryFeature) : null);
            }}
            polygonsTransitionDuration={300}
            atmosphereColor="#3a7ecf"
            atmosphereAltitude={0.2}

            /* Soft ring highlights at each crisis city */
            ringsData={regionMarkers}
            ringLat={(d: object) => (d as any).lat}
            ringLng={(d: object) => (d as any).lng}
            ringAltitude={0.07}
            ringColor={(d: object) => markerColor(d)}
            ringMaxRadius={1.2}
            ringPropagationSpeed={0}
            ringRepeatPeriod={0}

            /* Small dot at center of each ring */
            pointsData={regionMarkers}
            pointLat="lat"
            pointLng="lng"
            pointLabel={pointLabel}
            pointColor={(d: object) => markerColor(d)}
            pointAltitude={0.08}
            pointRadius={0.6}
            pointsMerge={false}
            onPointClick={(d: object) => {
                const r = d as RegionMarker;
                onRegionClick?.(r);
            }}
        />
    );
}
