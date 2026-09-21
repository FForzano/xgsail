import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ExplorerMap } from "@/components/map/ExplorerMap";
import { WindStationHintCard } from "@/components/common/WindStationHintCard";
import { RichText } from "@/components/ui/RichText";
import { clubsService, clubKeys } from "@/services/clubs";
import { useOsmLinkErrorNotifier } from "@/hooks/useOsmLinkErrorNotifier";
import { useToast } from "@/hooks/useToast";
import { useClubContext } from "./ClubDetailLayout";

export function ClubOverview() {
  const { t } = useTranslation();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const notifyLinkError = useOsmLinkErrorNotifier();
  const { club, stationedBoats, manages } = useClubContext();

  // Manage-gated on the server (403 for anyone else) and pointless once the
  // club is already linked, so skip the request entirely in both cases.
  const osmSuggestions = useQuery({
    queryKey: clubKeys.osmSuggestions(club.id),
    queryFn: () => clubsService.listOsmSuggestions(club.id),
    enabled: manages && !club.osm_ref,
  });

  const linkOsm = useMutation({
    mutationFn: (osmRef: string) => clubsService.update(club.id, { osm_ref: osmRef }),
    onSuccess: async () => {
      notify(t("gruppi.osmSuggestionLinked"), "success");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: clubKeys.all }),
        queryClient.invalidateQueries({ queryKey: clubKeys.detail(club.id) }),
        queryClient.invalidateQueries({ queryKey: clubKeys.osmSuggestions(club.id) }),
      ]);
    },
    onError: notifyLinkError,
  });

  // Stable identity: ExplorerMap re-centers whenever `center` changes, and a
  // fresh object every render would fight the user's own panning/zooming.
  const position = useMemo(
    () => (club.lat != null && club.lng != null ? { lat: club.lat, lng: club.lng } : null),
    [club.lat, club.lng],
  );

  return (
    <>
      {manages && <WindStationHintCard />}

      {(osmSuggestions.data?.length ?? 0) > 0 && (
        <Card title={t("gruppi.osmSuggestionsTitle")}>
          <div className="sf-strip">
            {osmSuggestions.data!.map((s) => (
              <div key={s.osm_ref} className="sf-strip__item sf-strip__item--muted">
                <span>
                  <strong>{s.name ?? t("gruppi.osmSuggestionUnnamed")}</strong>{" "}
                  <span className="sf-muted">
                    {t("gruppi.osmSuggestionDistance", { distance: Math.round(s.distance_m) })}
                  </span>
                </span>
                <Button
                  variant="ghost"
                  disabled={linkOsm.isPending}
                  onClick={() => linkOsm.mutate(s.osm_ref)}
                >
                  {t("gruppi.osmClaimAction")}
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div data-tour="club-info">
        <Card>
          <RichText html={club.description} tier="basic" className="sf-muted" />
          <p className="sf-muted">
            {club.city ?? ""}{" "}
            {club.website && (
              <a href={club.website} target="_blank" rel="noreferrer">
                {club.website}
              </a>
            )}
          </p>
        </Card>
      </div>

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
