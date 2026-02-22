"use client";

import { useMemo } from "react";
import { getEsriTileGridUrls } from "@/lib/esriTiles";
import type { RegionMarker } from "@/data/majorCities";

const ZOOM = 15;
const GRID = 2; // 2x2 tiles = 512x512 view

interface SatelliteRegionViewProps {
  region: RegionMarker;
}

export default function SatelliteRegionView({ region }: SatelliteRegionViewProps) {
  const tileUrls = useMemo(
    () => getEsriTileGridUrls(region.lat, region.lng, ZOOM, GRID),
    [region.lat, region.lng]
  );

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-400 uppercase tracking-wider">
        Satellite imagery — {region.name}, {region.countryCode}
      </p>
      <p className="text-xs text-gray-500">
        Esri World Imagery (same source as backend ground verifier). Click a region marker to view another area.
      </p>
      <div
        className="rounded-lg overflow-hidden border border-white/10 bg-black/40"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${GRID}, 256px)`,
          gridTemplateRows: `repeat(${GRID}, 256px)`,
          width: GRID * 256,
          maxWidth: "100%",
        }}
      >
        {tileUrls.flat().map((url, i) => (
          <img
            key={i}
            src={url}
            alt={`Tile ${i + 1}`}
            className="block w-full h-full object-cover"
            loading="lazy"
            crossOrigin="anonymous"
          />
        ))}
      </div>
    </div>
  );
}
