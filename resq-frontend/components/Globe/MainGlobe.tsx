"use client";

import dynamic from "next/dynamic";
import { useEffect, useState, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { feature } from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";
import type { FeatureCollection, Feature, Geometry } from "geojson";
import { fetchFundingScores } from "@/lib/api";
import { scoreToColor, scoreToSideColor } from "@/lib/utils";

// react-globe.gl must be client-only (uses WebGL / window)
const Globe = dynamic(() => import("react-globe.gl"), { ssr: false });

const WORLD_TOPO_URL =
    "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

interface CountryFeature extends Feature<Geometry> {
    properties: {
        name: string;
        iso_a3?: string;
        ISO_A3?: string;
        [key: string]: unknown;
    };
}

interface MainGlobeProps {
    onCountryClick?: (country: CountryFeature, score: number) => void;
    onCountryHover?: (country: CountryFeature | null) => void;
}

export default function MainGlobe({
    onCountryClick,
    onCountryHover,
}: MainGlobeProps) {
    const globeRef = useRef<unknown>(null);
    const [countries, setCountries] = useState<CountryFeature[]>([]);
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

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

    // Auto-rotate
    useEffect(() => {
        const gl = globeRef.current as {
            controls: () => { autoRotate: boolean; autoRotateSpeed: number };
        } | null;
        if (gl?.controls) {
            const controls = gl.controls();
            controls.autoRotate = true;
            controls.autoRotateSpeed = 0.4;
        }
    }, [countries]);

    const getIso = (feat: CountryFeature): string => {
        return (
            feat.properties?.iso_a3 ||
            feat.properties?.ISO_A3 ||
            feat.properties?.ISO_A3_EH ||
            (feat.id as string) ||
            ""
        );
    };

    const getScore = useCallback(
        (feat: CountryFeature): number => {
            const iso = getIso(feat);
            return scores[iso] ?? -1; // -1 = no data
        },
        [scores]
    );

    const capColor = useCallback(
        (feat: object) => {
            const s = getScore(feat as CountryFeature);
            if (s < 0) return "rgba(30, 30, 50, 0.6)"; // no data = dark
            return scoreToColor(s);
        },
        [getScore]
    );

    const sideColor = useCallback(
        (feat: object) => {
            const s = getScore(feat as CountryFeature);
            if (s < 0) return "rgba(30, 30, 50, 0.3)";
            return scoreToSideColor(s);
        },
        [getScore]
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
            ref={globeRef as React.Ref<unknown>}
            width={dimensions.width}
            height={dimensions.height}
            globeImageUrl="//unpkg.com/three-globe/example/img/earth-dark.jpg"
            backgroundImageUrl="//unpkg.com/three-globe/example/img/night-sky.png"
            polygonsData={countries}
            polygonCapColor={capColor}
            polygonSideColor={sideColor}
            polygonStrokeColor={() => "rgba(255, 255, 255, 0.15)"}
            polygonLabel={label}
            polygonAltitude={(feat: object) => {
                const s = getScore(feat as CountryFeature);
                return s >= 0 ? 0.01 + s * 0.02 : 0.005;
            }}
            onPolygonClick={(feat: object) => {
                const f = feat as CountryFeature;
                const s = getScore(f);
                onCountryClick?.(f, s);
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
