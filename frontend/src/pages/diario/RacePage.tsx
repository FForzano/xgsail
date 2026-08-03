import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { racesService, racedaysService, regattasService, raceKeys } from "@/services/races";
import { activitiesService, activityKeys } from "@/services/activities";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { timeController } from "@/stores/timeController";
import { buildTracks, medianIntervalMs, timeBounds } from "@/components/race/raceModel";
import { MapView, type MapMark } from "@/components/race/MapView";
import { Timeline } from "@/components/race/Timeline";
import { SpeedChart } from "@/components/race/SpeedChart";
import { Leaderboard } from "@/components/race/Leaderboard";
import { RaceManagePanel } from "@/components/race/RaceManagePanel";
import { RegattaHero } from "@/components/race/RegattaHero";
import { WindCard } from "@/components/common/WindCard";
import { StatTile, StatTiles } from "@/components/session/StatTile";
import { Section } from "@/components/ui/Section";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { BackLink } from "@/components/ui/BackLink";
import { resultStatusBadge } from "@/utils/badges";
import { fmtDuration, fmtPoints, fmtTime } from "@/utils/format";
import podium from "@/components/race/podium.module.css";
import { podiumRankClass } from "@/components/race/podium";
import type { UUID } from "@/types";
import styles from "./RacePage.module.css";

/** The race dashboard: replay core (map + playback + leaderboard + speed
 * chart + results) with the management panel for scoped officers.
 * Full-width, outside the Diario tab layout.
 *
 * Ordered for the competitor: context, totals, replay, podium, and their own
 * track — with the organizer's tools collapsed at the bottom. */
