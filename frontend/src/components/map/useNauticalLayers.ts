import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import L from "leaflet";
import { useNauticalPoi } from "@/hooks/useNauticalPoi";
import { clubKeys, clubsService } from "@/services/clubs";
import type { NauticalPoi } from "@/services/overpass";
import { createBaseLayers } from "./baseLayers";
import { collapseClubCards, syncClubsLayer } from "./ClubsLayer";
import { syncPoiLayer } from "./PoiLayer";
import type { MapLayers } from "./useMapLayers";

/** Creates a layer group on `map` while `enabled`, and hands it back so the
 * effect that fills it can depend on it — a ref wouldn't do, since setting a
 * ref doesn't re-run the effect that draws into the group. */
function useLayerGroup(map: L.Map | null, enabled: boolean): L.LayerGroup | null {
  const [group, setGroup] = useState<L.LayerGroup | null>(null);
  useEffect(() => {
    if (!map || !enabled) {
      setGroup(null);
      return;
    }
    const created = L.layerGroup().addTo(map);
    setGroup(created);
    return () => {
      setGroup(null);
      map.removeLayer(created);
    };
  }, [map, enabled]);
  return group;
}

/** Attaches the optional nautical overlays (OpenSeaMap chart, Overpass POIs,
 * XGSail clubs) to an already-built Leaflet map, adding and removing them as
 * the user toggles them. Shared by the replay map (components/race/MapView)
 * and the standalone explorer map so both behave identically.
 *
 * Each overlay lives in its own effect, separate from whatever effect built
 * the map — toggling one must never tear down tiles or tracks. */
export function useNauticalLayers(map: L.Map | null, layers: MapLayers): void {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const pois = useNauticalPoi(map, layers.poi);
  const clubs = useQuery({
    queryKey: clubKeys.all,
    queryFn: () => clubsService.list(),
    enabled: layers.clubs,
    staleTime: 5 * 60 * 1000,
  });

  // OpenSeaMap raster overlay.
  useEffect(() => {
    if (!map || !layers.seamark) return;
    const seamark = createBaseLayers().seamark;
    seamark.addTo(map);
    return () => {
      map.removeLayer(seamark);
    };
  }, [map, layers.seamark]);

  const poiGroup = useLayerGroup(map, layers.poi);
  useEffect(() => {
    if (!poiGroup) return;
    syncPoiLayer(poiGroup, pois, (poi: NauticalPoi) => t(`map.poi.${poi.kind}`));
  }, [poiGroup, pois, t]);

  const clubsGroup = useLayerGroup(map, layers.clubs);
  useEffect(() => {
    if (!map || !clubsGroup) return;
    syncClubsLayer(map, clubsGroup, clubs.data ?? [], { open: t("map.openClub") }, (clubId) =>
      navigate(`/gruppi/clubs/${clubId}`),
    );
    // Tapping the map (rather than another pin) closes whichever club card is
    // open — the pins themselves handle the pin-to-pin case.
    const collapse = () => collapseClubCards(map);
    map.on("click", collapse);
    return () => {
      map.off("click", collapse);
    };
  }, [map, clubsGroup, clubs.data, t, navigate]);
}
