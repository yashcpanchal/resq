"use client";

/**
 * TacticalGrid — 3×3 Military HUD overlay with real OSM features.
 *
 * Colors are driven by OSM feature type (what the feature IS), not
 * by what the VLM said.  The VLM sector descriptions appear in
 * tooltips only.
 *
 * Category colors:
 *   staging    (green)  — open land, parks, fields, meadows, natural areas
 *   risk       (red)    — buildings, dense residential areas
 *   access     (amber)  — roads, paths, tracks
 *   operations (blue)   — schools, hospitals, community centres
 *
 * Import with: `dynamic(() => import(...), { ssr: false })`.
 */

import { useEffect, useMemo, useCallback } from "react";
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  Rectangle,
  Tooltip,
  useMap,
} from "react-leaflet";
import type {
  LatLngBoundsExpression,
  PathOptions,
  Layer,
} from "leaflet";
import L from "leaflet";
import type {
  Feature,
  FeatureCollection,
  Geometry,
} from "geojson";
import "leaflet/dist/leaflet.css";

/* ================================================================== */
/*  Grid geometry                                                      */
/* ================================================================== */

const GRID_TAGS = ["NW", "N", "NE", "W", "C", "E", "SW", "S", "SE"] as const;
type GridTag = (typeof GRID_TAGS)[number];

const GRID_OFFSETS: Record<GridTag, [dLat: number, dLng: number]> = {
  NW: [+1, -1], N: [+1, 0], NE: [+1, +1],
  W:  [ 0, -1], C: [ 0, 0], E:  [ 0, +1],
  SW: [-1, -1], S: [-1, 0], SE: [-1, +1],
};

const CELL_DEG = 0.001;

/* ================================================================== */
/*  Category system — driven by feature type, NOT VLM text             */
/* ================================================================== */

const COLORS: Record<string, string> = {
  staging:    "#00ff00",
  risk:       "#ff4444",
  access:     "#ffcc00",
  operations: "#00aaff",
  unknown:    "#888888",
};

const LABELS: Record<string, string> = {
  staging:    "STAGING / OPEN",
  risk:       "STRUCTURES",
  access:     "ACCESS ROUTES",
  operations: "OPERATIONS",
  unknown:    "UNCLASSIFIED",
};

/* ================================================================== */
/*  Keyword classification (fallback only — no GeoJSON)                */
/* ================================================================== */

const CAT_KEYWORDS: Record<string, string[]> = {
  staging: [
    "flat", "clearing", "empty", "staging", "field", "open",
    "courtyard", "parking", "landing", "helicopter", "camp",
    "meadow", "grass", "park", "pitch", "recreation", "vacant",
  ],
  risk: [
    "building", "structure", "dense", "residential", "housing",
  ],
  access: [
    "road", "access", "path", "route", "highway", "street",
    "vehicle", "driveway", "entrance", "entry", "gate",
  ],
  operations: [
    "school", "hospital", "clinic", "church", "mosque",
    "community", "government", "police", "fire",
  ],
};

function classifyText(text: string): string {
  const lower = text.toLowerCase();
  let best = "unknown";
  let bestHits = 0;
  for (const [cat, kws] of Object.entries(CAT_KEYWORDS)) {
    const hits = kws.reduce((n, kw) => n + (lower.includes(kw) ? 1 : 0), 0);
    if (hits > bestHits) {
      best = cat;
      bestHits = hits;
    }
  }
  return best;
}

/* ================================================================== */
/*  Sector bounding-box computation                                    */
/* ================================================================== */

interface SectorInfo {
  tag: GridTag;
  description: string;
  category: string;
  color: string;
  bounds: LatLngBoundsExpression;
}

function buildSectors(
  sectors: Record<string, string>,
  center: { lat: number; lng: number },
): SectorInfo[] {
  const half = CELL_DEG / 2;
  return GRID_TAGS.map((tag): SectorInfo => {
    const desc = sectors[tag] ?? "No intel";
    const cat = sectors[tag] ? classifyText(desc) : "unknown";
    const [dLat, dLng] = GRID_OFFSETS[tag];
    const cLat = center.lat + dLat * CELL_DEG;
    const cLng = center.lng + dLng * CELL_DEG;
    return {
      tag,
      description: desc,
      category: cat,
      color: COLORS[cat] ?? COLORS.unknown,
      bounds: [
        [cLat - half, cLng - half],
        [cLat + half, cLng + half],
      ],
    };
  });
}