export function RacePage() {
  const { raceId } = useParams<{ raceId: UUID }>();
  const { t } = useTranslation();
  const { can } = useCapabilities();
  const [previewMarks, setPreviewMarks] = useState<MapMark[]>([]);

  const race = useQuery({
    queryKey: raceKeys.race(raceId!),
    queryFn: () => racesService.get(raceId!),
    enabled: !!raceId,
  });
  const data = useQuery({
    queryKey: raceKeys.data(raceId!),
    queryFn: () => racesService.data(raceId!),
    enabled: !!raceId,
  });
  const marks = useQuery({
    queryKey: activityKeys.marks(race.data?.activity_id ?? "none"),
    queryFn: () => activitiesService.marks(race.data!.activity_id!),
    enabled: !!race.data?.activity_id,
  });
  // Club scope for permission gating: race → raceday → regatta → club_id.
  const raceday = useQuery({
    queryKey: raceKeys.raceday(race.data?.race_day_id ?? "none"),
    queryFn: () => racedaysService.get(race.data!.race_day_id),
    enabled: !!race.data?.race_day_id,
  });
  const regatta = useQuery({
    queryKey: raceKeys.regatta(raceday.data?.regatta_id ?? "none"),
    queryFn: () => regattasService.get(raceday.data!.regatta_id!),
    enabled: !!raceday.data?.regatta_id,
  });
  const results = useMemo(() => race.data?.results ?? [], [race.data]);
  const boats = useQuery({
    queryKey: boatKeys.all,
    queryFn: () => boatsService.list(),
    enabled: results.length > 0,
  });
  const myBoats = useQuery({ queryKey: boatKeys.mine, queryFn: () => boatsService.list(true) });

  const tracks = useMemo(() => (data.data ? buildTracks(data.data) : []), [data.data]);

  useEffect(() => {
    if (tracks.length) timeController.setBounds(...timeBounds(tracks));
    return () => timeController.pause();
  }, [tracks]);

  const mapMarks = useMemo<MapMark[]>(
    () => [
      ...(marks.data ?? []).map((m) => ({ id: m.id, mark_role: m.mark_role, lat: m.lat, lng: m.lng })),
      ...previewMarks,
    ],
    [marks.data, previewMarks],
  );

  /** The viewer's own entry in this race: the session that carries their
   * track (so they can jump to the full analysis) and their result, if the
   * committee has already entered one. `buildTracks` keys tracks by session
   * id, which is also how `race.data.sessions` is keyed. */
  const mine = useMemo(() => {
    const ids = new Set((myBoats.data ?? []).map((b) => b.id));
    for (const [sessionId, entry] of Object.entries(data.data?.sessions ?? {})) {
      if (entry.boat && ids.has(entry.boat.id)) {
        return {
          sessionId: sessionId as UUID,
          boatName: entry.boat.name,
          result: results.find((r) => r.boat_id === entry.boat!.id) ?? null,
        };
      }
    }
    return null;
  }, [data.data, myBoats.data, results]);

  if (race.isLoading || data.isLoading || !raceId) return <Spinner />;
  if (!race.data) return null;

  const clubId = regatta.data?.club_id;
  const canRace = clubId != null && can("race.manage", clubId);
  const canMarks = clubId != null && can("mark.manage", clubId);
  const canResults = clubId != null && can("result.manage", clubId);
  const boatName = (id: UUID) => boats.data?.find((b) => b.id === id)?.name ?? id.slice(0, 8);

  const [from, to] = tracks.length ? timeBounds(tracks) : [0, 0];
  const totalRaces = (regatta.data?.race_days ?? []).reduce(
    (n, day) => n + (day.races ?? []).length,
    0,
  );
  const ranked = [...results].sort((a, b) => (a.position ?? 99) - (b.position ?? 99));
  const podiumRows = ranked.filter((r) => r.position != null && r.position <= 3);

  // "3° · 4 punti", or the bare RRS abbreviation when the boat didn't finish.
  const myResult = mine?.result;
  const myResultLabel = !myResult
    ? t("race.yourRaceNoResult")
    : myResult.status !== "finished"
      ? myResult.status.toUpperCase()
      : `${myResult.position != null ? `${myResult.position}° ` : ""}${t("regate.pointsValue", {
          points: fmtPoints(myResult.score),
        })}`;

  return (
    <div className="sf-section__body">
      {raceday.data?.regatta_id && (
        <BackLink
          fallback={`/diario/regate/regatta/${raceday.data.regatta_id}`}
          label={t("regate.backToRegatta")}
        />
      )}

      {regatta.data && (
        <RegattaHero
          regatta={regatta.data}
          race={{
            raceNumber: race.data.race_number,
            status: race.data.status,
            date: raceday.data?.date ?? null,
            startTime: race.data.start_time,
          }}
        />
      )}

      <StatTiles>
        <StatTile label={t("race.statBoats")} value={tracks.length} />
        <StatTile
          label={t("race.statDuration")}
          value={tracks.length ? fmtDuration((to - from) / 1000) : "—"}
        />
        <StatTile
          label={t("race.statStart")}
          value={race.data.start_time ? fmtTime(new Date(race.data.start_time).getTime()) : "—"}
        />
        <StatTile
          label={t("race.statRaceOf")}
          value={totalRaces ? `${race.data.race_number}/${totalRaces}` : race.data.race_number}
        />
      </StatTiles>

      {tracks[0]?.pts[0] && (
        <WindCard
          lat={tracks[0].pts[0].lat}
          lng={tracks[0].pts[0].lon}
          at={race.data.start_time}
        />
      )}

      {tracks.length === 0 ? (
        <Section title={t("race.replay")}>
          <EmptyState>{t("race.noData")}</EmptyState>
          {mapMarks.length > 0 && (
            <div className="sf-bleed">
              <MapView tracks={[]} marks={mapMarks} />
            </div>
          )}
        </Section>
      ) : (
        <div className={styles.race}>
          <div>
            <div className="sf-bleed">
              <MapView
                tracks={tracks}
                marks={mapMarks}
                nautical
                controls={<Timeline overlay stepMs={medianIntervalMs(tracks[0]) * 5} />}
              />
            </div>
            <SpeedChart tracks={tracks} />
          </div>
          <div className="sf-section__body">
            <Section title={t("race.leaderboard")}>
              <Leaderboard tracks={tracks} />
            </Section>
          </div>
        </div>
      )}

      {mine && (
        <Section title={t("race.yourRace")}>
          <div className={styles.yourRace}>
            {mine.result?.position != null && (
              <span className={`${podium.medal} ${podiumRankClass(mine.result.position)}`}>
                {mine.result.position}
              </span>
            )}
            <div className={styles.yourRaceText}>
              <span className={styles.yourRaceBoat}>{mine.boatName}</span>
              <span className="sf-muted">{myResultLabel}</span>
            </div>
            {race.data.activity_id && (
              <Link
                className={styles.yourRaceLink}
                to={`/diario/activities/${race.data.activity_id}/barche/${mine.sessionId}`}
              >
                {t("race.openSession")}
                <ChevronRight size={16} />
              </Link>
            )}
          </div>
        </Section>
      )}

      {results.length > 0 && (
        <Section title={t("race.results")}>
          {podiumRows.length > 0 && (
            <div className={styles.podium}>
              {podiumRows.map((r) => (
                <div
                  key={r.boat_id}
                  className={`${podiumRankClass(r.position!)} ${podium.surface} ${styles.podiumBox}`}
                >
                  <span className={`${podium.medal} ${podiumRankClass(r.position!)}`}>
                    {r.position}
                  </span>
                  <span className={styles.podiumBoat}>{boatName(r.boat_id)}</span>
                  <span className="sf-muted">{fmtPoints(r.score)}</span>
                </div>
              ))}
            </div>
          )}
          <div className="sf-tablewrap">
            <table className="sf-table">
              <thead>
                <tr>
                  <th>{t("race.position")}</th>
                  <th>{t("race.boat")}</th>
                  <th>{t("race.resultStatus")}</th>
                  <th>{t("race.score")}</th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((r) => (
                  <tr key={r.boat_id}>
                    <td>{r.position ?? "—"}</td>
                    <td>{boatName(r.boat_id)}</td>
                    <td>
                      <span className={resultStatusBadge(r.status)}>{r.status.toUpperCase()}</span>
                    </td>
                    <td>{fmtPoints(r.score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {(canRace || canMarks || canResults) && (
        <RaceManagePanel
          race={race.data}
          canRace={canRace}
          canMarks={canMarks}
          canResults={canResults}
          onPreviewMarks={setPreviewMarks}
        />
      )}
    </div>
  );
}
