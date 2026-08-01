import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { raceKeys, regattasService } from "@/services/races";
import { resultStatusBadge } from "@/utils/badges";
import { fmtPoints } from "@/utils/format";
import type { StandingRow, UUID } from "@/types";
import podium from "./podium.module.css";
import { podiumRankClass } from "./podium";
import styles from "./RegattaStandings.module.css";

/** Overall standings for a regatta: one row per boat, one column per race,
 * totals on the right. The scoring is the backend's
 * (`GET /regattas/{id}/standings`) — nothing here recomputes points. */
export function RegattaStandings({
  regattaId,
  highlightBoatId,
}: {
  regattaId: UUID;
  /** The viewer's own boat, pulled out of the pack. */
  highlightBoatId?: UUID | null;
}) {
  const { t } = useTranslation();

  const standings = useQuery({
    queryKey: raceKeys.standings(regattaId),
    queryFn: () => regattasService.standings(regattaId),
  });

  if (standings.isLoading) return <Spinner />;

  const data = standings.data;
  // Boats on the start list are listed even before they sail, so a non-empty
  // `standings` isn't proof there's anything to rank yet.
  const scored = data?.standings.some((row) => Object.keys(row.races).length > 0);
  if (!data || !scored) return <EmptyState>{t("regate.standingsEmpty")}</EmptyState>;

  return (
    <div>
      {data.is_official && (
        <p className={`sf-badge ${styles.officialBadge}`}>{t("regate.officialStandings")}</p>
      )}
      <div className="sf-tablewrap">
        <table className="sf-table">
          <thead>
            <tr>
              <th className={styles.rankCell}>{t("race.position")}</th>
              <th>{t("race.boat")}</th>
              {data.races.map((race) => (
                <th
                  key={race.id}
                  className={styles.raceCol}
                  title={`${t("regate.raceNumber")} ${race.race_number}`}
                >
                  {t("regate.raceAbbr", { n: race.race_number })}
                </th>
              ))}
              <th className={styles.totalCol}>{t("regate.total")}</th>
            </tr>
          </thead>
          <tbody>
            {data.standings.map((row) => (
              <StandingsRow
                key={row.boat.id}
                row={row}
                raceIds={data.races.map((r) => r.id)}
                mine={!!highlightBoatId && row.boat.id === highlightBoatId}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StandingsRow({ row, raceIds, mine }: { row: StandingRow; raceIds: UUID[]; mine: boolean }) {
  const raced = Object.keys(row.races).length > 0;
  const rowClass = [mine ? styles.mine : "", raced ? "" : styles.idle].filter(Boolean).join(" ");

  return (
    <tr className={rowClass}>
      <td className={styles.rankCell}>
        <span className={`${podium.medal} ${raced ? podiumRankClass(row.rank) : ""}`}>
          {row.rank}
        </span>
      </td>
      <td>
        <span className={styles.boatName}>{row.boat.name}</span>
        {row.boat.sail_number && <span className={styles.sail}>{row.boat.sail_number}</span>}
      </td>
      {raceIds.map((raceId) => (
        <td key={raceId} className={styles.raceCol}>
          <RaceCell result={row.races[raceId]} />
        </td>
      ))}
      {/* A boat that hasn't raced has a total of 0, which would otherwise read
          as a leading score under low-point scoring. */}
      <td className={styles.totalCol}>{raced ? fmtPoints(row.total) : "—"}</td>
    </tr>
  );
}

function RaceCell({ result }: { result?: StandingRow["races"][string] }) {
  if (!result) return <>—</>;
  if (result.status !== "finished") {
    // dnf/dns/dsq/ocs/ret — the RRS abbreviations, identical in every language.
    return (
      <span className={`${resultStatusBadge(result.status)} sf-badge--sm`}>
        {result.status.toUpperCase()}
      </span>
    );
  }
  return <>{result.position ?? fmtPoints(result.score)}</>;
}
