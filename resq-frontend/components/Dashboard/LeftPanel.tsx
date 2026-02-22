"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X, MapPin, Satellite } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import SatelliteRegionView from "./SatelliteRegionView";
import type { RegionMarker } from "@/data/majorCities";

interface LeftPanelProps {
  /** Country name when a country is selected (for crisis placeholder). */
  countryName: string | null;
  /** When a region/city marker is clicked, show satellite view instead of crisis text. */
  selectedRegion: RegionMarker | null;
  onClose: () => void;
  onClearRegion: () => void;
}

export default function LeftPanel({
  countryName,
  selectedRegion,
  onClose,
  onClearRegion,
}: LeftPanelProps) {
  const isOpen = Boolean(countryName || selectedRegion);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="left-panel"
          initial={{ x: "-100%", opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: "-100%", opacity: 0 }}
          transition={{ type: "spring", damping: 26, stiffness: 200 }}
          className="absolute left-0 top-0 z-30 h-full w-[380px] max-w-full"
        >
          <div className="h-full overflow-y-auto p-4">
            <Card className="bg-gray-950/80 backdrop-blur-xl border-white/10 text-white shadow-2xl">
              <CardHeader className="flex flex-row items-start justify-between pb-2">
                <div className="flex items-center gap-2">
                  {selectedRegion ? (
                    <>
                      <Satellite className="h-5 w-5 text-sky-400" />
                      <CardTitle className="text-xl font-bold">
                        {selectedRegion.name}
                      </CardTitle>
                    </>
                  ) : (
                    <>
                      <MapPin className="h-5 w-5 text-amber-400" />
                      <CardTitle className="text-xl font-bold">
                        Crisis overview
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
                      key="satellite"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                    >
                      <SatelliteRegionView region={selectedRegion} />
                    </motion.div>
                  ) : (
                    <motion.div
                      key="crisis"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="space-y-3"
                    >
                      <p className="text-xs text-gray-400 uppercase tracking-wider">
                        Current humanitarian crises
                      </p>
                      <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3">
                        <p className="text-sm text-gray-200 leading-relaxed italic">
                          {countryName
                            ? `Crisis description data will be provided here for ${countryName}. This section will show a short summary of ongoing humanitarian situations (displacement, food insecurity, health emergencies, etc.) in the selected region.`
                            : "Select a country on the globe to see crisis overview, or click a region marker to view satellite imagery of that area."}
                        </p>
                      </div>
                      <p className="text-xs text-gray-500">
                        Click a city/region marker on the globe to replace this panel with satellite images of that area.
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </CardContent>
            </Card>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
