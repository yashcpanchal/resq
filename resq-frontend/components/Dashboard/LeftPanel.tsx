"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  MapPin,
  AlertTriangle,
  Info,
  Users,
  Wallet,
  Loader2,
  Satellite,
  Maximize2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import SatelliteRegionView from "./SatelliteRegionView";
import type { RegionMarker } from "@/data/majorCities";
import type { CityCrisis, CrisisNeed } from "@/lib/api";

interface LeftPanelProps {
  countryName: string | null;
  selectedRegion: (RegionMarker & Partial<CityCrisis>) | null;
  discoveredCrises: CityCrisis[];
  loadingCrises: boolean;
  onClose: () => void;
  onClearRegion: () => void;
}

export default function LeftPanel({
  countryName,
  selectedRegion,
  discoveredCrises,
  loadingCrises,
  onClose,
  onClearRegion,
}: LeftPanelProps) {
  const isOpen = Boolean(countryName || selectedRegion);
  const [enlargedMap, setEnlargedMap] = useState(false);

  const isCrisisMarker =
    selectedRegion &&
    "needs" in selectedRegion &&
    Array.isArray(selectedRegion.needs) &&
    selectedRegion.needs.length > 0;

  // Build the tactical page URL from the city's coordinates
  const tacticalUrl =
    selectedRegion?.lat && selectedRegion?.lng
      ? `/tactical?lat=${selectedRegion.lat}&lng=${selectedRegion.lng}&name=${encodeURIComponent(selectedRegion.name)}&embed=true`
      : null;

  return (
    <>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="left-panel"
            initial={{ x: "-100%", opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "-100%", opacity: 0 }}
            transition={{ type: "spring", damping: 26, stiffness: 200 }}
            className="absolute left-0 top-0 z-30 h-full w-[400px] max-w-full"
          >
            <div className="h-full overflow-y-auto p-4 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-white/20 transition-colors">
              <Card className="bg-gray-950/90 backdrop-blur-2xl border-white/10 text-white shadow-2xl">
                <CardHeader className="flex flex-row items-start justify-between pb-2">
                  <div className="flex items-center gap-2">
                    {selectedRegion ? (
                      <>
                        {isCrisisMarker ? (
                          <AlertTriangle className="h-5 w-5 text-amber-500" />
                        ) : (
                          <Satellite className="h-5 w-5 text-sky-400" />
                        )}
                        <CardTitle className="text-xl font-bold">
                          {selectedRegion.name}
                        </CardTitle>
                      </>
                    ) : (
                      <>
                        <MapPin className="h-5 w-5 text-amber-400" />
                        <CardTitle className="text-xl font-bold">
                          {countryName ?? "Crisis overview"}
                        </CardTitle>
                      </>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    {selectedRegion && (
                      <button
                        onClick={onClearRegion}
                        className="rounded-full p-1.5 hover:bg-white/10 transition text-gray-400 hover:text-white text-xs"
                        title="Back to crisis view"
                      >
                        Back
                      </button>
                    )}
                    <button
                      onClick={onClose}
                      className="rounded-full p-1.5 hover:bg-white/10 transition"
                    >
                      <X size={18} />
                    </button>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4 pt-2">
                  <AnimatePresence mode="wait">
                    {selectedRegion ? (
                      <motion.div
                        key={isCrisisMarker ? "crisis-detail" : "satellite"}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="space-y-6"
                      >
                        {isCrisisMarker ? (
                          <>
                            <CrisisDetailView needs={selectedRegion.needs!} />

                            {/* Tactical Map embed */}
                            {tacticalUrl && (
                              <div className="space-y-3 pt-2 border-t border-white/5">
                                <p className="text-xs text-gray-400 uppercase tracking-widest font-semibold flex items-center gap-2">
                                  <Satellite size={14} className="text-sky-400" />
                                  Tactical Map Analysis
                                </p>
                                <div
                                  className="relative group cursor-pointer rounded-lg overflow-hidden border border-white/10 hover:border-sky-500/50 transition-colors"
                                  onClick={() => setEnlargedMap(true)}
                                >
                                  <iframe
                                    src={tacticalUrl}
                                    className="w-full h-[280px] pointer-events-none"
                                    title="Tactical Map"
                                  />
                                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                                    <div className="bg-black/60 backdrop-blur p-2 rounded-full opacity-0 group-hover:opacity-100 transition-opacity">
                                      <Maximize2 size={16} className="text-white" />
                                    </div>
                                  </div>
                                  <p className="px-3 py-2 text-[10px] text-gray-400 italic bg-gray-950/80">
                                    Click to enlarge tactical view
                                  </p>
                                </div>
                              </div>
                            )}
                          </>
                        ) : (
                          <SatelliteRegionView region={selectedRegion as any} />
                        )}
                      </motion.div>
                    ) : (
                      <motion.div
                        key="overview"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="space-y-4"
                      >
                        {loadingCrises && (
                          <div className="flex items-center gap-3 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
                            <Loader2 size={18} className="animate-spin text-blue-400" />
                            <p className="text-sm text-blue-300">
                              Discovering crisis zones in {countryName}…
                            </p>
                          </div>
                        )}

                        {!loadingCrises && discoveredCrises.length > 0 && (
                          <div className="space-y-3">
                            <p className="text-xs text-gray-400 uppercase tracking-widest font-semibold">
                              {discoveredCrises.length} zones identified
                            </p>
                            {discoveredCrises.map((city, i) => (
                              <motion.div
                                key={city.name}
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: i * 0.05 }}
                                className="p-3 rounded-lg bg-white/5 border border-white/10 space-y-2"
                              >
                                <div className="flex items-center gap-2">
                                  <AlertTriangle size={14} className="text-amber-500 shrink-0" />
                                  <span className="text-sm font-semibold text-gray-100">
                                    {city.name}
                                  </span>
                                </div>
                                <div className="flex flex-wrap gap-1.5">
                                  {city.needs?.slice(0, 3).map((need, j) => (
                                    <span
                                      key={j}
                                      className={`text-[10px] px-2 py-0.5 rounded font-medium ${need.severity === "critical"
                                        ? "bg-red-500/20 text-red-400"
                                        : need.severity === "high"
                                          ? "bg-orange-500/20 text-orange-400"
                                          : "bg-blue-500/20 text-blue-400"
                                        }`}
                                    >
                                      {need.sector}
                                    </span>
                                  ))}
                                </div>
                              </motion.div>
                            ))}
                            <div className="flex items-start gap-2 text-xs text-gray-500 pt-1">
                              <Info size={14} className="mt-0.5 shrink-0" />
                              <p>
                                Click a marker on the globe to view detailed needs for
                                that zone.
                              </p>
                            </div>
                          </div>
                        )}

                        {!loadingCrises && discoveredCrises.length === 0 && countryName && (
                          <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3">
                            <p className="text-sm text-gray-200 leading-relaxed italic">
                              No crisis zones discovered for {countryName}. The
                              model may not have current data for this region.
                            </p>
                          </div>
                        )}

                        {!countryName && (
                          <div className="rounded-lg bg-gray-800/50 border border-white/10 p-3">
                            <p className="text-sm text-gray-300 leading-relaxed">
                              Select a country on the globe to discover crisis
                              zones, or click a city marker for satellite imagery.
                            </p>
                          </div>
                        )}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </CardContent>
              </Card>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Enlarged Tactical Map Modal — full interactive iframe */}
      <AnimatePresence>
        {enlargedMap && tacticalUrl && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm"
            onClick={() => setEnlargedMap(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="relative w-[90vw] h-[90vh] rounded-xl overflow-hidden border border-white/20 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => setEnlargedMap(false)}
                className="absolute top-3 right-3 z-10 bg-black/60 backdrop-blur p-2 rounded-full text-white hover:text-sky-400 transition-colors"
              >
                <X size={20} />
              </button>
              <iframe
                src={tacticalUrl}
                className="w-full h-full"
                title="Tactical Map — Enlarged"
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

/* ---------- Sub-component for crisis detail view ---------- */

function CrisisDetailView({ needs }: { needs: CrisisNeed[] }) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-400 uppercase tracking-widest font-semibold">
        Humanitarian Relief Assessment
      </p>
      {needs.map((need, i) => (
        <div
          key={i}
          className="space-y-2 p-3 rounded-lg bg-white/5 border border-white/10"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-gray-100">
              {need.sector}
            </span>
            <span
              className={`text-[10px] px-2 py-0.5 rounded uppercase font-bold tracking-tight ${need.severity === "critical"
                ? "bg-red-500/20 text-red-400"
                : need.severity === "high"
                  ? "bg-orange-500/20 text-orange-400"
                  : "bg-blue-500/20 text-blue-400"
                }`}
            >
              {need.severity}
            </span>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            {need.description}
          </p>
          <div className="flex flex-wrap gap-3 pt-1">
            {need.affected_population && (
              <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
                <Users size={12} className="text-gray-500" />
                <span>{need.affected_population}</span>
              </div>
            )}
            {need.funding_gap && (
              <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
                <Wallet size={12} className="text-gray-500" />
                <span>{need.funding_gap}</span>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
