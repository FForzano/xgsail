import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Area, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TrueWindPoint } from "@/types";
import { useTimeState } from "@/stores/timeController";
import { fmtKnots, fmtTime, splitKnots } from "@/utils/format";
import { BASE_RGB, RAMP_LIGHT, rgbCss } from "@/utils/colorRamp";
import { windSeries, windSummary } from "@/utils/windStats";
import { StatTile, StatTiles } from "./StatTile";
import styles from "./WindChart.module.css";

// The session's wind as live-station sites draw it (iKitesurf, Windfinder
// reports): mean wind as a filled area, gusts as a lighter band rising from
// it, so how gusty the day was reads from the band's thickness instead of
// from two numbers. One hue (the --sf-primary ramp): mean and gust are one
// quantity at two intensities, not two categories. Recharts paints plain
// SVG attributes, which don't resolve CSS custom properties — hence rgbCss.
const MEAN_COLOR = rgbCss(BASE_RGB);
const GUST_COLOR = rgbCss(RAMP_LIGHT);
const H = 150;

export function WindChart({ points }: { points: TrueWindPoint[] | null | undefined }) {
  const { t } = useTranslation();
  const { cursor } = useTimeState();
  const summary = useMemo(() => windSummary(points), [points]);
  const data = useMemo(() => windSeries(points), [points]);
  if (!summary || data.length < 2) return null;

  const top = Math.max(summary.maxGustKts ?? 0, summary.peakKts);
  const hasGusts = summary.maxGustKts != null;

  return (
    <div>
      {/* The same ruled results line as the session's own totals, not a
          headline number with satellites. */}
      <div className={styles.head}>
        <StatTiles>
          <StatTile label={t("wind.mean")} value={fmtKnots(summary.meanKts)} />
          {hasGusts && <StatTile label={t("wind.maxGust")} value={fmtKnots(summary.maxGustKts)} />}
          <StatTile label={t("wind.peak")} value={fmtKnots(summary.peakKts)} />
        </StatTiles>
      </div>

      <ResponsiveContainer width="100%" height={H}>
        <ComposedChart data={data} margin={{ top: 6, right: 4, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="ms"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(ms: number) => fmtTime(ms).slice(0, 5)}
            tick={{ fill: "var(--sf-muted)", fontSize: 11 }}
            stroke="var(--sf-border)"
            minTickGap={40}
          />
          <YAxis
            domain={[0, Math.ceil(top + 1)]}
            width={28}
            tickFormatter={(v: number) => splitKnots(v).value.replace(/\.0$/, "")}
            tick={{ fill: "var(--sf-muted)", fontSize: 11 }}
            stroke="var(--sf-border)"
            tickCount={4}
          />
          <Tooltip
            labelFormatter={(ms) => (typeof ms === "number" ? fmtTime(ms) : "")}
            formatter={(v, name) =>
              name === "gustBand"
                ? [fmtKnots(Array.isArray(v) ? Number(v[1]) : Number(v)), t("wind.gust")]
                : [fmtKnots(Number(v)), t("wind.mean")]
            }
            separator=": "
            contentStyle={{
              background: "var(--sf-surface)",
              border: "1px solid var(--sf-border)",
              borderRadius: 8,
              fontSize: 12,
              padding: "0.35rem 0.6rem",
            }}
            itemStyle={{ color: "var(--sf-text)", padding: 0 }}
            labelStyle={{ color: "var(--sf-muted)" }}
          />
          {hasGusts && (
            <Area
              dataKey="gustBand"
              type="monotone"
              stroke={GUST_COLOR}
              strokeWidth={1}
              fill={GUST_COLOR}
              fillOpacity={0.35}
              isAnimationActive={false}
            />
          )}
          <Area
            dataKey="mean"
            type="monotone"
            stroke={MEAN_COLOR}
            strokeWidth={2}
            fill={MEAN_COLOR}
            fillOpacity={0.3}
            isAnimationActive={false}
          />
          {cursor >= data[0].ms && cursor <= data[data.length - 1].ms && (
            <ReferenceLine x={cursor} stroke="var(--sf-text)" strokeWidth={1} />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      <ul className={styles.legend}>
        <li>
          <span className={styles.swatch} style={{ background: MEAN_COLOR }} />
          {t("wind.mean")}
        </li>
        {hasGusts && (
          <li>
            <span className={styles.swatch} style={{ background: GUST_COLOR }} />
            {t("wind.gusts")}
          </li>
        )}
      </ul>
    </div>
  );
}
