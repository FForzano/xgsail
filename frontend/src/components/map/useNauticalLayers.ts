import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import L from "leaflet";
import { NEAR_DETAIL_MIN_ZOOM, useNauticalPoi } from "@/hooks/useNauticalPoi";
import { clubKeys, clubsService } from "@/services/clubs";
import { windKeys, windService } from "@/services/wind";
import type { NauticalPoi } from "@/services/nauticalPoi";
import { createBaseLayers } from "./baseLayers";
import { syncClubsLayer } from "./ClubsLayer";
import { syncStationsLayer } from "./StationsLayer";
import { syncPoiLayer } from "./PoiLayer";
import { CLUBS_MIN_ZOOM, type MapLayers } from "./useMapLayers";

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

/** Attaches the optional nautical overlays (OpenSeaMap chart, nautical POIs,
 * XGSail clubs, weather stations) to an already-built Leaflet map, adding and
 * removing them as the user toggles them. Shared by the replay map
 * (components/race/MapView) and the standalone explorer map so both behave
 * identically.
 *
 * Each overlay lives in its own effect, separate from whatever effect built
 * the map — toggling one must never tear down tiles or tracks.
 *
 * Three layers are gated on zoom, in two tiers: clubs from `CLUBS_MIN_ZOOM`,
 * POIs and weather stations only from the closer `NEAR_DETAIL_MIN_ZOOM`.
 * Worldwide point data degrades into an unreadable field of pins when zoomed
 * out, and clubs are the one layer worth spotting from further away — the
 * stations sit with the POIs as secondary detail. Returns one flag per reason
 * a ticked layer might still be showing nothing — below either zoom gate, or
 * (POIs only) upstream unreachable — so the switcher can say which, and why. */
export function useNauticalLayers(
  map: L.Map | null,
  layers: MapLayers,
): { clubsHidden: boolean; nearDetailHidden: boolean; poiFailed: boolean } {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const zoom = useMapZoom(map);
  const showClubs = layers.clubs && zoom >= CLUBS_MIN_ZOOM;
  const showStations = layers.stations && zoom >= NEAR_DETAIL_MIN_ZOOM;

  const { pois, failed: poiFailed } = useNauticalPoi(map, layers.poi);
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

  // With the nautical chart on, an unnamed POI adds nothing: OpenSeaMap
  // already draws a harbour/marina symbol at those exact coordinates, and what
  // our pin has over that mute raster symbol is the label — name, kind,
  // tappable OSM link. A named POI is therefore always worth drawing, and with
  // the chart off even an unnamed one still says something is there. Filtered
  // here, at display time, never in the fetch: a cached POI result must
  // not depend on which layers happen to be toggled.
  //
  // A POI already linked to a club (Club.osm_ref) is also dropped, since the
  // club's own pin now stands for it — but only while the clubs layer is
  // actually being drawn (`showClubs`, the same condition the clubs query is
  // `enabled` on above). `clubs.data` otherwise lingers in the TanStack cache
  // after the layer is toggled off, which would keep hiding the POI even
  // though nothing was drawn in its place — making the place vanish from the
  // map entirely.
  // OSM elements a club has claimed as being itself: their POI pin is the
  // duplicate the club's own pin replaces. Keyed on `showClubs`, not just on
  // `clubs.data` — the club list lingers in the TanStack cache after the
  // layer is switched off, and hiding the POI when nothing draws the club in
  // its place would make the place vanish from the map entirely.
  const linkedOsmRefs = useMemo(
    () =>
      new Set(
        (showClubs ? clubs.data ?? [] : [])
          .map((c) => c.osm_ref)
          .filter((ref): ref is string => !!ref),
      ),
    [showClubs, clubs.data],
  );
  const visiblePois = useMemo(
    () =>
      (layers.seamark ? pois.filter((poi) => poi.name) : pois).filter((poi) => !linkedOsmRefs.has(poi.id)),
    [pois, layers.seamark, linkedOsmRefs],
  );

  const poiGroup = useLayerGroup(map, layers.poi);
  useEffect(() => {
    if (!poiGroup) return;
    syncPoiLayer(
      poiGroup,
      visiblePois,
      (poi: NauticalPoi) => t(`map.poi.${poi.kind}`),
      t("map.poi.createClub"),
      (poi: NauticalPoi) => {
        const params = new URLSearchParams({ osm: poi.id });
        if (poi.name) params.set("osm_name", poi.name);
        params.set("osm_lat", String(poi.lat));
        params.set("osm_lng", String(poi.lng));
        navigate(`/gruppi/clubs?${params.toString()}`);
      },
    );
  }, [poiGroup, visiblePois, t, navigate]);

  const clubsGroup = useLayerGroup(map, showClubs);
  useEffect(() => {
    if (!map || !clubsGroup) return;
    syncClubsLayer(map, clubsGroup, clubs.data ?? [], { open: t("map.openClub") }, (clubId) =>
      navigate(`/gruppi/clubs/${clubId}`),
    );
  }, [map, clubsGroup, clubs.data, t, navigate]);

  const stationsGroup = useLayerGroup(map, showStations);
  useEffect(() => {
    if (!map || !stationsGroup) return;
    syncStationsLayer(map, stationsGroup, stations.data ?? [], {
      noReading: t("map.stations.noReading"),
      ago: (minutes: number) => t("map.stations.ago", { minutes }),
    });
  }, [map, stationsGroup, stations.data, t]);

  return {
    clubsHidden: layers.clubs && zoom < CLUBS_MIN_ZOOM,
    nearDetailHidden: (layers.poi || layers.stations) && zoom < NEAR_DETAIL_MIN_ZOOM,
    poiFailed: layers.poi && poiFailed,
  };
}
