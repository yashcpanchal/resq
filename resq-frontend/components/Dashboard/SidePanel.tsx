"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Crosshair, Loader2, ExternalLink, ShieldAlert, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { scoreToColor } from "@/lib/utils";
import { fetchTacticalAnalysis, type TacticalAnalysisResult, fetchSafetyReport } from "@/lib/api";

interface SidePanelProps {
    country: string | null;
    score: number;
    lat?: number;
    lng?: number;
    onClose: () => void;
}

function scoreBadge(score: number) {
    if (score < 0) return { label: "No Data", variant: "secondary" as const };
    if (score < 0.3) return { label: "Critical", variant: "destructive" as const };
    if (score < 0.6) return { label: "Underfunded", variant: "default" as const };
    return { label: "Adequate", variant: "secondary" as const };
}

const safetyCache: Record<string, string> = {};

function FormattedBriefing({ text }: { text: string }) {
    if (!text) return null;
    let parts: { id: number, title: string, body: string }[] = [];

    // If it's the raw fallback data
    if (text.includes("---")) {
        const chunks = text.split("---").map(p => p.trim()).filter(Boolean);
        parts = chunks.map((part, i) => {
            let content = part.replace(/^\[\d+\]\s*/, "").trim();
            if (content.startsWith("Source: Raw retrieved data")) return null;
            let category = "Intel Report";
            const catMatch = content.match(/^\[(.*?)\]\s*([\s\S]*)/);
            if (catMatch) {
                category = catMatch[1];
                content = catMatch[2];
            }
            return { id: i, title: category, body: content };
        }).filter(Boolean) as any;
    } else {
        const paragraphs = text.split(/\n\n+/).map(p => p.trim()).filter(Boolean);
        let currentTitle = "Operational Context";
        let currentBody: string[] = [];
        for (const p of paragraphs) {
            const headingMatch = p.match(/^#+\s+(.*)$/) || p.match(/^\*\*(.*?)\*\*$/) || p.match(/^([A-Z][a-zA-Z\s]+):$/);
            if (headingMatch && p.length < 120) {
                if (currentBody.length > 0) {
                    parts.push({ id: parts.length, title: currentTitle, body: currentBody.join("\n\n") });
                    currentBody = [];
                }
                currentTitle = headingMatch[1].replace(/\*\*/g, "");
            } else {
                currentBody.push(p.replace(/^\*\*(.*?)\*\*\s*/, "$1: "));
            }
        }
        if (currentBody.length > 0) {
            parts.push({ id: parts.length, title: currentTitle, body: currentBody.join("\n\n") });
        }
    }

    return (
        <div className="space-y-3 mt-2 max-h-[400px] overflow-y-auto [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-white/10 hover:[&::-webkit-scrollbar-thumb]:bg-white/20 [&::-webkit-scrollbar-thumb]:rounded-full pr-1">
            {parts.map(p => (
                <div key={p.id} className="p-3 rounded-lg bg-white/5 border border-white/10 space-y-1.5">
                    <p className="text-[11px] font-bold text-blue-400 uppercase tracking-wider">{p.title}</p>
                    <div className="text-[12px] text-gray-300 leading-relaxed whitespace-pre-wrap">
                        {p.body}
                    </div>
                </div>
            ))}
        </div>
    );
}

export default function SidePanel({ country, score, lat, lng, onClose }: SidePanelProps) {
    const badge = scoreBadge(score);
    const hasCoords = lat !== undefined && lng !== undefined;

    const [tacticalState, setTacticalState] = useState<
        "idle" | "loading" | "done" | "error"
    >("idle");
    const [tacticalResult, setTacticalResult] = useState<TacticalAnalysisResult | null>(null);
    const [tacticalError, setTacticalError] = useState("");

    const [safetyState, setSafetyState] = useState<"idle" | "loading" | "done" | "error">("idle");
    const [safetyReport, setSafetyReport] = useState<string | null>(null);

    useEffect(() => {
        setTacticalState("idle");
        setTacticalResult(null);
        setTacticalError("");
        setSafetyState("idle");
        setSafetyReport(null);

        if (hasCoords) {
            loadSafety(lat!, lng!);
        }
    }, [country, lat, lng]);

    const loadSafety = async (lat: number, lng: number) => {
        const key = `${lat.toFixed(4)},${lng.toFixed(4)}`;
        if (safetyCache[key]) {
            setSafetyReport(safetyCache[key]);
            setSafetyState("done");
            return;
        }

        setSafetyState("loading");
        try {
            const { report } = await fetchSafetyReport(lat, lng);
            safetyCache[key] = report;
            setSafetyReport(report);
            setSafetyState("done");
        } catch (err) {
            console.error("Safety fetch failed:", err);
            setSafetyState("error");
        }
    };

    const runAnalysis = async () => {
        if (!hasCoords) return;
        setTacticalState("loading");
        setTacticalError("");
        try {
            const result = await fetchTacticalAnalysis(lat!, lng!, country ?? "Location");
            setTacticalResult(result);
            setTacticalState("done");
        } catch (err) {
            setTacticalError(err instanceof Error ? err.message : "Analysis failed");
            setTacticalState("error");
        }
    };

    const tacticalUrl = hasCoords
        ? `/tactical?lat=${lat}&lng=${lng}&name=${encodeURIComponent(country ?? "Location")}`
        : null;

    return (
        <AnimatePresence>
            {country && (
                <motion.div
                    key="side-panel"
                    initial={{ x: "100%", opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    exit={{ x: "100%", opacity: 0 }}
                    transition={{ type: "spring", damping: 26, stiffness: 200 }}
                    className="absolute right-0 top-0 z-30 h-full w-[380px] max-w-full"
                >
                    <div className="h-full overflow-y-auto p-4">
                        <Card className="bg-gray-950/80 backdrop-blur-xl border-white/10 text-white shadow-2xl">
                            <CardHeader className="flex flex-row items-start justify-between pb-2">
                                <div>
                                    <CardTitle className="text-xl font-bold">{country}</CardTitle>
                                    <Badge variant={badge.variant} className="mt-1">
                                        {badge.label}
                                    </Badge>
                                </div>
                                <button
                                    onClick={onClose}
                                    className="rounded-full p-1.5 hover:bg-white/10 transition"
                                >
                                    <X size={18} />
                                </button>
                            </CardHeader>

                            <CardContent className="space-y-5 pt-2">
                                {/* Funding Score Gauge */}
                                <div>
                                    <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">
                                        Funding Score
                                    </p>
                                    <div className="relative h-3 rounded-full bg-gray-800 overflow-hidden">
                                        <motion.div
                                            initial={{ width: 0 }}
                                            animate={{ width: `${Math.max(score, 0) * 100}%` }}
                                            transition={{ duration: 0.8, ease: "easeOut" }}
                                            className="h-full rounded-full"
                                            style={{
                                                background: score >= 0 ? scoreToColor(score) : "#555",
                                            }}
                                        />
                                    </div>
                                    <p className="text-right text-sm mt-1 font-mono" style={{ color: score >= 0 ? scoreToColor(score) : "#888" }}>
                                        {score >= 0 ? `${(score * 100).toFixed(1)}%` : "N/A"}
                                    </p>
                                </div>

                                {/* Actian Safety Briefing (Layer 3) */}
                                {hasCoords && (
                                    <div className="space-y-3 border-t border-white/10 pt-4">
                                        <div className="flex items-center gap-2">
                                            <ShieldAlert size={14} className="text-blue-400" />
                                            <p className="text-xs text-blue-400 uppercase tracking-wider">
                                                Operational Context Briefing
                                            </p>
                                        </div>

                                        {safetyState === "loading" && (
                                            <div className="flex items-center gap-3 py-4 px-3 rounded-lg bg-blue-500/5 border border-blue-500/10">
                                                <Loader2 size={16} className="animate-spin text-blue-400" />
                                                <p className="text-xs text-gray-400 italic">Synthesizing intelligence...</p>
                                            </div>
                                        )}

                                        {safetyState === "done" && safetyReport && (
                                            <FormattedBriefing text={safetyReport} />
                                        )}

                                        {safetyState === "error" && (
                                            <div className="rounded-lg bg-red-500/5 border border-red-500/10 p-3 flex items-start gap-2">
                                                <Info size={14} className="text-red-400 mt-0.5" />
                                                <p className="text-xs text-red-400/80 italic">Briefing unavailable. Country ingestion may still be in progress.</p>
                                            </div>
                                        )}
                                    </div>
                                )}


                            </CardContent>
                        </Card>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
