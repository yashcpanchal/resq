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
import { m49ToIso3, iso3ToM49 } from "@/lib/countryCodeMap";

// react-globe.gl must be client-only (uses WebGL / window)
const Globe = dynamic(() => import("react-globe.gl"), { ssr: false });

const WORLD_TOPO_URL =
    "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

/** Default camera altitude (fully zoomed out). */
const DEFAULT_ALTITUDE = 2.5;
/** Camera altitude when focused on a country. */
const FOCUS_ALTITUDE = 1.6;
/** Transition duration in ms for the rotate/zoom animation. */
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
    onCountryClick?: (country: CountryFeature, score: number, lat: number, lng: number) => void;
    onCountryHover?: (country: CountryFeature | null) => void;
}

export default function MainGlobe({
    focusCountryCode,
    onCountryClick,
    onCountryHover,
}: MainGlobeProps) {
    const globeRef = useRef<GlobeInstance | undefined>(undefined);
    const [countries, setCountries] = useState<CountryFeature[]>([]);
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
    const [selectedIso, setSelectedIso] = useState<string | null>(null);

    const { data: scores = {} } = useQuery({
        queryKey: ["funding-scores"],
        queryFn: fetchFundingScores,
    });

    // Load TopoJSON → GeoJSON
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

    // Track window size for responsive globe
    useEffect(() => {
        const update = () =>
            setDimensions({ width: window.innerWidth, height: window.innerHeight });
        update();
        window.addEventListener("resize", update);
        return () => window.removeEventListener("resize", update);
    }, []);


    // ---- Helpers ---- //

    const getIso = useCallback((feat: CountryFeature): string => {
        const numericId =
            typeof feat.id === "number"
                ? String(feat.id).padStart(3, "0")
                : String(feat.id ?? "");
        return m49ToIso3[numericId] ?? numericId;
    }, []);

    const getScore = useCallback(
        (feat: CountryFeature): number => {
            const iso = getIso(feat);
            return scores[iso] ?? -1;
        },
        [scores, getIso]
    );

    // ---- Focus / zoom animation ---- //

    /** Find the feature matching an ISO-3 code. */
    const featureByIso = useMemo(() => {
        const map = new Map<string, CountryFeature>();
        for (const feat of countries) {
            map.set(getIso(feat), feat);
        }
        return map;
    }, [countries, getIso]);

    /** Animate to the centroid of a feature. */
    const focusOnFeature = useCallback(
        (feat: CountryFeature) => {
            const gl = globeRef.current;
            if (!gl?.pointOfView) return;

            const [lng, lat] = geoCentroid(feat);
            gl.pointOfView({ lat, lng, altitude: FOCUS_ALTITUDE }, TRANSITION_MS);
        },
        []
    );

    /** React to external focus requests (e.g. search). */
    useEffect(() => {
        if (!focusCountryCode) {
            // Reset: zoom out
            setSelectedIso(null);
            const gl = globeRef.current;
            if (gl?.pointOfView) {
                gl.pointOfView({ altitude: DEFAULT_ALTITUDE }, TRANSITION_MS);
            }
            return;
        }

        const feat = featureByIso.get(focusCountryCode);
        if (feat) {
            setSelectedIso(focusCountryCode);
            focusOnFeature(feat);
        }
    }, [focusCountryCode, featureByIso, focusOnFeature]);

    // ---- Rendering callbacks ---- //

    const capColor = useCallback(
        (feat: object) => {
            const f = feat as CountryFeature;
            const iso = getIso(f);
            const s = getScore(f);

            // Highlight selected country with a bright accent
            if (iso === selectedIso) {
                return s >= 0 ? scoreToColor(s) : "rgba(100, 140, 255, 0.8)";
            }

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

            if (iso === selectedIso) {
                return s >= 0 ? scoreToColor(s) : "rgba(100, 140, 255, 0.6)";
            }

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

            // Elevate the selected country so it pops out
            if (iso === selectedIso) return 0.06;

            return s >= 0 ? 0.01 + s * 0.02 : 0.005;
        },
        [getScore, getIso, selectedIso]
    );

    const label = useCallback(
        (feat: object) => {
            const f = feat as CountryFeature;
            const s = getScore(f);
            const name = f.properties?.name ?? "Unknown";
            const scoreText =
                s >= 0 ? `${(s * 100).toFixed(1)}% funded` : "No data";
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
          <span style="color: ${s >= 0 ? scoreToColor(s) : "#888"};">
            ${scoreText}
          </span>
        </div>
      `;
        },
        [getScore]
    );

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
                const [cLng, cLat] = geoCentroid(f);
                onCountryClick?.(f, s, cLat, cLng);
            }}
            onPolygonHover={(feat: object | null) => {
                onCountryHover?.(feat ? (feat as CountryFeature) : null);
            }}
            polygonsTransitionDuration={300}
            atmosphereColor="#3a7ecf"
            atmosphereAltitude={0.2}
        />
    );
}
