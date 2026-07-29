/** Escapes user-supplied text before it goes into an `innerHTML` string.
 * Needed wherever we hand markup to Leaflet (popups, div icons) rather than
 * letting React do the escaping — boat names, club names and OSM `name` tags
 * are all attacker-controllable in principle. */
export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
