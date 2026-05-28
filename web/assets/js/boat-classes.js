// Shared boat-class catalogue + form helpers, used by both the race
// dashboard (race-app.js) and the events admin (events-app.js).
//
// The dropdown is parameterized by an `idPrefix` so the same component
// can live in two modals simultaneously (race-edit + regatta-edit) on
// the same page without DOM-id collisions.

// beam_m is the maximum hull beam (one-design class spec). Used to draw
// the real-scale hull polygon on the map; falls back to ~32% of LOA for
// custom classes (matches the four built-ins within ±0.02 m).
export const BOAT_CLASSES = [
    { id: 'j80',      name: 'J/80',      loa_m: 8.00, beam_m: 2.51, bow_offset_m: 3.00 },
    { id: 'sonar23',  name: 'Sonar 23',  loa_m: 7.01, beam_m: 2.18, bow_offset_m: 2.50 },
    { id: 'rhodes19', name: 'Rhodes 19', loa_m: 5.79, beam_m: 1.93, bow_offset_m: 1.70 },
    { id: 'i420',     name: '420',       loa_m: 4.20, beam_m: 1.63, bow_offset_m: 1.50 },
];

export const DEFAULT_BOAT_CLASS_ID = 'j80';
export const DEFAULT_BOAT_LOA_M    = 8.0;
export const DEFAULT_BOAT_BEAM_M   = 2.51;
export const DEFAULT_BOW_OFFSET_M  = 3.0;

export function boatClassById(id) {
    return BOAT_CLASSES.find(c => c.id === id) || null;
}

export function metersToFeet(m) {
    return m * 3.28084;
}

export function formatLoa(m) {
    return `${m.toFixed(2)} m / ${metersToFeet(m).toFixed(1)} ft`;
}

export function classHint(cls) {
    if (!cls) return '';
    const zone = (cls.loa_m * 3).toFixed(1);
    const bow  = (cls.bow_offset_m != null ? cls.bow_offset_m : DEFAULT_BOW_OFFSET_M).toFixed(2);
    return `Zone radius ${zone} m · GPS-antenna→bow ${bow} m`;
}

// Normalize an incoming boat_class value to the canonical {id, name,
// loa_m, bow_offset_m} shape. Accepts:
//   - null / undefined → null
//   - structured object → returned as-is
//   - legacy string "J/80" → resolved against BOAT_CLASSES by name/id
export function normalizeBoatClass(input) {
    if (!input) return null;
    if (typeof input === 'string') {
        const t = input.trim();
        if (!t) return null;
        return BOAT_CLASSES.find(c => c.name === t || c.id === t.toLowerCase()) || null;
    }
    return input;
}

function _ids(prefix = '') {
    return {
        select:       `${prefix}boat-class-input`,
        customGroup:  `${prefix}boat-class-custom-group`,
        customName:   `${prefix}boat-class-custom-name`,
        customLoa:    `${prefix}boat-class-custom-loa`,
        customOffset: `${prefix}boat-class-custom-offset`,
        hint:         `${prefix}boat-class-hint`,
    };
}

export function populateBoatClassDropdown(prefix = '') {
    const ids = _ids(prefix);
    const sel = document.getElementById(ids.select);
    if (!sel || sel.dataset.populated === '1') return;
    // value="" → no overall class. Used for mixed handicap fleets
    // where each boat has its own LOA from the boats catalog; the
    // race-level boat_class is meaningless then. Listed first so the
    // dropdown surfaces it as a deliberate choice.
    sel.innerHTML =
        '<option value="">— No overall class (mixed handicap)</option>'
        + BOAT_CLASSES.map(c =>
            `<option value="${c.id}">${c.name} — ${formatLoa(c.loa_m)}</option>`
        ).join('')
        + '<option value="__custom__">Custom…</option>';
    sel.dataset.populated = '1';

    sel.addEventListener('change', () => {
        const customGroup = document.getElementById(ids.customGroup);
        const hint        = document.getElementById(ids.hint);
        if (sel.value === '__custom__') {
            if (customGroup) customGroup.style.display = '';
            if (hint) hint.textContent = 'Zone radius = 3 × LOA · bow offset projects antenna fix forward for OCS / zone-entry';
        } else if (sel.value === '') {
            if (customGroup) customGroup.style.display = 'none';
            if (hint) hint.textContent = 'Per-boat LOA from the catalog drives hull rendering · mark zone = 3 × largest boat\'s LOA';
        } else {
            if (customGroup) customGroup.style.display = 'none';
            const cls = boatClassById(sel.value);
            if (hint) hint.textContent = classHint(cls);
        }
    });
}

