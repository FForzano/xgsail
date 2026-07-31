import podium from "./podium.module.css";

/** Tint class for a place, or "" from 4th down — the three surfaces that show
 * a podium (series standings, race results, the sailor's own card) all map
 * rank → class the same way, so the mapping lives here rather than three
 * times over. */
export function podiumRankClass(rank: number): string {
  return rank === 1 ? podium.rank1 : rank === 2 ? podium.rank2 : rank === 3 ? podium.rank3 : "";
}
