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
    // Use the Next.js proxy route (same-origin, 5-min timeout) to avoid CORS issues.
    const res = await fetch("/api/tactical-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat, lng, name: name ?? "Location" }),
    });
    if (!res.ok) throw new Error(`Tactical analysis failed: ${res.status}`);
    return res.json();
}

export interface CrisisNeed {
    sector: string;
    severity: string;
    description: string;
    affected_population: string | null;
    funding_gap: string | null;
}

export interface CityCrisis {
    name: string;
    lat: number;
    lng: number;
    needs: CrisisNeed[];
    crises: any[]; // For compatibility
}

export interface CountryCrisesResponse {
    country: string;
    cities: CityCrisis[];
    sources_note: string;
}

export async function fetchCountryCrises(country: string): Promise<CountryCrisesResponse> {
    // Call FastAPI directly — the Next.js proxy times out on long LLM calls.
    const res = await fetch("http://localhost:8000/api/v1/crises-by-country", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country }),
    });
    if (!res.ok) throw new Error(`Failed to fetch country crises: ${res.status}`);
    return res.json();
}

export async function fetchSafetyReport(lat: number, lng: number): Promise<{ report: string }> {
    const res = await fetch("http://localhost:8000/api/v1/safety-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat, lng }),
    });
    if (!res.ok) throw new Error(`Failed to fetch safety report: ${res.status}`);
    return res.json();
}

export async function triggerIngest(country: string): Promise<{ chunks_ingested: number }> {
    const res = await fetch("http://localhost:8000/api/v1/ingest-reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country }),
    });
    if (!res.ok) throw new Error(`Ingest failed: ${res.status}`);
    return res.json();
}
