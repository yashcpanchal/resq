"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { scoreToColor } from "@/lib/utils";

interface SidePanelProps {
    country: string | null;
    score: number;
    onClose: () => void;
}

function scoreBadge(score: number) {
    if (score < 0) return { label: "No Data", variant: "secondary" as const };
    if (score < 0.3) return { label: "Critical", variant: "destructive" as const };
    if (score < 0.6) return { label: "Underfunded", variant: "default" as const };
    return { label: "Adequate", variant: "secondary" as const };
}

export default function SidePanel({ country, score, onClose }: SidePanelProps) {
    const badge = scoreBadge(score);

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

                                {/* Info section */}
                                <div className="space-y-3">
                                    <div className="rounded-lg bg-white/5 p-3">
                                        <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">
                                            Interpretation
                                        </p>
                                        <p className="text-sm text-gray-200 leading-relaxed">
                                            {score < 0 &&
                                                "No funding data available for this country."}
                                            {score >= 0 &&
                                                score < 0.3 &&
                                                "This country is critically underfunded. Humanitarian operations may be severely hampered."}
                                            {score >= 0.3 &&
                                                score < 0.6 &&
                                                "Funding covers less than 60% of requirements. Significant gaps remain in aid delivery."}
                                            {score >= 0.6 &&
                                                score < 0.85 &&
                                                "Funding is moderate but gaps persist in some sectors."}
                                            {score >= 0.85 &&
                                                "Funding requirements are largely met for this country."}
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