function parseAnalysisToSectors(raw: string): Record<string, string> {
  const tagRe = new RegExp(
    `\\[(${GRID_TAGS.join("|")})\\]\\s*([\\s\\S]*?)(?=\\[(?:${GRID_TAGS.join("|")})\\]|$)`,
    "gi",
  );
  const result: Record<string, string> = {};
  let m: RegExpExecArray | null;
  while ((m = tagRe.exec(raw)) !== null) {
    const tag = m[1].toUpperCase();
    if (!(tag in result)) {
      result[tag] = m[2].trim().replace(/\s+/g, " ");
    }
  }
  return result;
}

/* ================================================================== */
/*  Feature color — always from the `category` property (set by       */
/*  the backend from OSM tags), never from VLM text                    */
/* ================================================================== */

function featureColor(props: Record<string, unknown>): string {
  const category = props.category as string | undefined;
  return COLORS[category ?? "unknown"] ?? COLORS.unknown;
}

/* ================================================================== */
/*  Fit map                                                            */
/* ================================================================== */

function FitGrid({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap();
  useEffect(() => {
    const pad = CELL_DEG * 1.85;
    map.fitBounds([
      [lat - pad, lng - pad],
      [lat + pad, lng + pad],
    ]);
  }, [map, lat, lng]);
  return null;
}

/* ================================================================== */
/*  HUD corner brackets                                                */
/* ================================================================== */

function CornerBracket({
  position,
}: {
  position: "top-left" | "top-right" | "bottom-left" | "bottom-right";
}) {
  const isTop = position.startsWith("top");
  const isLeft = position.includes("left");
  const S = 20;
  const posStyle: React.CSSProperties = {
    position: "absolute",
    zIndex: 1000,
    pointerEvents: "none",
    ...(isTop ? { top: 2 } : { bottom: 2 }),
    ...(isLeft ? { left: 2 } : { right: 2 }),
  };
  const hx1 = isLeft ? 0 : S;
  const hx2 = isLeft ? S : 0;
  const hy = isTop ? 0 : S;
  const vx = isLeft ? 0 : S;
  const vy1 = isTop ? 0 : S;
  const vy2 = isTop ? S : 0;

  return (
    <svg width={S} height={S} style={posStyle}>
      <line x1={hx1} y1={hy} x2={hx2} y2={hy} stroke="rgba(0,255,136,0.4)" strokeWidth={1.5} />
      <line x1={vx} y1={vy1} x2={vx} y2={vy2} stroke="rgba(0,255,136,0.4)" strokeWidth={1.5} />
    </svg>
  );
}

/* ================================================================== */
/*  TacticalGrid                                                       */
/* ================================================================== */

export interface TacticalGridProps {
  center: { lat: number; lng: number };
  analysis: string;
  sectors?: Record<string, string>;
  geojson?: FeatureCollection;
}

export default function TacticalGrid({
  center,
  analysis,
  sectors: sectorsProp,
  geojson,
}: TacticalGridProps) {
  const resolvedSectors = useMemo(
    () => (sectorsProp && Object.keys(sectorsProp).length > 0)
      ? sectorsProp
      : parseAnalysisToSectors(analysis),
    [sectorsProp, analysis],
  );

  const sectorInfos = useMemo(
    () => buildSectors(resolvedSectors, center),
    [resolvedSectors, center],
  );

  const hasFeatures = geojson && geojson.features && geojson.features.length > 0;

  const activeCats = useMemo(() => {
    const cats = new Set<string>();
    if (hasFeatures) {
      for (const feat of geojson!.features) {
        const cat = (feat.properties?.category as string) ?? "unknown";
        if (cat !== "unknown") cats.add(cat);
      }
    } else {
      for (const s of sectorInfos) {
        if (s.description !== "No intel") cats.add(s.category);
      }
    }
    return [...cats].sort();
  }, [hasFeatures, geojson, sectorInfos]);

  const styleFeature = useCallback(
    (feature?: Feature<Geometry>) => {
      if (!feature) return {};
      const p = (feature.properties ?? {}) as Record<string, unknown>;
      const color = featureColor(p);
      const category = p.category as string | undefined;
      const ftype = p.feature_type as string | undefined;
      const isLine = ftype === "highway";
      const isOps = category === "operations";

      const opts: PathOptions = {
        color,
        weight: isLine ? 2.5 : isOps ? 2 : 1,
        opacity: 0.9,
        fillColor: color,
        fillOpacity: isLine ? 0 : isOps ? 0.45 : 0.35,
        ...(isOps ? { dashArray: "5 3" } : {}),
      };
      return opts;
    },
    [],
  );

  const onEachFeature = useCallback(
    (feature: Feature<Geometry>, layer: Layer) => {
      const p = (feature.properties ?? {}) as Record<string, unknown>;
      const sector = p.sector as string | undefined;
      const category = (p.category as string) ?? "unknown";
      const name = p.name as string | undefined;
      const sectorDesc =
        (p.sector_description as string | undefined) ??
        (sector ? resolvedSectors[sector] : undefined);
      const color = featureColor(p);

      const tooltip = L.tooltip({
        sticky: true,
        direction: "top",
        offset: [0, -6],
        className: "tg-tooltip",
      });

      const catLabel = LABELS[category] ?? "FEATURE";
      const sectorTag = sector ? `[${sector}]` : "";
      const nameHtml = name ? `<div class="tg-tip-name">${name}</div>` : "";
      const descHtml = sectorDesc
        ? `<div class="tg-tip-body">${sectorDesc}</div>`
        : "";

      tooltip.setContent(
        `<div class="tg-tip-inner">
          <div class="tg-tip-header" style="color:${color}">
            ${sectorTag} ${catLabel}
          </div>
          ${nameHtml}
          ${descHtml}
        </div>`,
      );

      layer.bindTooltip(tooltip);
    },
    [resolvedSectors],
  );

  return (
    <div
      className="relative w-full h-full overflow-hidden"
      style={{ fontFamily: "'JetBrains Mono', 'Fira Code', Consolas, monospace" }}
    >
      <style>{HUD_STYLES}</style>

      {/* HUD top bar */}
      <div className="absolute top-0 inset-x-0 z-[1000] flex items-center justify-between px-4 py-2 bg-gradient-to-b from-black/80 via-black/40 to-transparent pointer-events-none select-none">
        <div className="flex items-center gap-2">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-400 shadow-[0_0_6px_rgba(0,255,136,0.6)] animate-pulse" />
          <span className="text-[11px] tracking-[0.15em] text-green-300/90 uppercase font-bold">
            Tactical Grid — Active
          </span>
        </div>
        <span className="text-[10px] text-gray-500 tabular-nums tracking-wide">
          {center.lat.toFixed(5)}°N {center.lng.toFixed(5)}°E
        </span>
      </div>

      {/* Map */}
      <MapContainer
        center={[center.lat, center.lng]}
        zoom={17}
        zoomControl={false}
        attributionControl={false}
        style={{ width: "100%", height: "100%", background: "#060a10" }}
      >
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          maxZoom={19}
        />
        <FitGrid lat={center.lat} lng={center.lng} />

        {/* Reference grid lines */}
        {sectorInfos.map((s) => (
          <Rectangle
            key={`grid-${s.tag}`}
            bounds={s.bounds}
            pathOptions={{
              color: "rgba(0, 255, 136, 0.18)",
              weight: 0.8,
              fillColor: "transparent",
              fillOpacity: 0,
              dashArray: "4 4",
            }}
          >
            {!hasFeatures && (
              <Tooltip sticky className="tg-tooltip" direction="top" offset={[0, -6]}>
                <div className="tg-tip-inner">
                  <div className="tg-tip-header" style={{ color: s.color }}>
                    [{s.tag}]&ensp;{LABELS[s.category] ?? "SECTOR"}
                  </div>
                  <div className="tg-tip-body">{s.description}</div>
                </div>
              </Tooltip>
            )}
          </Rectangle>
        ))}

        {/* Sector rectangles (fallback when no GeoJSON) */}
        {!hasFeatures &&
          sectorInfos.map((s) => (
            <Rectangle
              key={`fill-${s.tag}`}
              bounds={s.bounds}
              pathOptions={{
                color: s.color,
                weight: 1,
                opacity: 0.7,
                fillColor: s.color,
                fillOpacity: 0.25,
                dashArray: s.tag === "C" ? undefined : "6 3",
              }}
            >
              <Tooltip sticky className="tg-tooltip" direction="top" offset={[0, -6]}>
                <div className="tg-tip-inner">
                  <div className="tg-tip-header" style={{ color: s.color }}>
                    [{s.tag}]&ensp;{LABELS[s.category] ?? "SECTOR"}
                  </div>
                  <div className="tg-tip-body">{s.description}</div>
                </div>
              </Tooltip>
            </Rectangle>
          ))}

        {/* Real OSM features */}
        {hasFeatures && (
          <GeoJSON
            key={`geo-${center.lat}-${center.lng}`}
            data={geojson!}
            style={styleFeature}
            onEachFeature={onEachFeature}
          />
        )}
      </MapContainer>

      {/* Crosshair */}
      <div className="absolute inset-0 z-[999] pointer-events-none flex items-center justify-center">
        <svg width="32" height="32" viewBox="0 0 32 32" className="opacity-50">
          <line x1="16" y1="0"  x2="16" y2="12" stroke="#00ff88" strokeWidth="0.8" />
          <line x1="16" y1="20" x2="16" y2="32" stroke="#00ff88" strokeWidth="0.8" />
          <line x1="0"  y1="16" x2="12" y2="16" stroke="#00ff88" strokeWidth="0.8" />
          <line x1="20" y1="16" x2="32" y2="16" stroke="#00ff88" strokeWidth="0.8" />
          <circle cx="16" cy="16" r="2" stroke="#00ff88" strokeWidth="0.6" fill="none" />
        </svg>
      </div>

      {/* Corner brackets */}
      <CornerBracket position="top-left" />
      <CornerBracket position="top-right" />
      <CornerBracket position="bottom-left" />
      <CornerBracket position="bottom-right" />

      {/* Legend */}
      <div className="absolute bottom-3 left-3 z-[1000] flex items-center gap-4 rounded bg-black/75 backdrop-blur-sm border border-white/[0.06] px-3 py-1.5 pointer-events-none select-none">
        {activeCats.map((cat) => (
          <div key={cat} className="flex items-center gap-1.5">
            <span
              className="inline-block w-2 h-2 rounded-[2px]"
              style={{ background: COLORS[cat], boxShadow: `0 0 4px ${COLORS[cat]}44` }}
            />
            <span
              className="text-[9px] uppercase tracking-[0.12em] font-semibold"
              style={{ color: COLORS[cat] }}
            >
              {LABELS[cat]}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ================================================================== */
/*  Scoped Leaflet CSS                                                 */
/* ================================================================== */

const HUD_STYLES = `
  .tg-tooltip {
    background: rgba(2, 8, 16, 0.94) !important;
    border: 1px solid rgba(0, 255, 136, 0.22) !important;
    border-radius: 2px !important;
    padding: 0 !important;
    box-shadow:
      0 0 20px rgba(0, 255, 100, 0.05),
      0 4px 16px rgba(0, 0, 0, 0.6) !important;
  }
  .tg-tooltip::before {
    border-top-color: rgba(0, 255, 136, 0.22) !important;
  }
  .tg-tip-inner {
    padding: 8px 12px;
    max-width: 280px;
    font-family: "JetBrains Mono", "Fira Code", Consolas, monospace;
  }
  .tg-tip-header {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 2px;
    white-space: nowrap;
  }
  .tg-tip-name {
    font-size: 11px;
    font-weight: 500;
    color: #e0e8f0;
    margin-bottom: 4px;
  }
  .tg-tip-body {
    font-size: 10px;
    line-height: 1.55;
    color: #a8bdd0;
  }
  .leaflet-container {
    background: #060a10 !important;
  }
`;