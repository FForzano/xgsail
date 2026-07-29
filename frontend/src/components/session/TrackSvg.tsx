import { useMemo } from "react";
import { smoothTrackLine, type Track } from "@/components/race/raceModel";

// Same downsample cap and extra shrink as the worker-side thumbnail renderer
// (workers/process_upload/thumbnail.py) — kept in sync so a track looks the
// same whether it comes from the PNG thumbnail or from this SVG.
const MAX_POINTS = 800;
const ZOOM_OUT = 0.9;

function downsample(pts: Track["pts"]): Track["pts"] {
  const step = Math.max(1, Math.floor(pts.length / MAX_POINTS));
  return step === 1 ? pts : pts.filter((_, i) => i % step === 0);
}

/** The session's GPS track drawn as an inline SVG polyline, in the caller's
 * chosen color. Used by the share image (see ShareCard) instead of the
 * backend-rendered thumbnail PNG: no remote image means no CORS/presigned-URL
 * failure during rasterization, and the color becomes a user choice.
 *
 * Flat equirectangular projection with cos-latitude correction — the same
 * math as workers/process_upload/thumbnail.py `_render()`, which is plenty at
 * the few-km scale of one session. */
export function TrackSvg({
  track,
  color,
  width,
  height,
  padding = 0,
  strokeWidth = 10,
  className,
}: {
  track: Track;
  color: string;
  width: number;
  height: number;
  /** Empty margin (px) kept around the drawn line, on top of ZOOM_OUT. */
  padding?: number;
  strokeWidth?: number;
  className?: string;
}) {
  const points = useMemo(() => {
    const line = smoothTrackLine(downsample(track.pts));
    if (line.length < 2) return null;

    let minLat = Infinity;
    let maxLat = -Infinity;
    let minLon = Infinity;
    let maxLon = -Infinity;
    for (const [lat, lon] of line) {
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
      if (lon < minLon) minLon = lon;
      if (lon > maxLon) maxLon = lon;
    }
    const lonScale = Math.cos(((minLat + maxLat) / 2) * (Math.PI / 180)) || 1;

    const latSpan = Math.max(maxLat - minLat, 1e-9);
    const lonSpan = Math.max((maxLon - minLon) * lonScale, 1e-9);
    const innerW = width - 2 * padding;
    const innerH = height - 2 * padding;
    const scale = Math.min(innerW / lonSpan, innerH / latSpan) * ZOOM_OUT;
    const offX = padding + (innerW - lonSpan * scale) / 2;
    const offY = padding + (innerH - latSpan * scale) / 2;

    return line
      .map(([lat, lon]) => {
        const x = offX + (lon - minLon) * lonScale * scale;
        // Flip: SVG Y grows downward, latitude grows upward.
        const y = height - offY - (lat - minLat) * scale;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [track, width, height, padding]);

  if (!points) return null;

  return (
    <svg
      className={className}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      aria-hidden="true"
    >
      <polyline
        points={points}
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
