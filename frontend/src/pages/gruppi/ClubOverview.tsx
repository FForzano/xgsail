import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Card } from "@/components/ui/Card";
import { ExplorerMap } from "@/components/map/ExplorerMap";
import { WindStationHintCard } from "@/components/common/WindStationHintCard";
import { useClubContext } from "./ClubDetailLayout";

export function ClubOverview() {
  const { t } = useTranslation();
  const { club, stationedBoats, manages } = useClubContext();
  // Stable identity: ExplorerMap re-centers whenever `center` changes, and a
  // fresh object every render would fight the user's own panning/zooming.
  const position = useMemo(
    () => (club.lat != null && club.lng != null ? { lat: club.lat, lng: club.lng } : null),
    [club.lat, club.lng],
  );

  return (
    <>
      {manages && <WindStationHintCard />}

      <Card>
        <p className="sf-muted">{club.description}</p>
        <p className="sf-muted">
          {club.city ?? ""}{" "}
          {club.website && (
            <a href={club.website} target="_blank" rel="noreferrer">
              {club.website}
            </a>
          )}
        </p>
      </Card>

      {position && (
        <Card title={t("gruppi.clubLocation")}>
          <ExplorerMap center={position} zoom={14} marker={position} />
        </Card>
      )}

      {stationedBoats.length > 0 && (
        <Card title={t("gruppi.stationedBoats")}>
          <div className="sf-strip">
            {stationedBoats.map((b) => (
              <div key={b.id} className="sf-strip__item sf-strip__item--muted">
                <span>
                  <strong>{b.name}</strong>{" "}
                  <span className="sf-muted">{b.sail_number ?? ""}</span>
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}