export function setBoatClassInForm(boatClass, prefix = '') {
    const ids = _ids(prefix);
    const sel = document.getElementById(ids.select);
    if (!sel) return;
    const customGroup  = document.getElementById(ids.customGroup);
    const customName   = document.getElementById(ids.customName);
    const customLoa    = document.getElementById(ids.customLoa);
    const customOffset = document.getElementById(ids.customOffset);
    const hint         = document.getElementById(ids.hint);

    const normalized = normalizeBoatClass(boatClass);
    const knownIds   = new Set(BOAT_CLASSES.map(c => c.id));

    if (normalized && normalized.id && knownIds.has(normalized.id)) {
        sel.value = normalized.id;
        if (customGroup)  customGroup.style.display = 'none';
        if (customName)   customName.value = '';
        if (customLoa)    customLoa.value = '';
        if (customOffset) customOffset.value = '';
        if (hint)         hint.textContent = classHint(boatClassById(normalized.id));
    } else if (normalized && normalized.loa_m) {
        sel.value = '__custom__';
        if (customGroup)  customGroup.style.display = '';
        if (customName)   customName.value = normalized.name || '';
        if (customLoa)    customLoa.value  = normalized.loa_m;
        if (customOffset) customOffset.value = normalized.bow_offset_m != null ? normalized.bow_offset_m : '';
        if (hint)         hint.textContent = 'Custom class — bow offset projects antenna fix forward for OCS / zone-entry';
    } else if (boatClass === null) {
        // Explicit "no class" — preserves the editor's "(none)" state
        // across re-opens of a handicap race. (boatClass=undefined
        // still falls through to the default below.)
        sel.value = '';
        if (customGroup)  customGroup.style.display = 'none';
        if (customName)   customName.value = '';
        if (customLoa)    customLoa.value = '';
        if (customOffset) customOffset.value = '';
        if (hint)         hint.textContent = 'Per-boat LOA from the catalog drives hull rendering · mark zone = 3 × largest boat\'s LOA';
    } else {
        sel.value = DEFAULT_BOAT_CLASS_ID;
        if (customGroup)  customGroup.style.display = 'none';
        if (customName)   customName.value = '';
        if (customLoa)    customLoa.value = '';
        if (customOffset) customOffset.value = '';
        if (hint)         hint.textContent = classHint(boatClassById(DEFAULT_BOAT_CLASS_ID));
    }
}

export function getBoatClassFromForm(prefix = '') {
    const ids = _ids(prefix);
    const sel = document.getElementById(ids.select);
    if (!sel) return null;
    // Explicit "no class" — saved as null so the race record carries
    // no boat_class field at all. The dashboard then reads per-boat
    // LOA from the catalog.
    if (sel.value === '') return null;
    if (sel.value === '__custom__') {
        const name      = (document.getElementById(ids.customName)?.value || '').trim();
        const loa       = parseFloat(document.getElementById(ids.customLoa)?.value || '');
        const offsetRaw = document.getElementById(ids.customOffset)?.value || '';
        if (!name || !Number.isFinite(loa) || loa <= 0) {
            throw new Error('Custom boat class needs a name and a positive LOA in meters');
        }
        let bowOffset = parseFloat(offsetRaw);
        if (!Number.isFinite(bowOffset) || bowOffset < 0) bowOffset = loa * 0.38;
        return {
            id: `custom_${name.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`,
            name,
            loa_m: loa,
            bow_offset_m: Math.round(bowOffset * 100) / 100,
        };
    }
    const cls = boatClassById(sel.value);
    return cls ? { ...cls } : null;
}
