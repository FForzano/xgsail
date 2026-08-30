import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import L from "leaflet";
import { useNauticalPoi } from "@/hooks/useNauticalPoi";
import { clubKeys, clubsService } from "@/services/clubs";
import { windKeys, windService } from "@/services/wind";
import type { NauticalPoi } from "@/services/overpass";
import { createBaseLayers } from "./baseLayers";
import { collapseClubCards, syncClubsLayer } from "./ClubsLayer";
import { collapseStationCards, syncStationsLayer } from "./StationsLayer";
import { syncPoiLayer } from "./PoiLayer";
import { DETAIL_LAYERS_MIN_ZOOM, type MapLayers } from "./useMapLayers";

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

/** The map's current zoom, kept in state so the effects that gate a layer on
 * it actually re-run when the user zooms. */
function useMapZoom(map: L.Map | null): number {
  const [zoom, setZoom] = useState(() => map?.getZoom() ?? 0);
  useEffect(() => {
    if (!map) return;
    const update = () => setZoom(map.getZoom());
    update();
    map.on("zoomend", update);
    return () => {
      map.off("zoomend", update);
    };
  }, [map]);
  return zoom;
}

/** Attaches the optional nautical overlays (OpenSeaMap chart, Overpass POIs,
 * XGSail clubs, weather stations) to an already-built Leaflet map, adding and
 * removing them as the user toggles them. Shared by the replay map
 * (components/race/MapView) and the standalone explorer map so both behave
 * identically.
 *
 * Each overlay lives in its own effect, separate from whatever effect built
 * the map — toggling one must never tear down tiles or tracks.
 *
 * The clubs and stations layers are additionally gated on zoom
 * (`DETAIL_LAYERS_MIN_ZOOM`): both are worldwide point data, and at a
 * continental zoom they degrade into a field of pins that tells the user
 * nothing. Returns `detailHidden` so the switcher can say why a layer the
 * user just ticked isn't showing. */
export function useNauticalLayers(
  map: L.Map | null,
  layers: MapLayers,
): { detailHidden: boolean } {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const zoom = useMapZoom(map);
  const zoomedIn = zoom >= DETAIL_LAYERS_MIN_ZOOM;
  const showClubs = layers.clubs && zoomedIn;
  const showStations = layers.stations && zoomedIn;

  const pois = useNauticalPoi(map, layers.poi);
  const clubs = useQuery({
    queryKey: clubKeys.all,
    queryFn: () => clubsService.list(),
    enabled: showClubs,
    staleTime: 5 * 60 * 1000,
  });
  const stations = useQuery({
    queryKey: windKeys.stationsWithLast,
    // include_last: the card shows the station's most recent reading, which
    // is what tells a sailor whether it is actually alive.
    queryFn: () => windService.listStations({ includeLast: true }),
    enabled: showStations,
    staleTime: 60 * 1000,
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

  const clubsGroup = useLayerGroup(map, showClubs);
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

  const stationsGroup = useLayerGroup(map, showStations);
  useEffect(() => {
    if (!map || !stationsGroup) return;
    syncStationsLayer(map, stationsGroup, stations.data ?? [], {
      noReading: t("map.stations.noReading"),
      ago: (minutes: number) => t("map.stations.ago", { minutes }),
    });
    const collapse = () => collapseStationCards(map);
    map.on("click", collapse);
    return () => {
      map.off("click", collapse);
    };
  }, [map, stationsGroup, stations.data, t]);

  return { detailHidden: (layers.clubs || layers.stations) && !zoomedIn };
}
