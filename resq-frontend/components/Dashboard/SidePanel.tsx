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
    scoreDomain?: [number, number];
    lat?: number;
    lng?: number;
    onClose: () => void;
}

function scoreBadge(score: number) {
    if (isNaN(score)) return { label: "No Data", variant: "secondary" as const };
    if (score < -5000) return { label: "Critical", variant: "destructive" as const };
    if (score < 0) return { label: "Underfunded", variant: "default" as const };
    return { label: "Adequate", variant: "secondary" as const };
}

const safetyCache: Record<string, string> = {};

export default function SidePanel({ country, score, scoreDomain = [0, 1], lat, lng, onClose }: SidePanelProps) {
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
                                            animate={{
                                                width: !isNaN(score)
                                                    ? `${Math.min(Math.abs(score) / 100, 100)}%`
                                                    : "0%",
                                            }}
                                            transition={{ duration: 0.8, ease: "easeOut" }}
                                            className="h-full rounded-full"
                                            style={{
                                                background: !isNaN(score) ? scoreToColor(score, scoreDomain) : "#555",
                                            }}
                                        />
                                    </div>
                                    <p className="text-right text-sm mt-1 font-mono" style={{ color: !isNaN(score) ? scoreToColor(score, scoreDomain) : "#888" }}>
                                        {!isNaN(score) ? score.toFixed(0) : "N/A"}
                                    </p>
                                </div>

                                {/* Actian Safety Briefing (Layer 3) */}
                                {hasCoords && (
                                    <div className="space-y-3 border-t border-white/10 pt-4">
                                        <div className="flex items-center gap-2">
                                            <ShieldAlert size={14} className="text-blue-400" />
                                            <p className="text-xs text-blue-400 uppercase tracking-wider">
                                                Actian Safety Briefing
                                            </p>
                                        </div>

                                        {safetyState === "loading" && (
                                            <div className="flex items-center gap-3 py-4 px-3 rounded-lg bg-blue-500/5 border border-blue-500/10">
                                                <Loader2 size={16} className="animate-spin text-blue-400" />
                                                <p className="text-xs text-gray-400 italic">Synthesizing intelligence...</p>
                                            </div>
                                        )}

                                        {safetyState === "done" && safetyReport && (
                                            <div className="rounded-lg bg-white/5 border border-white/10 p-3 max-h-[300px] overflow-y-auto scrollbar-thin scrollbar-thumb-white/10">
                                                <div className="text-[13px] text-gray-200 leading-relaxed whitespace-pre-wrap font-sans">
                                                    {safetyReport.replace(/^## .*?\n/, "")}
                                                </div>
                                            </div>
                                        )}

                                        {safetyState === "error" && (
                                            <div className="rounded-lg bg-red-500/5 border border-red-500/10 p-3 flex items-start gap-2">
                                                <Info size={14} className="text-red-400 mt-0.5" />
                                                <p className="text-xs text-red-400/80 italic">Briefing unavailable. Country ingestion may still be in progress.</p>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Tactical Analysis Section */}
                                {hasCoords && (
                                    <div className="space-y-3 border-t border-white/10 pt-4">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <Crosshair size={14} className="text-green-400" />
                                                <p className="text-xs text-green-400 uppercase tracking-wider">
                                                    Tactical Analysis
                                                </p>
                                            </div>
                                            <span className="text-[10px] text-gray-600 font-mono tabular-nums">
                                                {lat!.toFixed(4)}°N {lng!.toFixed(4)}°E
                                            </span>
                                        </div>

                                        {tacticalState === "idle" && (
                                            <button
                                                onClick={runAnalysis}
                                                className="w-full flex items-center justify-center gap-2 rounded-lg bg-green-500/10 border border-green-500/20 px-4 py-2.5 text-sm text-green-400 hover:bg-green-500/20 transition"
                                            >
                                                <Crosshair size={14} />
                                                Run VLM Analysis
                                            </button>
                                        )}

                                        {tacticalState === "loading" && (
                                            <div className="flex flex-col items-center gap-2 py-6">
                                                <Loader2 size={24} className="animate-spin text-green-400" />
                                                <p className="text-xs text-gray-400">
                                                    Running Ollama VLM analysis...
                                                </p>
                                                <p className="text-[10px] text-gray-600">
                                                    This may take 30-120 seconds
                                                </p>
                                            </div>
                                        )}

                                        {tacticalState === "error" && (
                                            <div className="space-y-2">
                                                <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3">
                                                    <p className="text-xs text-red-400">
                                                        {tacticalError}
                                                    </p>
                                                </div>
                                                <button
                                                    onClick={runAnalysis}
                                                    className="w-full flex items-center justify-center gap-2 rounded-lg bg-white/5 px-4 py-2 text-xs text-gray-400 hover:bg-white/10 transition"
                                                >
                                                    Retry
                                                </button>
                                            </div>
                                        )}

                                        {tacticalState === "done" && tacticalResult && (
                                            <div className="space-y-3">
                                                {/* Annotated satellite thumbnail */}
                                                {tacticalResult.annotated_image && (
                                                    <div className="rounded-lg overflow-hidden border border-white/10">
                                                        <img
                                                            src={`data:image/jpeg;base64,${tacticalResult.annotated_image}`}
                                                            alt="Annotated satellite view"
                                                            className="w-full h-auto"
                                                        />
                                                    </div>
                                                )}

                                                {/* Sector summary */}
                                                {Object.keys(tacticalResult.sectors).length > 0 && (
                                                    <div className="rounded-lg bg-white/5 p-3 space-y-2">
                                                        <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">
                                                            Sector Summary
                                                        </p>
                                                        {Object.entries(tacticalResult.sectors)
                                                            .slice(0, 5)
                                                            .map(([tag, desc]) => (
                                                                <div key={tag} className="flex gap-2 text-xs">
                                                                    <span className="text-green-400/80 font-mono font-bold shrink-0">
                                                                        [{tag}]
                                                                    </span>
                                                                    <span className="text-gray-300 line-clamp-2">
                                                                        {desc}
                                                                    </span>
                                                                </div>
                                                            ))}
                                                        {Object.keys(tacticalResult.sectors).length > 5 && (
                                                            <p className="text-[10px] text-gray-600">
                                                                +{Object.keys(tacticalResult.sectors).length - 5} more sectors
                                                            </p>
                                                        )}
                                                    </div>
                                                )}

                                                {/* View Full Grid link */}
                                                {tacticalUrl && (
                                                    <a
                                                        href={tacticalUrl}
                                                        className="w-full flex items-center justify-center gap-2 rounded-lg bg-green-500/10 border border-green-500/20 px-4 py-2.5 text-sm text-green-400 hover:bg-green-500/20 transition"
                                                    >
                                                        <ExternalLink size={14} />
                                                        View Full Tactical Grid
                                                    </a>
                                                )}
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
