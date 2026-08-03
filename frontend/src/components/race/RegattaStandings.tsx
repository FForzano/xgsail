import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { raceKeys, regattasService } from "@/services/races";
import { resultStatusBadge } from "@/utils/badges";
import { fmtPoints } from "@/utils/format";
import type { DivisionStandings, StandingRow, UnrankedStandingRow, UUID } from "@/types";
import podium from "./podium.module.css";
import { podiumRankClass } from "./podium";
import styles from "./RegattaStandings.module.css";

/** Overall standings for a regatta: one row per boat, one column per race,
 * totals on the right. The scoring is the backend's
 * (`GET /regattas/{id}/standings`) — nothing here recomputes points. If the
 * regatta has divisions, each one gets its own tab and its own table; a
 * regatta with none renders the single table exactly as before. */
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
  // The table is the fleet, not just the scored part of it: a regatta with a
  // start list and no results yet still shows every entered boat (totals as
  // "—"). Only a genuinely empty start list has nothing to render.
  if (!data || (data.standings.length === 0 && data.unranked.length === 0))
    return <EmptyState>{t("regate.standingsEmpty")}</EmptyState>;

  return (
    <div>
      {data.is_official && (
        <p className={`sf-badge ${styles.officialBadge}`}>{t("regate.officialStandings")}</p>
      )}
      {data.divisions.length === 0 ? (
        <StandingsTable
          races={data.races}
          standings={data.standings}
          unranked={data.unranked}
          highlightBoatId={highlightBoatId}
        />
      ) : (
        <DivisionTabs divisions={data.divisions} highlightBoatId={highlightBoatId} />
      )}
    </div>
  );
}

/** One tab per division (plus a "no division" tab when some races/entries
 * aren't assigned to any), defaulting to whichever group has the viewer's
 * own boat. */
function DivisionTabs({
  divisions,
  highlightBoatId,
}: {
  divisions: DivisionStandings[];
  highlightBoatId?: UUID | null;
}) {
  const { t } = useTranslation();

  const defaultIndex = useMemo(() => {
    if (highlightBoatId) {
      const mine = divisions.findIndex((d) => d.standings.some((r) => r.boat.id === highlightBoatId));
      if (mine >= 0) return mine;
    }
    return 0;
  }, [divisions, highlightBoatId]);

  const [selected, setSelected] = useState(defaultIndex);
  const active = divisions[selected] ?? divisions[0];

  return (
    <div>
      <nav className={`sf-tabs ${styles.divisionTabs}`} aria-label={t("regate.divisions")}>
        {divisions.map((d, i) => (
          <button
            key={d.division?.id ?? "none"}
            type="button"
            className={`sf-tab ${i === selected ? "active" : ""}`}
            onClick={() => setSelected(i)}
          >
            {d.division?.name ?? t("regate.noDivision")}
            <span className="sf-tab__badge">{d.entry_count}</span>
          </button>
        ))}
      </nav>
      {active.division?.laps != null && (
        <p className={styles.divisionCaption}>
          {active.division.laps} {t("regate.divisionLaps")}
        </p>
      )}
      <StandingsTable
        races={active.races}
        standings={active.standings}
        unranked={active.unranked}
        highlightBoatId={highlightBoatId}
      />
    </div>
  );
}

function StandingsTable({
  races,
  standings,
  unranked,
  highlightBoatId,
}: {
  races: Array<{ id: UUID; race_number: number; division_race_number?: number }>;
  standings: StandingRow[];
  unranked: UnrankedStandingRow[];
  highlightBoatId?: UUID | null;
}) {
  const { t } = useTranslation();
  return (
    <div className="sf-tablewrap">
      <table className="sf-table">
        <thead>
          <tr>
            <th className={styles.rankCell}>{t("race.position")}</th>
            <th>{t("race.boat")}</th>
            {races.map((race) => {
              const n = race.division_race_number ?? race.race_number;
              return (
                <th key={race.id} className={styles.raceCol} title={`${t("regate.raceNumber")} ${n}`}>
                  {t("regate.raceAbbr", { n })}
                </th>
              );
            })}
            <th className={styles.totalCol}>{t("regate.total")}</th>
          </tr>
        </thead>
        <tbody>
          {standings.map((row) => (
            <StandingsRow
              key={row.boat.id}
              row={row}
              raceIds={races.map((r) => r.id)}
              mine={!!highlightBoatId && row.boat.id === highlightBoatId}
            />
          ))}
          {/* Paper entries: on the start list, impossible to rank. */}
          {unranked.map((entry) => (
            <UnrankedRow key={entry.entry_id} entry={entry} raceCount={races.length} />
          ))}
        </tbody>
      </table>
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

/** A paper entry from the start list: it has a name and nothing else, so every
 * scoring cell stays empty and it never gets a rank or a podium medal. */
function UnrankedRow({ entry, raceCount }: { entry: UnrankedStandingRow; raceCount: number }) {
  return (
    <tr className={styles.idle}>
      <td className={styles.rankCell}>—</td>
      <td>
        <span className={styles.boatName}>{entry.display_name ?? "—"}</span>
        {entry.display_sail_number && (
          <span className={styles.sail}>{entry.display_sail_number}</span>
        )}
      </td>
      {Array.from({ length: raceCount }, (_, i) => (
        <td key={i} className={styles.raceCol}>
          —
        </td>
      ))}
      <td className={styles.totalCol}>—</td>
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
