/**
 * API helpers — all calls go through the Next.js rewrite proxy (/api → backend).
 */

export async function fetchFundingScores(): Promise<Record<string, number>> {
    const res = await fetch("/api/funding-scores");
    if (!res.ok) throw new Error(`Failed to fetch funding scores: ${res.status}`);
    return res.json();
}
