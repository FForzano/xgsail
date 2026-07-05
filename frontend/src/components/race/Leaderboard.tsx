import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useTimeState } from "@/stores/timeController";
import { haversineMeters } from "@/utils/geo";
import { indexAt, type Track } from "./raceModel";

// Live standings at the cursor: distance sailed so far (proxy for progress) +
// current speed. Cumulative distance is precomputed once per track; each tick
// only binary-searches the cursor index.
export function Leaderboard({ tracks }: { tracks: Track[] }) {
  const { t } = useTranslation();
  const { cursor } = useTimeState();

  const cum = useMemo(() => {
    const map: Record<string, number[]> = {};
    for (const tr of tracks) {
      const arr = new Array<number>(tr.pts.length).fill(0);
      for (let i = 1; i < tr.pts.length; i++) {
        arr[i] =
          arr[i - 1] +
          haversineMeters(tr.pts[i - 1].lat, tr.pts[i - 1].lon, tr.pts[i].lat, tr.pts[i].lon);
      }
      map[tr.id] = arr;
    }
    return map;
  }, [tracks]);

  const rows = tracks
    .map((tr) => {
      const i = indexAt(tr, cursor);
      return {
        tr,
        dist: i >= 0 ? cum[tr.id][i] : 0,
        sog: i >= 0 ? tr.pts[i].sog : 0,
      };
    })
    .sort((a, b) => b.dist - a.dist);

  return (
    <div className="sf-tablewrap">
      <table className="sf-table">
        <thead>
          <tr>
            <th>{t("race.position")}</th>
            <th>{t("race.boat")}</th>
            <th>{t("race.sog")}</th>
            <th>{t("race.distance")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, idx) => (
            <tr key={r.tr.id}>
              <td>{idx + 1}</td>
              <td>
                <span className="sf-legend__dot" style={{ background: r.tr.color }} />
                {r.tr.name}
              </td>
              <td>{r.sog.toFixed(1)} kn</td>
              <td className="sf-muted">{(r.dist / 1852).toFixed(2)} nm</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
