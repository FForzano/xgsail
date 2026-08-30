import type L from "leaflet";
import styles from "./compactAttribution.module.css";

/** Makes Leaflet's attribution fit a phone without hiding the credit.
 *
 * On a narrow screen the full credit wraps onto two lines and runs under the
 * map's own floating controls. The OSM Foundation's attribution guidelines
 * allow exactly this case: the credit may be collapsed as long as "the user
 * must still be able to find the licence information if they look for it, for
 * example from an '(i)' button in the corner of the map". So on phones the
 * text collapses behind such a button; on wider screens nothing is hidden.
 *
 * Two things are deliberate:
 *
 * - Leaflet's own prefix (its flag + "Leaflet" link) is dropped. Leaflet is
 *   MIT-licensed and asks for no attribution, and that prefix is most of what
 *   pushed the line to wrap in the first place. The data credits stay.
 * - The toggle is a *sibling* of the attribution container, not a child.
 *   `L.Control.Attribution` rewrites its container's `innerHTML` every time a
 *   layer is added or removed (which is how OpenSeaMap's credit appears and
 *   disappears with its overlay), so a button placed inside would vanish the
 *   first time the user toggled a layer.
 */
export function installCompactAttribution(map: L.Map, label: string): void {
  const control = map.attributionControl;
  if (!control) return;
  control.setPrefix(false);

  const container = control.getContainer();
  const corner = container?.parentElement;
  if (!container || !corner) return;

  container.classList.add(styles.collapsed);

  const toggle = document.createElement("button");
  toggle.type = "button";
  // `leaflet-control` is not decoration: Leaflet's corner containers are
  // `pointer-events: none` and only elements carrying that class get pointer
  // events back, so without it the button simply cannot be clicked. It also
  // opts the button into the corner's float/clear stacking and its 10px
  // margins, which is what puts it on its own row.
  toggle.className = `${styles.toggle} leaflet-control`;
  // The visible button is just an "(i)", as the guidelines' own example has
  // it. `label` is the accessible name only: a screen reader announcing "i,
  // button" would tell a blind user nothing, so that one place needs words.
  toggle.textContent = "i";
  toggle.setAttribute("aria-label", label);
  toggle.setAttribute("aria-expanded", "false");
  toggle.addEventListener("click", (event) => {
    // Otherwise Leaflet reads the tap as a click on the map underneath, which
    // in picker mode would drop a pin where the button is.
    event.stopPropagation();
    const collapsed = container.classList.toggle(styles.collapsed);
    toggle.setAttribute("aria-expanded", String(!collapsed));
  });

  // Moved to the end of the corner so the stack reads, bottom-up: the "(i)"
  // in the very corner, the credit above it when expanded, and the zoom
  // control above both — where it lines up with the page's other round
  // controls. Leaflet stacks a corner's children in DOM order, top to bottom.
  corner.appendChild(container);
  corner.appendChild(toggle);
}
