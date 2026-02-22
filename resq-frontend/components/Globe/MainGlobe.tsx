"use client";

import dynamic from "next/dynamic";
import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { feature } from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";
import type { FeatureCollection, Feature, Geometry } from "geojson";
import { geoCentroid } from "d3-geo";
import { fetchFundingScores } from "@/lib/api";
import { scoreToColor, scoreToSideColor } from "@/lib/utils";
import { m49ToIso3 } from "@/lib/countryCodeMap";
import type { RegionMarker } from "@/data/majorCities";

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
}: MainGlobeProps) {
    const globeRef = useRef<GlobeInstance | undefined>(undefined);
    const [countries, setCountries] = useState<CountryFeature[]>([]);
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
    const [selectedIso, setSelectedIso] = useState<string | null>(null);

    const { data: scores = {} } = useQuery({
        queryKey: ["funding-scores"],
        queryFn: fetchFundingScores,
    });

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
            return scores[iso] ?? -1;
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
                return s >= 0 ? scoreToColor(s) : "rgba(100, 140, 255, 0.8)";
            if (s < 0) return "rgba(30, 30, 50, 0.6)";
            return scoreToColor(s);
        },
        [getScore, getIso, selectedIso]
    );

    const sideColor = useCallback(
        (feat: object) => {
            const f = feat as CountryFeature;
            const iso = getIso(f);
            const s = getScore(f);
            if (iso === selectedIso)
                return s >= 0 ? scoreToColor(s) : "rgba(100, 140, 255, 0.6)";
            if (s < 0) return "rgba(30, 30, 50, 0.3)";
            return scoreToSideColor(s);
        },
        [getScore, getIso, selectedIso]
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
            return s >= 0 ? 0.01 + s * 0.02 : 0.005;
        },
        [getScore, getIso, selectedIso]
    );

    const label = useCallback(
        (feat: object) => {
            const f = feat as CountryFeature;
            const iso = getIso(f);
            const s = getScore(f);
            const name = f.properties?.name ?? "Unknown";

            // If we have markers for this country, it's a "Crisis Context Found"
            const hasMarkers = regionMarkers.some(m => m.countryCode === iso);

            let scoreText = s >= 0 ? `${(s * 100).toFixed(1)}% funded` : "No funding data";
            if (s < 0 && hasMarkers) {
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
          <span style="color: ${s >= 0 ? scoreToColor(s) : (hasMarkers ? "#3b82f6" : "#888")};">
            ${scoreText}
          </span>
        </div>`;
        },
        [getScore, getIso, regionMarkers]
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
