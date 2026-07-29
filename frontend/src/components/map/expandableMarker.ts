import L from "leaflet";

/** Pins that carry their own label: one `divIcon` holds both a collapsed badge
 * and an expanded box, and tapping the pin swaps which of the two is shown by
 * toggling `expandedClass` on the wrapper element — no Leaflet popup involved,
 * so the label keeps the app's own styling and stays anchored to the pin.
 *
 * Shared by the race marks (components/race/MapView) and the club pins
 * (ClubsLayer); the two only differ in their markup and colours.
 *
 * Both helpers take the class names as parameters because they're CSS Module
 * locals — each caller owns its own stylesheet and hashed names. */

/** Collapses every expanded pin on `map`, so at most one is ever open. */
export function collapseExpandable(map: L.Map, innerClass: string, expandedClass: string): void {
  map
    .getContainer()
    .querySelectorAll<HTMLElement>(`.${innerClass}.${expandedClass}`)
    .forEach((el) => el.classList.remove(expandedClass));
}

/** Makes `marker` expand on tap and collapse on a second tap, closing whatever
 * else was open first. Call before adding the marker to the map. */
export function bindExpandableMarker(
  marker: L.Marker,
  map: L.Map,
  innerClass: string,
  expandedClass: string,
): void {
  marker.on("click", () => {
    const inner = marker.getElement()?.querySelector<HTMLElement>(`.${innerClass}`);
    const wasExpanded = inner?.classList.contains(expandedClass);
    collapseExpandable(map, innerClass, expandedClass);
    if (inner && !wasExpanded) inner.classList.add(expandedClass);
  });
}
