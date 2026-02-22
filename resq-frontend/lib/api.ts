/**
 * API helpers — all calls go through the Next.js rewrite proxy (/api → backend).
 */

import type { FeatureCollection } from "geojson";

export async function fetchFundingScores(): Promise<Record<string, number>> {
    const res = await fetch("/api/funding-scores");
    if (!res.ok) throw new Error(`Failed to fetch funding scores: ${res.status}`);
    return res.json();
}

export interface TacticalAnalysisResult {
    lat: number;
    lng: number;
    name: string;
    analysis: string;
    sectors: Record<string, string>;
    geojson: FeatureCollection;
    annotated_image: string;
}

export async function fetchTacticalAnalysis(
    lat: number,
    lng: number,
    name?: string,
): Promise<TacticalAnalysisResult> {
    const res = await fetch("/api/tactical-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat, lng, name: name ?? "Location" }),
    });
    if (!res.ok) throw new Error(`Tactical analysis failed: ${res.status}`);
    return res.json();
}
