import type { HullType } from "@/types";
import { boatIconFor, ICON_OUTLINE } from "./boatIcons";

/** A class's replay-map drawing as an inline preview, bow up — the same parts
 * the map marker paints, rendered as React elements. */
export function BoatSilhouette({
  silhouette,
  hullType,
  height,
  color = "var(--sf-primary)",
}: {
  silhouette: string | null | undefined;
  hullType?: HullType | null;
  /** Defaults to the drawing's own map height. */
  height?: number;
  color?: string;
}) {
  const icon = boatIconFor(silhouette, hullType);
  const h = height ?? icon.height;
  return (
    <svg
      viewBox={icon.viewBox}
      width={Math.round(h * icon.aspect)}
      height={h}
      aria-hidden="true"
      style={{ color, overflow: "visible", flexShrink: 0 }}
    >
      <g fill="currentColor" stroke={ICON_OUTLINE} strokeWidth={icon.stroke} strokeLinejoin="round">
        {icon.parts.map((part, i) => {
          const stroke = part.outline === false ? "none" : undefined;
          return part.tint ? (
            <g key={i}>
              <path d={part.d} fill="#fff" stroke="none" vectorEffect="non-scaling-stroke" />
              <path d={part.d} fillOpacity={0.35} stroke={stroke} vectorEffect="non-scaling-stroke" />
            </g>
          ) : (
            <path key={i} d={part.d} stroke={stroke} vectorEffect="non-scaling-stroke" />
          );
        })}
      </g>
    </svg>
  );
}
