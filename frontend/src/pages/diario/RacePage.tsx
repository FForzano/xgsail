import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { racesService, racedaysService, regattasService, raceKeys } from "@/services/races";
import { activitiesService, activityKeys } from "@/services/activities";
import { boatsService, boatKeys } from "@/services/boats";
import { useCapabilities } from "@/hooks/useCapabilities";
import { timeController } from "@/stores/timeController";
import { buildTracks, timeBounds } from "@/components/race/raceModel";
import { MapView, type MapMark } from "@/components/race/MapView";
import { Timeline } from "@/components/race/Timeline";
import { SpeedChart } from "@/components/race/SpeedChart";
import { Leaderboard } from "@/components/race/Leaderboard";
import { RaceManagePanel } from "@/components/race/RaceManagePanel";
import { WindCard } from "@/components/common/WindCard";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { BackLink } from "@/components/ui/BackLink";
import type { UUID } from "@/types";
import styles from "./RacePage.module.css";

/** The race dashboard (docs/frontend-project.md "Race/Regate"): replay core
 * (map + playback + leaderboard + speed chart + results) with the management
 * panel for scoped officers. Full-width, outside the Diario tab layout. */
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
  const results = race.data?.results ?? [];
  const boats = useQuery({
    queryKey: boatKeys.all,
    queryFn: () => boatsService.list(),
    enabled: results.length > 0,
  });

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

  if (race.isLoading || data.isLoading || !raceId) return <Spinner />;
  if (!race.data) return null;

  const clubId = regatta.data?.club_id;
  const canRace = clubId != null && can("race.manage", clubId);
  const canMarks = clubId != null && can("mark.manage", clubId);
  const canResults = clubId != null && can("result.manage", clubId);
  const boatName = (id: UUID) => boats.data?.find((b) => b.id === id)?.name ?? id.slice(0, 8);

  return (
    <div className="sf-section__body">
      {raceday.data?.regatta_id && (
        <BackLink
          fallback={`/diario/regate/regatta/${raceday.data.regatta_id}`}
          label={t("regate.backToRegatta")}
        />
      )}
      <h1>
        {regatta.data?.name ?? t("regate.title")} — {t("regate.raceNumber")}{" "}
        {race.data.race_number}
      </h1>

      {tracks[0]?.pts[0] && (
        <WindCard
          lat={tracks[0].pts[0].lat}
          lng={tracks[0].pts[0].lon}
          at={race.data.start_time}
        />
      )}

      {tracks.length === 0 ? (
        <Card title={t("race.leaderboard")}>
          <p className="sf-muted">{t("race.noData")}</p>
          {mapMarks.length > 0 && <MapView tracks={[]} marks={mapMarks} />}
        </Card>
      ) : (
        <div className={styles.race}>
          <div className="sf-section__body">
            <MapView tracks={tracks} marks={mapMarks} />
            <Timeline />
            <SpeedChart tracks={tracks} />
          </div>
          <div className="sf-section__body">
            <Card title={t("race.leaderboard")}>
              <Leaderboard tracks={tracks} />
            </Card>
          </div>
        </div>
      )}

      {results.length > 0 && (
        <Card title={t("race.results")}>
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
                {[...results]
                  .sort((a, b) => (a.position ?? 99) - (b.position ?? 99))
                  .map((r) => (
                    <tr key={r.boat_id}>
                      <td>{r.position ?? "—"}</td>
                      <td>{boatName(r.boat_id)}</td>
                      <td>
                        <span className="sf-badge">{r.status}</span>
                      </td>
                      <td>{r.score ?? "—"}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Card>
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
