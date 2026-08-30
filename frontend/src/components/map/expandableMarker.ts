import L from "leaflet";

/** Pins that carry their own label: one `divIcon` holds both a collapsed badge
 * and an expanded box, and tapping the pin swaps which of the two is shown by
 * toggling `expandedClass` on the wrapper element — no Leaflet popup involved,
 * so the label keeps the app's own styling and stays anchored to the pin.
 *
 * Shared by the race marks (components/race/MapView), the club pins
 * (ClubsLayer) and the station pins (StationsLayer); they only differ in their
 * markup and colours.
 *
 * The invariant is one open element per map, whatever kind it is: expanding a
 * pin collapses every other expanded pin *of any layer* and closes any open
 * Leaflet popup (the POI layer labels itself with popups, not with these
 * cards), and opening a popup collapses every expanded pin.
 *
 * That cross-layer part is why each pin records its own expanded class on its
 * DOM element: the class names are CSS Module locals — a build-time hash,
 * different per stylesheet — so a collapse-all pass has no way to know them
 * statically. They still arrive as parameters, because each caller owns its
 * own stylesheet; the element just carries the answer for everyone else. */

const EXPANDED_ATTR = "data-expanded-class";

/** Collapses every expanded pin on `map`, whichever layer it belongs to. */
export function collapseExpandable(map: L.Map): void {
  map
    .getContainer()
    .querySelectorAll<HTMLElement>(`[${EXPANDED_ATTR}]`)
    .forEach((el) => {
      const expandedClass = el.dataset.expandedClass;
      if (expandedClass) el.classList.remove(expandedClass);
    });
}

// Maps whose map-level listeners are already attached. Installed on demand
// from bindExpandableMarker rather than by each caller: the listeners are
// identical for every layer, and a map with no expandable pin has nothing for
// them to close anyway. The WeakSet keeps a re-drawn layer from stacking a
// second copy on the same map.
const policedMaps = new WeakSet<L.Map>();

function installSingleOpenPolicy(map: L.Map): void {
  if (policedMaps.has(map)) return;
  policedMaps.add(map);
  // Tapping the water closes the open card. Leaflet stops a marker click from
  // reaching the map, so the pin-to-pin case is handled in the click handler
  // below instead.
  map.on("click", () => collapseExpandable(map));
  map.on("popupopen", () => collapseExpandable(map));
}

/** Makes `marker` expand on tap and collapse on a second tap, closing whatever
 * else was open first. Call before adding the marker to the map. */
export function bindExpandableMarker(
  marker: L.Marker,
  map: L.Map,
  innerClass: string,
  expandedClass: string,
): void {
  installSingleOpenPolicy(map);
  const innerEl = () => marker.getElement()?.querySelector<HTMLElement>(`.${innerClass}`) ?? null;

  // "add", not now: the icon's element only exists once Leaflet has rendered
  // the marker.
  marker.on("add", () => innerEl()?.setAttribute(EXPANDED_ATTR, expandedClass));

  marker.on("click", () => {
    const inner = innerEl();
    const wasExpanded = inner?.classList.contains(expandedClass);
    collapseExpandable(map);
    map.closePopup();
    if (inner && !wasExpanded) inner.classList.add(expandedClass);
  });
}
