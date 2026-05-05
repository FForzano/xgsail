/**
 * Race Dashboard Application
 *
 * Main controller for the multi-boat race dashboard.
 * Handles race selection, data loading, map visualization,
 * and playback controls.
 */

// Check if user is authenticated via Cloudflare Access
function isAdmin() {
    return document.cookie.includes('CF_Authorization');
}
const IS_ADMIN = isAdmin();

// Configuration
const API_BASE = window.SAILFRAMES_API_URL || window.location.origin;
const BOAT_COLORS = {
    'E1': '#1d9bf0',  // Blue
    'E2': '#f59e0b',  // Orange
    'E3': '#00ba7c',  // Green
    'E4': '#f4212e',  // Red
    'E5': '#a855f7',  // Purple
    'E6': '#22d3ee',  // Cyan
};

// Single source of truth for "what color is this boat?" — keyed by
// device id so the polyline, marker, label, leaderboard swatch, and
// chart line/toggle are guaranteed to render the same color for the
// same boat. Use this everywhere instead of indexing BOAT_COLORS
// directly so any future fallback policy stays consistent.
function colorFor(deviceId) {
    return BOAT_COLORS[deviceId] || '#888888';
}

// Fleet configuration - COURAGEOUS J80 Spring Racing Series 2026
const FLEET_BOATS = ['Wizard', 'Fins', 'Doc Buck', 'Katu', 'Bliss & Ella', 'Amigo'];
const FLEET_TEAMS = ['Vela Veloce', 'Seadogs', 'Mystic Mutiny', 'Rooster Alumni Club', 'Anchor Management', 'Team 6'];

// State
let regattas = [];
let raceDays = [];  // Race days for selected regatta
let races = [];     // Races for selected race day
let currentRaceDay = null;
let currentRace = null;
let raceData = null;
let map = null;
let boatLayers = {};  // device_id -> { track, marker }
let isPlaying = false;
let playbackSpeed = 1;
let currentTime = 0;  // seconds from race start
let raceDuration = 0;
let playbackInterval = null;
let speedChart = null;
let heelChart = null;
let windChart = null;
let playCursorSeconds = 0;

// Wind data from nearby NOAA stations (Castle Island CSIM3, Logan KBOS,
// Boston 16NM 44013). One boat has an onboard Calypso; the rest don't.
// CSIM3 is ~3 km from Boston Harbor sailing waters with marine
// instrumentation, so it's the right authoritative TWD/TWS source for
// fleet-wide tactical metrics (laylines, TWA, wind badge).
let raceBuoyData = {};            // {stationId: {data_points, lat, lon, name, color, ...}}
let weatherWindSamples = [];       // sorted [{tMs, twd, tws}] from primary source
let weatherWindSource = null;      // "Castle Island" / "Logan" / null
let raceAvgTWD = null;             // average TWD across the race window, for laylines
let laylineLayer = null;           // Leaflet layer group holding rendered laylines
let windMarker = null;             // legacy single-marker (kept for compatibility)
let windMarkers = {};              // stationId → Leaflet marker (multi-station rendering)
let windStationStats = {};         // stationId → { meanTWD, stdTWD, minTWS, maxTWS, avgTWS, sampleCount }
let _windDropdownOutsideListener = null;  // ref-tracked so re-renders don't leak handlers

// Set of station IDs to show in dropdown + on map. Computed every picker
// render to dedupe stations that point at the same physical sensor through
// multiple aggregator paths (e.g. KBOS direct vs SYN_KBOS via Synoptic).
let visibleStationIds = new Set();
// Preferred-first ordering for the auto-pick. Synoptic SYN_* stations
// are added dynamically below if/when they appear in the API response.
// Order matters: the auto-pick at race load walks this list and takes the
// first station with usable samples. Boston 16NM (NDBC 44013) is the
// operational default for the Boston Harbor fleet — open-ocean buoy with
// the cleanest signal (no land/airport interference); Logan (KBOS) and
// Castle Island (CSIM3) are fallbacks when 44013 has dropouts.
const PRIMARY_WIND_STATIONS = ['44013', 'KBOS', 'CSIM3'];
let selectedWindStationId = null;  // user-selected wind source (null = auto-pick)

// User-controlled visibility toggles. Defaults are ON so the dashboard
// shows everything on first load; per-user overrides persist through
// a race session but reset when the page reloads (intentional — no
// cross-session state).
let laylinesVisible = true;
// Trail window: how much past track to render as a polyline. Default 1 min
// keeps the map readable; "All" (Infinity) restores the historical full-race
// behavior. Changing this re-renders every boat's trail at the current
// playback time.
let trailWindowMs = 60_000;
// Index into currentRace.course of the next mark the leader has yet to round.
// Drives "next windward only" layline rendering — when the leader rounds the
// current target, laylines shift to the next mark (and disappear if that
// mark is downwind). 0 = pre-start, course.length = finished.
let activeLeg = 0;
// TWD used to draw the currently rendered laylines. Updated each playback
// tick from windAt(targetTime) so the laylines pivot when the wind shifts.
// null = haven't sampled yet → renderLaylines falls back to raceAvgTWD.
let lastLaylineTWD = null;

// Per-marker overlay toggles, controlled by the top-right Leaflet legend.
// Each item adds (or removes) one piece of information from every boat's
// map cursor / track in real time. Defaults match the most-used readout.
//   trail — the colored polyline behind the boat (still trimmed by the
//           top-right trail-window picker for duration)
//   speed — current SOG in knots, beside the arrow
//   heel  — heel angle from the IMU, with Sd/Pt prefix
//   twa   — true wind angle (signed; P/S prefix). Per-boat — derived from
//           NOAA TWD and the boat's COG, so it works for every boat
//           regardless of whether they have an onboard wind sensor. This
//           is the most actionable wind metric on a boat marker: AWA is
//           nice but only one boat in the fleet has the Calypso, and TWD
//           is fleet-global (already on the wind picker).
let markerOverlays = {
    trail: true,
    speed: true,
    heel:  true,
    twa:   true,
};

// Auto-follow: keep the map framed on the current race leader and the
// mark they're sailing toward. Re-fits bounds at most every 700 ms to
// avoid jitter during slider scrubbing or fast playback. Toggle in the
// topright FOLLOW control; persisted to localStorage.
let followLeader = true;
let lastFollowPanMs = 0;
let polarOverlayVisible = true;

// J/80 typical upwind tack angle (degrees off true wind). Used for laylines.
const J80_UPWIND_TACK_ANGLE = 42;

// J/80 polar table (Seapilot format, 2018 publication).
// Columns: TWS in knots. Rows: target boat speed in knots at each (TWA, TWS).
// Source: https://www.seapilot.com/wp-content/uploads/2018/05/J80.txt
const J80_TWS = [6, 8, 10, 12, 14, 16, 20];
const J80_TWA_TABLE = [52.5, 60, 75, 90, 105, 120, 135, 150, 165, 180];
const J80_BSPEED_TABLE = [
    [5.514, 6.369, 6.818, 7.039, 7.178, 7.261, 7.311],  // 52.5°
    [5.787, 6.677, 7.125, 7.344, 7.492, 7.575, 7.670],  // 60°
    [6.235, 7.013, 7.473, 7.830, 8.024, 8.164, 8.345],  // 75°
    [6.733, 7.380, 7.726, 7.957, 8.303, 8.613, 8.923],  // 90°
    [6.775, 7.537, 8.031, 8.326, 8.582, 8.812, 9.197],  // 105°
    [6.381, 7.326, 8.021, 8.573, 8.999, 9.273, 9.753],  // 120°
    [5.605, 6.634, 7.317, 7.881, 8.439, 8.935, 9.813],  // 135°
    [3.928, 5.127, 5.953, 6.638, 7.190, 7.658, 8.557],  // 150°
    [2.996, 3.970, 4.897, 5.706, 6.375, 6.934, 7.763],  // 165°
    [2.799, 3.752, 4.617, 5.450, 6.115, 6.727, 7.632],  // 180°
];
const J80_BEAT_ANGLE = [45.2, 41.4, 40.4, 40.0, 39.8, 39.9, 39.9];
const J80_BEAT_VMG   = [3.550, 4.224, 4.561, 4.765, 4.880, 4.951, 4.960];

// Bilinear-interp target boat speed for given TWA (signed) and TWS.
function polarTargetSpeed(twaSigned, tws) {
    if (twaSigned == null || tws == null || !Number.isFinite(tws) || tws <= 0) return null;
    // Polar is symmetric port/starboard
    let a = Math.abs(twaSigned);
    if (a > 180) a = 360 - a;

    // Clamp TWS to polar range
    const twsArr = J80_TWS;
    const tt = Math.max(twsArr[0], Math.min(twsArr[twsArr.length - 1], tws));

    // TWS bracket
    let iLo = 0;
    while (iLo < twsArr.length - 1 && twsArr[iLo + 1] <= tt) iLo++;
    const iHi = Math.min(iLo + 1, twsArr.length - 1);
    const twsF = (iHi === iLo) ? 0 : (tt - twsArr[iLo]) / (twsArr[iHi] - twsArr[iLo]);

    // Per-TWS speed at TWA `a`. Synth a row at the optimal beat angle so
    // 40°-52.5° has a slope and TWAs below the beat angle return a graceful
    // pinching estimate (linear from 0 to beatSpeed).
    const speedAtCol = (col) => {
        const beatA = J80_BEAT_ANGLE[col];
        const beatSpd = J80_BEAT_VMG[col] / Math.cos(beatA * Math.PI / 180);
        if (a <= beatA) {
            // Below optimal — pinching. Crude linear from (0,0) to (beatA,beatSpd).
            return Math.max(0, (a / beatA) * beatSpd);
        }
        const angles = [beatA, ...J80_TWA_TABLE];
        const speeds = [beatSpd, ...J80_BSPEED_TABLE.map(row => row[col])];
        let aLo = 0;
        while (aLo < angles.length - 1 && angles[aLo + 1] < a) aLo++;
        const aHi = Math.min(aLo + 1, angles.length - 1);
        const aF = (aHi === aLo) ? 0 : (a - angles[aLo]) / (angles[aHi] - angles[aLo]);
        return speeds[aLo] * (1 - aF) + speeds[aHi] * aF;
    };

    const sLo = speedAtCol(iLo);
    const sHi = speedAtCol(iHi);
    return sLo * (1 - twsF) + sHi * twsF;
}

function polarPercent(sog, twaSigned, tws) {
    const target = polarTargetSpeed(twaSigned, tws);
    if (!target || target <= 0.1) return null;
    return (sog / target) * 100;
}
let availableSessions = {};  // device_id -> [session paths]
let pendingGpxFiles = {};   // device_id -> File (staged GPX uploads)

// Pre-race display: show 3 minutes before start
const PRE_RACE_SECONDS = 180;

// Initialize
document.addEventListener('DOMContentLoaded', init);

async function init() {
    console.log('[Race] Initializing race dashboard...');

    // Hide admin controls for non-authenticated users
    if (!IS_ADMIN) {
        document.getElementById('btn-new-race').style.display = 'none';
        document.getElementById('btn-edit-race').style.display = 'none';
        const editCourseBtn = document.getElementById('btn-edit-course');
        if (editCourseBtn) editCourseBtn.style.display = 'none';
    }

    // Initialize map
    initMap();
    addLaylinesMapControl();
    addFollowLeaderMapControl();
    addMarkerOverlaysMapControl();   // includes the trail-window dropdown
    addMapWindPicker();
    setupChartsOverlay();

    // Initialize chart
    initSpeedChart();

    // Load regattas (race days and races loaded on selection)
    await loadRegattas();

    // Setup event listeners
    setupEventListeners();

    // Drawer close
    const drawerClose = document.getElementById('drawer-close');
    if (drawerClose) drawerClose.addEventListener('click', closeBoatDrawer);
    // Esc key closes the drawer / open modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (drawerDeviceId) closeBoatDrawer();
            for (const id of ['leg-modal', 'maneuver-modal']) {
                const m = document.getElementById(id);
                if (m && m.style.display !== 'none') m.style.display = 'none';
            }
        }
    });

    // Modal close buttons
    for (const el of document.querySelectorAll('[data-close-modal]')) {
        el.addEventListener('click', () => {
            const id = el.getAttribute('data-close-modal');
            const m = document.getElementById(id);
            if (m) m.style.display = 'none';
        });
    }

    // Polar overlay toggle
    const polTog = document.getElementById('polar-overlay-toggle');
    if (polTog) polTog.addEventListener('click', () => {
        polarOverlayVisible = !polarOverlayVisible;
        polTog.classList.toggle('active', polarOverlayVisible);
        updateSpeedChart();
    });

    // Legs / Maneuvers modals
    const legBtn = document.getElementById('btn-leg-summary');
    if (legBtn) legBtn.addEventListener('click', openLegModal);
    const manBtn = document.getElementById('btn-maneuvers');
    if (manBtn) manBtn.addEventListener('click', openManeuverModal);

    // Mobile UX (only active when viewport ≤ 900 px — see race.css media query)
    setupMobileNav();

    // Ensure Leaflet has correct dimensions after initial CSS layout settles
    // (on mobile the map panel height depends on flex:1 inside .race-main,
    // which isn't necessarily resolved when initMap() runs).
    setTimeout(() => { if (map) map.invalidateSize(); }, 250);
    window.addEventListener('resize', () => {
        if (map) map.invalidateSize();
    });

    // Auto-load the most recent race with boat data
    await loadLatestRaceWithData();

    console.log('[Race] Dashboard ready');
}

async function loadLatestRaceWithData() {
    try {
        // Fetch all races
        const resp = await fetch(`${API_BASE}/api/races`);
        const data = await resp.json();
        const allRaces = data.races || [];

        const now = new Date();

        // Find races with boats assigned (boat_count > 0), not in the future, sorted by date descending
        const racesWithBoats = allRaces
            .filter(r => r.boat_count > 0 && new Date(r.start_time) <= now)
            .sort((a, b) => {
                // Sort by start_time descending (most recent first)
                return new Date(b.start_time) - new Date(a.start_time);
            });

        if (racesWithBoats.length === 0) {
            console.log('[Race] No past races with boats found');
            return;
        }

        // Pick the latest race DAY, then load its FIRST race (Race 1).
        // Auto-loading the most recent race outright was unhelpful when
        // a regatta day has 3 races — racers want to start their replay
        // at the beginning of the day, not at race 3.
        const latestDate = racesWithBoats[0].date;
        const dayRaces = racesWithBoats
            .filter(r => r.date === latestDate)
            .sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
        const targetRace = dayRaces[0];
        console.log('[Race] Auto-loading first race of latest day:', targetRace.name, targetRace.date, targetRace.race_id);

        // Set the regatta dropdown (use __all__ for races without regatta)
        const regattaId = targetRace.regatta_id || '__all__';
        document.getElementById('regatta-select').value = regattaId;
        await loadRaceDays(regattaId);

        // Set the race day dropdown
        document.getElementById('raceday-select').value = targetRace.date;
        loadRacesForDay(targetRace.date);

        // Set the race dropdown
        document.getElementById('race-select').value = targetRace.race_id;

        // Load the race data
        await loadRaceData(targetRace.race_id);

    } catch (err) {
        console.error('[Race] Failed to auto-load latest race:', err);
    }
}

// --- Map ---

function initMap() {
    map = L.map('race-map', {
        center: [42.36, -71.05],  // Boston Harbor
        zoom: 14,
        zoomControl: true,
        maxZoom: 20,  // Allow deep zoom regardless of tile layer limits
    });

    // Base layers
    const baseLayers = {
        'NOAA Charts': L.tileLayer.wms('https://gis.charttools.noaa.gov/arcgis/rest/services/MCS/NOAAChartDisplay/MapServer/exts/MaritimeChartService/WMSServer', {
            layers: '0,1,2,3,4,5,6,7',
            format: 'image/png',
            transparent: true,
            attribution: '&copy; <a href="https://nauticalcharts.noaa.gov">NOAA</a>',
            maxZoom: 18,
        }),
        'Dark': L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap, &copy; CARTO',
            maxZoom: 19,
        }),
        // Same Carto dark_all tiles as "Dark", but inverted + hue-shifted
        // via CSS so the dark canvas reads as a soft light blue. The
        // .tile-light-blue class is defined in race.css.
        'Light Blue': L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap, &copy; CARTO',
            maxZoom: 19,
            className: 'tile-light-blue',
        }),
        'OSM': L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://openstreetmap.org">OpenStreetMap</a> contributors',
            maxZoom: 19,
        }),
        'ESRI Ocean': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}', {
            attribution: '&copy; Esri, GEBCO, NOAA, National Geographic',
            maxNativeZoom: 13,  // Tiles only exist up to zoom 13
            maxZoom: 20,        // Allow overzoom (stretches tiles)
        }),
        'Satellite': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: '&copy; Esri',
            maxZoom: 19,
        }),
    };

    // Overlay layers (nautical marks)
    const overlayLayers = {
        'OpenSeaMap': L.tileLayer('https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openseamap.org">OpenSeaMap</a>',
            maxZoom: 18,
            opacity: 0.8,
        }),
        'SHOM Bathymetry (FR)': L.tileLayer.wms('https://services.data.shom.fr/INSPIRE/wms/r', {
            layers: 'LITTO3D_GUAD_2016_PYR_3857_WMSR,LITTO3D_MART_2016_PYR_3857_WMSR',
            format: 'image/png',
            transparent: true,
            attribution: '&copy; <a href="https://data.shom.fr">SHOM</a>',
            maxZoom: 18,
            opacity: 0.7,
        }),
    };

    // ESRI Ocean is the default — best legibility under colored boat
    // tracks at typical Boston Harbor zoom levels (NOAA charts and
    // OpenSeaMap stay available in the layers control).
    baseLayers['ESRI Ocean'].addTo(map);

    // Add layer control
    L.control.layers(baseLayers, overlayLayers, {
        position: 'topright',
        collapsed: true,
    }).addTo(map);
}

function clearBoatLayers() {
    for (const deviceId of Object.keys(boatLayers)) {
        if (boatLayers[deviceId].track) {
            map.removeLayer(boatLayers[deviceId].track);
        }
        if (boatLayers[deviceId].marker) {
            map.removeLayer(boatLayers[deviceId].marker);
        }
    }
    boatLayers = {};
    if (laylineLayer) {
        map.removeLayer(laylineLayer);
        laylineLayer = null;
    }
    // Reset leader-leg pointer so prior race's state doesn't bleed into the
    // freshly loaded one (laylines redraw to course[0] on next leaderboard tick).
    activeLeg = 0;
    // Drop the cached layline TWD too — next syncLaylineWind() tick will
    // resample from the new race's wind data.
    lastLaylineTWD = null;
    if (windMarker) {
        map.removeLayer(windMarker);
        windMarker = null;
    }
    for (const sid of Object.keys(windMarkers)) {
        if (windMarkers[sid]) map.removeLayer(windMarkers[sid]);
    }
    windMarkers = {};
    windStationStats = {};
}

// Project a point (lat, lon, bearingDegrees, distMeters) to a destination
// lat/lon. Earth-radius approximation, flat-earth-friendly for ≤10 km legs.
function destinationPoint(lat, lon, bearingDeg, distM) {
    const R = 6371000;
    const φ1 = lat * Math.PI / 180;
    const λ1 = lon * Math.PI / 180;
    const θ = bearingDeg * Math.PI / 180;
    const dR = distM / R;
    const φ2 = Math.asin(Math.sin(φ1) * Math.cos(dR) +
                          Math.cos(φ1) * Math.sin(dR) * Math.cos(θ));
    const λ2 = λ1 + Math.atan2(Math.sin(θ) * Math.sin(dR) * Math.cos(φ1),
                                Math.cos(dR) - Math.sin(φ1) * Math.sin(φ2));
    return [φ2 * 180 / Math.PI, λ2 * 180 / Math.PI];
}

// Draw port + starboard upwind laylines from each upcoming windward mark.
// "Windward" is determined relative to the race-average TWD: if the mark
// is in the upper half-plane relative to the wind (mark bearing within
// ±90° of TWD as seen from the start), it counts. Length is scaled to be
// visible across a typical Boston Harbor course (~3 km).
function addLaylinesMapControl() {
    if (!map) return;
    const ctl = L.control({ position: 'topright' });
    ctl.onAdd = function () {
        const div = L.DomUtil.create('div', 'leaflet-bar map-toggle-control');
        div.innerHTML = `<a href="#" id="layline-toggle" class="${laylinesVisible ? 'active' : ''}" title="Show/hide laylines">⌃ Laylines</a>`;
        L.DomEvent.disableClickPropagation(div);
        const a = div.querySelector('#layline-toggle');
        a.addEventListener('click', (e) => {
            e.preventDefault();
            laylinesVisible = !laylinesVisible;
            a.classList.toggle('active', laylinesVisible);
            // When turning on, snap immediately to the wind at the playback
            // cursor instead of waiting for the next updateBoatPositions tick.
            if (laylinesVisible && currentRace) {
                const targetMs = new Date(currentRace.start_time).getTime() + (playCursorSeconds * 1000);
                lastLaylineTWD = null;  // force re-sample
                syncLaylineWind(targetMs);
            }
            renderLaylines();
        });
        return div;
    };
    ctl.addTo(map);
}

// Auto-follow toggle. When on, the map flies to the current leader and
// the mark they're heading toward, re-framing as the fleet progresses
// through windward / leeward / second beat / finish. When off the user
// has full manual pan/zoom control. Default ON; persisted across races.
function addFollowLeaderMapControl() {
    if (!map) return;
    try {
        const saved = localStorage.getItem('sf-follow-leader');
        if (saved !== null) followLeader = saved === '1';
    } catch {}
    const ctl = L.control({ position: 'topright' });
    ctl.onAdd = function () {
        const div = L.DomUtil.create('div', 'leaflet-bar map-toggle-control');
        div.innerHTML = `<a href="#" id="follow-toggle" class="${followLeader ? 'active' : ''}" title="Auto-pan/zoom to keep the leader and next mark on screen">⚐ Follow</a>`;
        L.DomEvent.disableClickPropagation(div);
        const a = div.querySelector('#follow-toggle');
        a.addEventListener('click', (e) => {
            e.preventDefault();
            followLeader = !followLeader;
            a.classList.toggle('active', followLeader);
            try { localStorage.setItem('sf-follow-leader', followLeader ? '1' : '0'); } catch {}
            if (followLeader && currentRace) {
                applyLeaderFollow(true);
            }
        });
        return div;
    };
    ctl.addTo(map);
}

// Pan the map so the fleet stays on screen, WITHOUT changing zoom.
// Pressing play used to fitBounds the whole course and snap the user
// back to a wide view, undoing the start-line zoom-in. Now we just
// pan the camera centre to the midpoint between the leader and the
// mark they're chasing — the user keeps whatever zoom they set
// (initial start-line zoom, or anything they pinch to manually).
//
// Throttled (2.5 s) so scrubbing doesn't ricochet, and pan flight is
// slow (1.4 s, ease-out) so the motion reads as a glide. Hysteresis:
// skip the pan when the target centre is already close to the current
// map centre (less than ~25 % of the viewport away) — avoids twitchy
// micro-corrections.
function applyLeaderFollow(force = false, targetTimeMsArg = null) {
    if (!followLeader && !force) return;
    if (!map || !currentRace) return;
    const now = Date.now();
    if (!force && now - lastFollowPanMs < 2500) return;

    const courseSeq = currentRace.course || [];
    const marksById = courseSeq.length ? buildMarksById(currentRace) : {};
    const targetTimeMs = targetTimeMsArg
        ?? new Date(currentRace.start_time).getTime() + (playCursorSeconds * 1000);

    // Find the leader (most rounding events; ties → closest to next mark)
    // and remember their position + the mark they're heading to.
    let leaderPos = null;
    let leaderLegs = -1;
    let leaderDist = Infinity;
    let leaderNextMark = null;
    for (const layer of Object.values(boatLayers)) {
        if (!layer.visible || !layer.current) continue;
        const legs = legsCompletedAt(layer, targetTimeMs);
        let nextMark = null, d = Infinity;
        if (courseSeq.length) {
            const seqIdx = legs % courseSeq.length;
            nextMark = marksById[courseSeq[seqIdx]];
            if (nextMark) d = haversineMeters(layer.current.lat, layer.current.lon, nextMark.lat, nextMark.lon);
        }
        if (legs > leaderLegs || (legs === leaderLegs && d < leaderDist)) {
            leaderLegs = legs;
            leaderDist = d;
            leaderNextMark = nextMark;
            leaderPos = [layer.current.lat, layer.current.lon];
        }
    }
    if (!leaderPos) return;

    // Camera target: midpoint between leader and next mark when one
    // exists, else just the leader. This biases the view slightly
    // ahead of the leader so what they're sailing toward is visible.
    let targetCentre;
    const totalLegs = currentRace._totalLegs ?? courseSeq.length;
    if (courseSeq.length && leaderLegs < totalLegs && leaderNextMark) {
        targetCentre = L.latLng(
            (leaderPos[0] + leaderNextMark.lat) / 2,
            (leaderPos[1] + leaderNextMark.lon) / 2
        );
    } else if (currentRace.finish_line?.pin_lat != null) {
        const fl = currentRace.finish_line;
        const flMidLat = (fl.pin_lat + fl.boat_lat) / 2;
        const flMidLon = (fl.pin_lon + fl.boat_lon) / 2;
        targetCentre = L.latLng((leaderPos[0] + flMidLat) / 2, (leaderPos[1] + flMidLon) / 2);
    } else {
        targetCentre = L.latLng(leaderPos[0], leaderPos[1]);
    }

    // Hysteresis in screen-pixel space: if the new centre projects to
    // within ~25 % of the viewport diagonal of the current centre, the
    // fleet is still well-framed at the current zoom — no need to pan.
    if (!force) {
        const sz = map.getSize();
        const cur = map.latLngToLayerPoint(map.getCenter());
        const tgt = map.latLngToLayerPoint(targetCentre);
        const dx = tgt.x - cur.x, dy = tgt.y - cur.y;
        const distPx = Math.sqrt(dx * dx + dy * dy);
        const threshold = 0.25 * Math.min(sz.x, sz.y);
        if (distPx < threshold) return;
    }

    lastFollowPanMs = now;
    // panTo with animation — preserves current zoom level.
    map.panTo(targetCentre, {
        animate: true,
        duration: 1.4,
        easeLinearity: 0.25,
    });
}

// Trail window options shown in the SHOW > Trail dropdown. 30s exists
// for tight tactical replay, "All" restores the historical full-race
// behavior. Note that `Infinity` is encoded as the string "Infinity" in
// the option value because <select> coerces values to strings.
const TRAIL_WINDOW_OPTIONS = [
    { label: '30s', ms: 30_000 },
    { label: '1m',  ms: 60_000 },
    { label: '5m',  ms: 5 * 60_000 },
    { label: '10m', ms: 10 * 60_000 },
    { label: 'All', ms: Infinity },
];

// Top-right legend: per-marker overlay toggles. Each row drives whether
// a particular piece of info is rendered on the boat cursor; the Trail
// row also exposes a duration dropdown that combines what used to be a
// separate TRAIL Leaflet control. State lives in `markerOverlays` and
// `trailWindowMs`, both persisted to localStorage so the user's choices
// stick across races.
function addMarkerOverlaysMapControl() {
    if (!map) return;
    // Hydrate from prior session if present.
    try {
        const saved = JSON.parse(localStorage.getItem('sf-marker-overlays') || 'null');
        if (saved && typeof saved === 'object') {
            for (const k of Object.keys(markerOverlays)) {
                if (typeof saved[k] === 'boolean') markerOverlays[k] = saved[k];
            }
        }
        const savedWin = localStorage.getItem('sf-trail-window-ms');
        if (savedWin) {
            const n = (savedWin === 'Infinity') ? Infinity : Number(savedWin);
            if (Number.isFinite(n) || n === Infinity) trailWindowMs = n;
        }
    } catch {}

    const items = [
        { key: 'trail', label: 'Trail' },
        { key: 'speed', label: 'Speed' },
        { key: 'heel',  label: 'Heel' },
        { key: 'twa',   label: 'TWA' },
    ];

    const ctl = L.control({ position: 'topright' });
    ctl.onAdd = function () {
        const div = L.DomUtil.create('div', 'leaflet-bar map-toggle-control marker-overlays-control');
        div.title = 'Boat-cursor overlays — toggle each piece of info';
        const optionsHtml = TRAIL_WINDOW_OPTIONS.map(o => {
            const v = (o.ms === Infinity) ? 'Infinity' : String(o.ms);
            const sel = (o.ms === trailWindowMs) ? ' selected' : '';
            return `<option value="${v}"${sel}>${o.label}</option>`;
        }).join('');
        div.innerHTML = `<span class="trail-window-label">SHOW</span>` +
            items.map(it => {
                const cb = `<label><input type="checkbox" data-key="${it.key}" ${markerOverlays[it.key] ? 'checked' : ''}> ${it.label}`;
                if (it.key === 'trail') {
                    return `${cb}<select class="trail-window-select" data-trail-window
                                     title="How much past track to draw">${optionsHtml}</select></label>`;
                }
                return `${cb}</label>`;
            }).join('');
        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);

        div.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', () => {
                markerOverlays[cb.dataset.key] = cb.checked;
                try { localStorage.setItem('sf-marker-overlays', JSON.stringify(markerOverlays)); } catch {}
                if (currentRace) updateBoatPositions(playCursorSeconds);
            });
        });
        const sel = div.querySelector('.trail-window-select');
        if (sel) {
            sel.addEventListener('change', () => {
                const v = sel.value;
                trailWindowMs = (v === 'Infinity') ? Infinity : Number(v);
                try { localStorage.setItem('sf-trail-window-ms', v); } catch {}
                refreshAllTrails();
            });
        }
        return div;
    };
    ctl.addTo(map);
}

// Top-left wind widget on the map: a rotating arrow + TWD/TWS readout
// with the station dropdown directly below. Replaces the old leaderboard
// wind badge AND the toolbar wind picker — there's now one wind control
// for the whole dashboard, anchored to the map. The dropdown's content
// is rendered into #wind-source-picker by renderWindSourcePicker(); the
// rest of the picker code is unchanged.
function addMapWindPicker() {
    if (!map) return;
    const ctl = L.control({ position: 'topleft' });
    ctl.onAdd = function () {
        const div = L.DomUtil.create('div', 'leaflet-bar map-wind-picker');
        div.innerHTML = `
            <div class="map-wind-picker-row">
                <div class="map-wind-arrow" id="map-wind-arrow" title="True wind">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M12 2 L18 14 L12 11 L6 14 Z"
                              fill="#22d3ee" stroke="#fff" stroke-width="1"/>
                    </svg>
                </div>
                <div class="map-wind-readout">
                    <span class="map-wind-readout-twd" id="map-wind-twd">---°</span>
                    <span class="map-wind-readout-tws" id="map-wind-tws">-- kn</span>
                </div>
            </div>
            <div class="wind-source-picker" id="wind-source-picker" style="display:none"></div>
        `;
        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);
        return div;
    };
    ctl.addTo(map);
}

// Charts overlay open/close. Triggered by the toolbar Charts button,
// closed by the X / backdrop click / Escape. Adds .charts-open to body
// so the rest of the dashboard can react if needed.
function setupChartsOverlay() {
    const overlay = document.getElementById('charts-overlay');
    const trigger = document.getElementById('btn-charts');
    if (!overlay || !trigger) return;

    function open() {
        overlay.hidden = false;
        document.body.classList.add('charts-open');
        // Chart.js cached canvas dimensions when the canvas was hidden
        // (display:none → 0×0). Force a resize now that the overlay is
        // visible so curves fill the new viewport instead of staying
        // collapsed at the top.
        requestAnimationFrame(() => {
            if (speedChart) speedChart.resize();
            if (heelChart)  heelChart.resize();
            if (windChart)  windChart.resize();
        });
    }
    function close() {
        overlay.hidden = true;
        document.body.classList.remove('charts-open');
    }

    trigger.addEventListener('click', () => overlay.hidden ? open() : close());
    overlay.querySelectorAll('[data-close-charts]').forEach(el => {
        el.addEventListener('click', close);
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !overlay.hidden) close();
    });

    // Panel-fade slider — drags the alpha on the chart panel itself so
    // the map behind shows through. The backdrop stays fully transparent
    // (it's only there as a click-to-close target). At 0% the panel is
    // fully opaque (no map bleed); at 100% the panel is fully
    // transparent (map fully visible, charts ghost over it). Persisted
    // across page loads via localStorage.
    const slider = document.getElementById('charts-panel-fade');
    const valEl  = document.getElementById('charts-panel-fade-val');
    const panel  = overlay.querySelector('.charts-overlay-panel');
    function applyPanelFade(pct) {
        const alpha = Math.max(0, Math.min(1, 1 - pct / 100));
        if (panel) panel.style.background = `rgba(15, 23, 42, ${alpha.toFixed(2)})`;
        if (valEl) valEl.textContent = `${pct}%`;
        try { localStorage.setItem('sf-charts-panel-fade', String(pct)); } catch {}
    }
    if (slider) {
        const saved = parseInt(localStorage.getItem('sf-charts-panel-fade') || '30', 10);
        slider.value = String(saved);
        applyPanelFade(saved);
        slider.addEventListener('input', (e) => applyPanelFade(parseInt(e.target.value, 10)));
    }
}

// Trim each boat's polyline to the configured trail window around the
// current playback index. With trailWindowMs === Infinity the full track
// is restored.
function refreshAllTrails() {
    for (const layer of Object.values(boatLayers)) {
        applyTrailWindow(layer);
    }
}

function applyTrailWindow(layer) {
    if (!layer || !layer.track || !layer.coords || !layer.times) return;
    // The SHOW > Trail toggle hides the polyline entirely. Empty latlngs
    // keeps the layer registered (so toggleBoatVisibility still works)
    // but draws nothing.
    if (!markerOverlays.trail) {
        layer.track.setLatLngs([]);
        return;
    }
    const n = layer.coords.length;
    if (n === 0) return;
    const endIdx = Math.min(n - 1, layer.currentIdx ?? (n - 1));
    if (!Number.isFinite(trailWindowMs)) {
        layer.track.setLatLngs(layer.coords);
        return;
    }
    const cutoff = layer.times[endIdx] - trailWindowMs;
    let startIdx = endIdx;
    while (startIdx > 0 && layer.times[startIdx - 1] >= cutoff) startIdx--;
    layer.track.setLatLngs(layer.coords.slice(startIdx, endIdx + 1));
}

function renderLaylines() {
    if (laylineLayer) { map.removeLayer(laylineLayer); laylineLayer = null; }
    if (!laylinesVisible) return;
    // Prefer the live TWD set by syncLaylineWind() against playback time;
    // fall back to the race-average if no sample has been seen yet (e.g.
    // initial render before the first updateBoatPositions tick).
    const twd = lastLaylineTWD ?? raceAvgTWD;
    if (twd == null || !currentRace?.course?.length) return;
    const marksById = buildMarksById(currentRace);
    const startAnchor = startMidpoint(currentRace);
    if (!startAnchor) return;

    // Find the *next upwind beat* in the course from activeLeg forward.
    // We scan each remaining leg and check whether the bearing from the
    // previous mark (or start) into this mark is within ±90° of TWD —
    // i.e. is this leg a beat? The first beat we hit is what we draw
    // laylines for. This covers two-lap W-L courses (laylines on W2
    // even after L is rounded) and courses with offset+gate marks
    // (W2's laylines visible during the downwind segment, tactically
    // useful for planning the second beat). Race 2 of 2026-05-04 had no
    // laylines on its leg-3 windward because the prior code only tested
    // bearing-from-START — fragile when the course has the same mark id
    // appearing twice or when intermediate marks confuse the index walk.
    const courseSeq = currentRace.course;
    // Race-wide event count includes multi-lap roundings + finish-line
    // crossing; it's the right ceiling for "race over, stop drawing".
    const totalLegs = currentRace._totalLegs ?? courseSeq.length;
    if (totalLegs > 0 && activeLeg >= totalLegs) return;  // race finished
    // Walk the course modulo so multi-lap races (e.g. 2-lap W-L defined
    // as course=[W,L]) still find the next upwind beat on lap 2.
    const scanLimit = courseSeq.length * MAX_LAPS_TO_DETECT;

    let targetMark = null;
    let targetIdx = -1;
    for (let i = activeLeg; i < scanLimit; i++) {
        const mark = marksById[courseSeq[i % courseSeq.length]];
        if (!mark) continue;
        const prevSeqIdx = (i - 1 + courseSeq.length) % courseSeq.length;
        const prev = (i === 0)
            ? startAnchor
            : (marksById[courseSeq[prevSeqIdx]] || startAnchor);
        const legBearing = bearingDegrees(prev.lat, prev.lon, mark.lat, mark.lon);
        const offset = ((legBearing - twd + 540) % 360) - 180;
        if (Math.abs(offset) <= 90) {
            targetMark = mark;
            targetIdx = i;
            break;
        }
    }
    if (!targetMark) return;  // no upwind leg ahead — racing downwind to finish

    laylineLayer = L.featureGroup().addTo(map);
    const LAYLINE_M = 3000;
    const stbBearing = (twd + 180 - J80_UPWIND_TACK_ANGLE + 360) % 360;
    const portBearing = (twd + 180 + J80_UPWIND_TACK_ANGLE) % 360;
    const stbEnd = destinationPoint(targetMark.lat, targetMark.lon, stbBearing, LAYLINE_M);
    const portEnd = destinationPoint(targetMark.lat, targetMark.lon, portBearing, LAYLINE_M);

    const styleStb = { color: '#22d3ee', weight: 1.5, opacity: 0.55, dashArray: '6,6' };
    const stylePort = { color: '#ef4444', weight: 1.5, opacity: 0.55, dashArray: '6,6' };
    const markName = targetMark.name || targetMark.mark_type || `Mark ${targetIdx + 1}`;
    const twdLabel = `TWD ${twd.toFixed(0)}°`;
    const legNote = (targetIdx > activeLeg) ? ` (leg ${targetIdx + 1})` : '';
    L.polyline([[targetMark.lat, targetMark.lon], stbEnd], styleStb)
        .bindTooltip(`Starboard layline → ${markName}${legNote} · ${twdLabel}`, { sticky: true })
        .addTo(laylineLayer);
    L.polyline([[targetMark.lat, targetMark.lon], portEnd], stylePort)
        .bindTooltip(`Port layline → ${markName}${legNote} · ${twdLabel}`, { sticky: true })
        .addTo(laylineLayer);
}

// Re-render laylines if the wind at the current playback time has shifted
// enough since the last render (≥1°). Cheap guard: avoids rebuilding the
// two polylines on every frame when interpolation jitter is sub-degree.
// Called from updateBoatPositions; also re-fires on layline toggle so the
// initial display reflects the playback cursor's wind, not race-average.
function syncLaylineWind(targetTimeMs) {
    if (!laylinesVisible) return;
    const sample = windAt(targetTimeMs);
    const twd = sample?.twd;
    if (twd == null) return;
    if (lastLaylineTWD != null) {
        const diff = Math.abs(((twd - lastLaylineTWD + 540) % 360) - 180);
        if (diff < 1) return;
    }
    lastLaylineTWD = twd;
    renderLaylines();
}

// Two- to four-letter team initials, e.g. "Mystic Mutiny" → "MM",
// "Rooster Alumni Club" → "RAC". Single-word team names get an explicit
// override (Seadogs → SD) — otherwise we fall back to the first two
// letters of the name.
const TEAM_INITIALS_OVERRIDES = {
    'Seadogs':  'SD',
    'Vela Veloce':  'VV',
    'Mystic Mutiny':  'MM',
    'Anchor Management':  'AM',
    'Rooster Alumni Club':  'RAC',
    'Always Lost':  'AL',
};
function teamInitials(name) {
    if (!name) return '';
    if (TEAM_INITIALS_OVERRIDES[name]) return TEAM_INITIALS_OVERRIDES[name];
    const words = name.trim().split(/\s+/).filter(Boolean);
    if (words.length >= 2) {
        return words.map(w => w[0].toUpperCase()).join('').slice(0, 4);
    }
    return name.slice(0, 2).toUpperCase();
}

// Build the divIcon HTML for a boat marker. Includes the directional
// arrow plus a small label (initials · speed · heel · TWA) — each piece
// can be hidden via the top-right SHOW legend (markerOverlays). The
// initials chip stays so boats are always identifiable; only the
// numeric stats can be turned off.
function createBoatIcon(color, rotation = 0, initials = '', speedKn = null, heelDeg = null, twaSigned = null) {
    const svg = `
        <svg class="boat-marker-svg" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"
             style="transform: rotate(${rotation}deg);">
            <path d="M12 2 L20 20 L12 16 L4 20 Z"
                  fill="${color}" stroke="white" stroke-width="1.5"/>
        </svg>`;
    const ovr = markerOverlays || { speed: true, heel: true, twa: true };
    const speedTxt = (ovr.speed && speedKn != null && Number.isFinite(speedKn))
        ? `${speedKn.toFixed(1)}kn` : '';
    // Heel: signed (port = negative on this fleet's IMU). P/S matches
    // the TWA convention so the two metrics read consistently. The
    // "Heel " prefix labels the value so it isn't mistaken for TWA.
    const heelTxt = (ovr.heel && heelDeg != null && Number.isFinite(heelDeg))
        ? ` Heel ${heelDeg >= 0 ? 'S' : 'P'} ${Math.round(Math.abs(heelDeg))}°`
        : '';
    // TWA: signed true wind angle. Negative = port tack, positive = stbd.
    // Per-boat (depends on COG), so it tells you how close-hauled / deep
    // each boat is sailing.
    const twaTxt = (ovr.twa && twaSigned != null && Number.isFinite(twaSigned))
        ? ` TWA ${twaSigned <= 0 ? 'P' : 'S'} ${Math.round(Math.abs(twaSigned))}°`
        : '';
    const stats = (speedTxt || heelTxt || twaTxt)
        ? `<span class="bml-stats">${speedTxt}${heelTxt}${twaTxt}</span>` : '';
    const label = initials || stats
        ? `<span class="boat-marker-label"><span class="bml-init" style="color:${color}">${initials}</span>${stats}</span>`
        : '';
    return L.divIcon({
        html: `<div class="boat-marker-wrap">${svg}${label}</div>`,
        className: 'boat-marker',
        iconSize: null,        // let the wrap size to its content
        iconAnchor: [12, 12],  // anchor on the arrow's center
    });
}

function haversineMeters(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const toRad = (d) => d * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 +
              Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
}

// Bearing from A to B, degrees clockwise from north (0..360).
function bearingDegrees(lat1, lon1, lat2, lon2) {
    const f1 = lat1 * Math.PI / 180, f2 = lat2 * Math.PI / 180;
    const dLam = (lon2 - lon1) * Math.PI / 180;
    const y = Math.sin(dLam) * Math.cos(f2);
    const x = Math.cos(f1) * Math.sin(f2) - Math.sin(f1) * Math.cos(f2) * Math.cos(dLam);
    return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

// --- Course-aware progress metrics (Tier 2) ---
const MARK_ROUNDING_RADIUS_M = 35;  // meters, generous for J/80 mark roundings

function buildMarksById(race) {
    const out = {};
    for (const m of (race?.marks || [])) {
        if (m.mark_id) out[m.mark_id] = m;
    }
    return out;
}

function startMidpoint(race) {
    const sl = race?.start_line;
    if (sl && sl.pin_lat != null && sl.boat_lat != null) {
        return {
            lat: (sl.pin_lat + sl.boat_lat) / 2,
            lon: (sl.pin_lon + sl.boat_lon) / 2,
        };
    }
    return null;
}

// How many laps to scan for. Most J/80 club races are 1–2 laps; 4 is a
// safe ceiling that covers everything we've ever sailed. Over-scanning
// is harmless — if the boat never re-enters the next slot's radius the
// algorithm just stops.
const MAX_LAPS_TO_DETECT = 4;

// Walk each boat's track once and record the time it passed within
// MARK_ROUNDING_RADIUS_M of each mark in the course sequence — repeated
// up to MAX_LAPS_TO_DETECT times so that races defined as a single lap
// of [W, L] (the common J/80 pattern) automatically pick up the second
// lap's roundings without anyone having to re-enter the marks. After
// the last detected rounding, if a finish_line is defined and the boat
// crosses it, that crossing is appended as the race-end timestamp.
//
// Result stored on layer.roundingTimes — a flat array of epoch ms, one
// entry per detected event. Length up to courseSeq.length * MAX_LAPS + 1
// (the +1 = finish-line crossing).
function precomputeRoundingsForLayer(layer, courseSeq, marksById, finishLine) {
    if (!courseSeq?.length || !layer?.data?.length) {
        layer.roundingTimes = null;
        return;
    }
    const times = [];
    const maxEvents = courseSeq.length * MAX_LAPS_TO_DETECT;
    let lastSampleConsumed = 0;
    for (let i = 0; i < layer.data.length && times.length < maxEvents; i++) {
        const p = layer.data[i];
        if (!p.lat || !p.lon) continue;
        const seqIdx = times.length % courseSeq.length;
        const m = marksById[courseSeq[seqIdx]];
        if (!m) break;  // dangling mark id — give up rather than mis-credit
        const d = haversineMeters(p.lat, p.lon, m.lat, m.lon);
        if (d < MARK_ROUNDING_RADIUS_M) {
            times.push(new Date(p.t).getTime());
            lastSampleConsumed = i;
        }
    }

    // Finish-line crossing: walk forward from the last detected rounding
    // and look for the first GPS segment that intersects the line. If no
    // finish line is defined or the boat never crosses, leave the array
    // as-is (last rounding becomes the de-facto finish).
    if (finishLine && finishLine.pin_lat != null && finishLine.boat_lat != null) {
        const startIdx = times.length ? lastSampleConsumed + 1 : 1;
        let prevP = layer.data[startIdx - 1] || null;
        for (let i = startIdx; i < layer.data.length; i++) {
            const p = layer.data[i];
            if (!p.lat || !p.lon) { prevP = p; continue; }
            if (prevP && prevP.lat && prevP.lon) {
                if (segmentsIntersect(
                    prevP.lat, prevP.lon, p.lat, p.lon,
                    finishLine.pin_lat, finishLine.pin_lon,
                    finishLine.boat_lat, finishLine.boat_lon
                )) {
                    times.push(new Date(p.t).getTime());
                    break;
                }
            }
            prevP = p;
        }
    }

    layer.roundingTimes = times;
}

// 2-D segment intersection. Lat/lon at Boston-Harbor scale is close
// enough to a Cartesian plane (sub-metre error over a few km) for a
// boolean "did the boat's last GPS segment cross the finish line?"
// check. Returns false for collinear or non-overlapping segments.
function segmentsIntersect(ax, ay, bx, by, cx, cy, dx, dy) {
    const d1 = (dx - cx) * (ay - cy) - (dy - cy) * (ax - cx);
    const d2 = (dx - cx) * (by - cy) - (dy - cy) * (bx - cx);
    const d3 = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
    const d4 = (bx - ax) * (dy - ay) - (by - ay) * (dx - ax);
    return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
           ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

// --- Weather-station wind (Tier 2 wind / TWD / laylines) ---

async function loadRaceWindData(startTime, endTime) {
    weatherWindSamples = [];
    weatherWindSource = null;
    raceAvgTWD = null;
    raceBuoyData = {};
    selectedWindStationId = null;
    if (!startTime || !endTime) return;
    try {
        const startTs = new Date(startTime).getTime() / 1000;
        const endTs = new Date(endTime).getTime() / 1000;
        const resp = await fetch(`${API_BASE}/api/buoys/data?start_ts=${startTs}&end_ts=${endTs}`);
        if (!resp.ok) {
            console.warn('[Wind] buoys/data HTTP', resp.status);
            return;
        }
        const data = await resp.json();
        raceBuoyData = data.buoys || {};
        // Auto-pick the first station with usable samples. Try the NDBC
        // primaries (Castle Island, Logan, 16NM) first; if none of them
        // has data for this race window, fall back to any Synoptic
        // station (SYN_*) that does.
        const usableId = (sid) =>
            raceBuoyData[sid]?.data_points?.some(d =>
                d.wind_dir != null && d.wind_speed_kts != null
            );
        for (const sid of PRIMARY_WIND_STATIONS) {
            if (usableId(sid)) { selectedWindStationId = sid; break; }
        }
        if (!selectedWindStationId) {
            for (const sid of Object.keys(raceBuoyData)) {
                if (usableId(sid)) { selectedWindStationId = sid; break; }
            }
        }
        rebuildWindFromSelected();
        renderWindSourcePicker();
    } catch (e) {
        console.error('[Wind] load failed', e);
    }
}

// Rebuild weatherWindSamples/raceAvgTWD/weatherWindSource from the
// currently selected station. Cheap; safe to call whenever the user
// flips between Castle Island and Logan.
function rebuildWindFromSelected() {
    weatherWindSamples = [];
    weatherWindSource = null;
    raceAvgTWD = null;
    if (!selectedWindStationId) return;
    const buoy = raceBuoyData[selectedWindStationId];
    if (!buoy?.data_points?.length) return;
    const samples = [];
    for (const dp of buoy.data_points) {
        if (dp.wind_dir == null || dp.wind_speed_kts == null) continue;
        const tMs = (dp.timestamp ? new Date(dp.timestamp).getTime() : (dp.ts * 1000));
        if (!Number.isFinite(tMs)) continue;
        samples.push({ tMs, twd: dp.wind_dir, tws: dp.wind_speed_kts });
    }
    if (!samples.length) return;
    samples.sort((a, b) => a.tMs - b.tMs);
    weatherWindSamples = samples;
    weatherWindSource = buoy.name || selectedWindStationId;
    let sx = 0, sy = 0;
    for (const s of samples) {
        sx += Math.sin(s.twd * Math.PI / 180);
        sy += Math.cos(s.twd * Math.PI / 180);
    }
    raceAvgTWD = (Math.atan2(sx, sy) * 180 / Math.PI + 360) % 360;
    console.log(`[Wind] using ${weatherWindSource}, ${samples.length} samples, avg TWD ${raceAvgTWD.toFixed(0)}°`);
}

// Wind-source segmented picker (Castle Is / Logan / 44013) next to badge.
function shortStationLabel(stationId, fullName) {
    const overrides = {
        'CSIM3': 'Castle Is',
        'KBOS':  'Logan',
        '44013': '16NM',
        '44029': 'Mass Bay',
    };
    if (overrides[stationId]) return overrides[stationId];
    if (!fullName) return stationId;
    let n = fullName
        .replace(/\b(Sailing Center|Sailing|Airport|Buoy|Station)\b/gi, '')
        .replace(/\s+/g, ' ').trim();
    return n.length > 14 ? n.slice(0, 13) + '…' : n;
}

// Compute mean/std/min/max wind direction and speed across the race
// window for one station. TWD uses vector mean (handles 0/360 wrap).
function computeWindStats(buoy, raceStartMs, raceEndMs) {
    if (!buoy?.data_points?.length) return null;
    // ±30 min buffer so short race windows still show stats.
    const startMs = raceStartMs - 30 * 60 * 1000;
    const endMs = raceEndMs + 30 * 60 * 1000;
    const inWindow = [];
    for (const d of buoy.data_points) {
        if (d.wind_dir == null || d.wind_speed_kts == null) continue;
        const t = d.timestamp ? new Date(d.timestamp).getTime() : (d.unix_ts * 1000);
        if (!Number.isFinite(t) || t < startMs || t > endMs) continue;
        inWindow.push(d);
    }
    if (!inWindow.length) return null;
    let sx = 0, sy = 0;
    let minTWS = Infinity, maxTWS = -Infinity, sumTWS = 0;
    for (const d of inWindow) {
        sx += Math.sin(d.wind_dir * Math.PI / 180);
        sy += Math.cos(d.wind_dir * Math.PI / 180);
        const s = d.wind_speed_kts;
        if (s < minTWS) minTWS = s;
        if (s > maxTWS) maxTWS = s;
        sumTWS += s;
    }
    const meanTWD = (Math.atan2(sx, sy) * 180 / Math.PI + 360) % 360;
    const r = Math.sqrt(sx * sx + sy * sy) / inWindow.length;
    // Circular std (Mardia/Jupp formula). Clamp r to avoid log(0).
    const stdTWD = Math.sqrt(-2 * Math.log(Math.max(r, 1e-6))) * 180 / Math.PI;
    return {
        sampleCount: inWindow.length,
        meanTWD, stdTWD,
        minTWS, maxTWS,
        avgTWS: sumTWS / inWindow.length,
    };
}

function computeAllWindStats() {
    windStationStats = {};
    if (!currentRace) return;
    const raceStartMs = new Date(currentRace.start_time).getTime();
    const raceEndMs   = new Date(currentRace.end_time).getTime();
    for (const [sid, buoy] of Object.entries(raceBuoyData)) {
        const s = computeWindStats(buoy, raceStartMs, raceEndMs);
        if (s) windStationStats[sid] = s;
    }
}

function fmtStationStats(stats) {
    const tws = stats.minTWS.toFixed(0) === stats.maxTWS.toFixed(0)
        ? `${stats.minTWS.toFixed(0)} kn`
        : `${stats.minTWS.toFixed(0)}–${stats.maxTWS.toFixed(0)} kn`;
    return `${Math.round(stats.meanTWD).toString().padStart(3, '0')}°±${Math.round(stats.stdTWD)}°  ${tws}`;
}

// Compact "source" label for the dropdown column. NDBC/METAR/NWS render as-is;
// Synoptic stations get the underlying mesonet network when available so the
// user can tell a Tempest from a CWOP from a Logan-via-Synoptic mirror.
function fmtSourceLabel(buoy) {
    const src = (buoy.source || 'ndbc').toLowerCase();
    if (src === 'ndbc')  return 'NDBC';
    if (src === 'metar') return 'METAR';
    if (src === 'nws')   return 'NWS';
    if (src === 'synoptic') {
        const net = (buoy.network || '').toUpperCase();
        // Map Synoptic's network short names to a 1-token tag suitable
        // for the dropdown column. Order matters — earliest match wins.
        if (net.includes('TEMPEST') || net.includes('WXFLOW')) return 'Syn·Tempest';
        if (net.includes('CWOP') || net.includes('APRS'))      return 'Syn·CWOP';
        if (net.includes('ASOS') || net.includes('AWOS') ||
            net.includes('METAR') || net.includes('NWS/FAA'))  return 'Syn·METAR';
        if (net.includes('RAWS'))                              return 'Syn·RAWS';
        if (net.includes('WEATHERSTEM'))                       return 'Syn·WxStem';
        if (net.includes('DAVIS') || net.includes('WLINK'))    return 'Syn·Davis';
        if (net === 'NTC' || net.includes('TIDES'))            return 'Syn·NOAA·NTC';
        if (net.includes('BUOY') || net.includes('NDBC') ||
            net.includes('CMAN'))                              return 'Syn·NDBC';
        if (net.includes('SCHOOL'))                            return 'Syn·SchoolNet';
        return net ? `Syn·${net.length > 10 ? net.slice(0, 9) + '…' : net}` : 'Synoptic';
    }
    return src;
}

// Dedupe stations that point at the same physical sensor reachable via
// multiple aggregators (e.g. KBOS direct + SYN_KBOS via Synoptic, or any
// Synoptic mirror of an NDBC buoy). Group by lat/lon proximity (≤200 m)
// and keep the highest-priority source per group:
//   ndbc > metar > nws > synoptic
// Hidden duplicates stay in raceBuoyData (data preserved) but disappear
// from the picker and the map markers so the screen isn't double-marked.
function recomputeVisibleStations() {
    const SOURCE_PRIORITY = { ndbc: 0, metar: 1, nws: 2, synoptic: 3 };
    const stations = Object.entries(raceBuoyData)
        .filter(([sid, _b]) => windStationStats[sid])
        .map(([sid, b]) => ({
            id: sid,
            lat: typeof b.lat === 'number' ? b.lat : null,
            lon: typeof b.lon === 'number' ? b.lon : null,
            source: (b.source || 'ndbc').toLowerCase(),
        }))
        .filter(s => s.lat != null && s.lon != null);

    const groups = [];
    for (const s of stations) {
        let placed = false;
        for (const g of groups) {
            const ref = g[0];
            if (haversineMeters(s.lat, s.lon, ref.lat, ref.lon) <= 200) {
                g.push(s);
                placed = true;
                break;
            }
        }
        if (!placed) groups.push([s]);
    }

    const visible = new Set();
    for (const g of groups) {
        if (g.length === 1) {
            visible.add(g[0].id);
            continue;
        }
        g.sort((a, b) => {
            const pa = SOURCE_PRIORITY[a.source] ?? 99;
            const pb = SOURCE_PRIORITY[b.source] ?? 99;
            return pa - pb;
        });
        visible.add(g[0].id);
        // Note: g.slice(1) are hidden duplicates — their data stays in
        // raceBuoyData, just not surfaced in the UI.
    }
    visibleStationIds = visible;
}

// Wind-source dropdown. Triggered by a single button showing the
// currently selected station + its summary; click to expand the menu
// listing every station with usable wind data, each row showing the
// mean wind direction (with circular std-dev) and speed range during
// the race window.
function renderWindSourcePicker() {
    const host = document.getElementById('wind-source-picker');
    if (!host) return;

    computeAllWindStats();
    recomputeVisibleStations();

    const stations = Object.entries(raceBuoyData)
        .filter(([sid, _b]) => windStationStats[sid] && visibleStationIds.has(sid))
        .map(([sid, b]) => ({
            id: sid,
            name: b.name || sid,
            color: b.color || '#888',
            source: fmtSourceLabel(b),
            stats: windStationStats[sid],
        }));

    // If the auto-pick selected a station that's now hidden as a duplicate,
    // promote to the corresponding visible peer.
    if (selectedWindStationId && !visibleStationIds.has(selectedWindStationId) && stations.length) {
        selectedWindStationId = stations[0].id;
        rebuildWindFromSelected();
    }

    const order = (sid) => {
        const i = PRIMARY_WIND_STATIONS.indexOf(sid);
        return i >= 0 ? i : 100;
    };
    stations.sort((a, b) => {
        const o = order(a.id) - order(b.id);
        if (o !== 0) return o;
        // Then by sample count desc, then by name
        const c = b.stats.sampleCount - a.stats.sampleCount;
        return c !== 0 ? c : a.name.localeCompare(b.name);
    });

    if (stations.length === 0) {
        host.style.display = 'none';
        return;
    }
    host.style.display = 'flex';

    // Make sure selectedWindStationId is set to a station that exists
    if (!stations.find(s => s.id === selectedWindStationId)) {
        selectedWindStationId = stations[0].id;
        rebuildWindFromSelected();
    }
    const selected = stations.find(s => s.id === selectedWindStationId) || stations[0];

    host.innerHTML = `
      <button class="wind-dropdown-trigger" id="wind-dropdown-trigger" aria-haspopup="listbox" aria-expanded="false">
        <span class="wind-dropdown-prefix">WIND</span>
        <span class="wind-dropdown-current">
          <span class="wind-dropdown-current-name">${shortStationLabel(selected.id, selected.name)}</span>
          <span class="wind-dropdown-current-stats">${fmtStationStats(selected.stats)} · ${selected.source}</span>
        </span>
        <span class="wind-dropdown-arrow" aria-hidden="true">▾</span>
      </button>
      <div class="wind-dropdown-menu" id="wind-dropdown-menu" role="listbox" hidden>
        <div class="wind-dropdown-header" role="presentation"
             title="Number of wind samples each station reported during this race window">
            <span></span>
            <span>STATION</span>
            <span>SOURCE</span>
            <span>MEAN DIR · SPEED</span>
            <span class="wind-dropdown-header-n" title="Sample count during race window">N</span>
        </div>
        ${stations.map(s => `
          <button class="wind-dropdown-option ${s.id === selectedWindStationId ? 'active' : ''}"
                  data-station="${s.id}" role="option"
                  aria-selected="${s.id === selectedWindStationId}"
                  title="${shortStationLabel(s.id, s.name)} · ${s.source} · ${s.stats.sampleCount} samples during race">
            <span class="wind-option-dot" style="background:${s.color}"></span>
            <span class="wind-option-name">${shortStationLabel(s.id, s.name)}</span>
            <span class="wind-option-source">${s.source}</span>
            <span class="wind-option-stats">${fmtStationStats(s.stats)}</span>
            <span class="wind-option-count">${s.stats.sampleCount}</span>
          </button>
        `).join('')}
      </div>
    `;

    const trigger = host.querySelector('#wind-dropdown-trigger');
    const menu = host.querySelector('#wind-dropdown-menu');

    function close() {
        menu.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
    }
    function toggle(e) {
        if (e) { e.stopPropagation(); e.preventDefault(); }
        const willOpen = menu.hidden;
        menu.hidden = !willOpen;
        trigger.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    }

    trigger.addEventListener('click', toggle);

    // Click outside to close. Detach the previous render's listener so
    // we don't leak handlers across picker rebuilds.
    if (_windDropdownOutsideListener) {
        document.removeEventListener('click', _windDropdownOutsideListener);
    }
    _windDropdownOutsideListener = (e) => { if (!host.contains(e.target)) close(); };
    document.addEventListener('click', _windDropdownOutsideListener);

    for (const opt of menu.querySelectorAll('.wind-dropdown-option')) {
        opt.addEventListener('click', (e) => {
            e.stopPropagation();
            close();
            setWindStation(opt.dataset.station);
        });
    }
}

function setWindStation(stationId) {
    if (stationId === selectedWindStationId) return;
    if (!raceBuoyData[stationId]?.data_points?.length) return;
    selectedWindStationId = stationId;
    rebuildWindFromSelected();
    renderWindSourcePicker();
    // New station → new wind series. Force the layline TWD to resample
    // against the current playback time before rebuilding the polylines.
    lastLaylineTWD = null;
    if (currentRace) {
        const targetMs = new Date(currentRace.start_time).getTime() + (playCursorSeconds * 1000);
        syncLaylineWind(targetMs);
        updateWindBadge(targetMs);
    }
    renderLaylines();
    updateSpeedChart();           // rebuilds polar overlays under new wind
    renderLeaderboard();          // TWA/%pol depend on wind
    updateBoatDrawer();
}

// Linear interp of TWD/TWS at a given time. TWD interpolated as a vector
// (sin/cos average) so wraparound across 0/360 is handled correctly.
function windAt(timeMs) {
    if (!weatherWindSamples.length) return null;
    if (timeMs <= weatherWindSamples[0].tMs) return weatherWindSamples[0];
    const last = weatherWindSamples[weatherWindSamples.length - 1];
    if (timeMs >= last.tMs) return last;
    // Binary search
    let lo = 0, hi = weatherWindSamples.length - 1;
    while (lo + 1 < hi) {
        const mid = (lo + hi) >> 1;
        if (weatherWindSamples[mid].tMs <= timeMs) lo = mid; else hi = mid;
    }
    const a = weatherWindSamples[lo], b = weatherWindSamples[hi];
    const span = b.tMs - a.tMs;
    if (span <= 0) return a;
    const f = (timeMs - a.tMs) / span;
    const ar = a.twd * Math.PI / 180, br = b.twd * Math.PI / 180;
    const sx = Math.sin(ar) * (1 - f) + Math.sin(br) * f;
    const sy = Math.cos(ar) * (1 - f) + Math.cos(br) * f;
    const twd = (Math.atan2(sx, sy) * 180 / Math.PI + 360) % 360;
    const tws = a.tws * (1 - f) + b.tws * f;
    return { tMs: timeMs, twd, tws };
}

function precomputeAllRoundings() {
    if (!currentRace) return;
    const marksById = buildMarksById(currentRace);
    const courseSeq = currentRace.course || [];
    const finishLine = currentRace.finish_line || null;
    for (const layer of Object.values(boatLayers)) {
        precomputeRoundingsForLayer(layer, courseSeq, marksById, finishLine);
    }
    // Race-wide totalLegs = max events any boat reached. Used by the
    // leaderboard to know when a boat has "finished" and by the layline
    // scanner to stop drawing once the fleet is done. With multi-lap
    // detection in precomputeRoundingsForLayer, this lifts the implicit
    // `courseSeq.length` ceiling so race 2 (course=[W,L], 2 laps, with
    // a finish line) shows 4 legs in the summary instead of 2.
    let maxEvents = 0;
    for (const layer of Object.values(boatLayers)) {
        const n = layer?.roundingTimes?.length || 0;
        if (n > maxEvents) maxEvents = n;
    }
    currentRace._totalLegs = maxEvents;
}

function legsCompletedAt(layer, targetTimeMs) {
    if (!layer?.roundingTimes) return 0;
    let count = 0;
    for (const t of layer.roundingTimes) {
        if (t !== undefined && t <= targetTimeMs) count++;
        else break;
    }
    return count;
}

// Along-course meters from start to current playback time. Sums leg
// lengths for completed legs and adds projected progress along the
// active leg (legLength - distToTarget, clamped to [0, legLength]).
// Indexes into courseSeq modulo its length so multi-lap progress (race
// 2: course=[W,L] sailed 2× → legsCompleted up to 4) keeps growing
// instead of capping at the end of lap 1.
function progressMetersAt(point, courseSeq, marksById, legsCompleted, startAnchor) {
    if (!courseSeq?.length || !point) return 0;
    let prev = startAnchor;
    if (!prev) return 0;
    let cum = 0;
    for (let i = 0; i < legsCompleted; i++) {
        const m = marksById[courseSeq[i % courseSeq.length]];
        if (!m) break;
        cum += haversineMeters(prev.lat, prev.lon, m.lat, m.lon);
        prev = m;
    }
    const totalLegs = currentRace?._totalLegs ?? courseSeq.length;
    if (legsCompleted < totalLegs && prev) {
        const target = marksById[courseSeq[legsCompleted % courseSeq.length]];
        if (target) {
            const legLen = haversineMeters(prev.lat, prev.lon, target.lat, target.lon);
            const distToT = haversineMeters(point.lat, point.lon, target.lat, target.lon);
            cum += Math.max(0, Math.min(legLen, legLen - distToT));
        }
    }
    return cum;
}

function addBoatTrack(deviceId, gpsData, boat, imuData = null) {
    const color = colorFor(deviceId);

    // Create track polyline (initially empty — populated by applyTrailWindow
    // after the first updateBoatPositions call sets currentIdx).
    const coords = gpsData.map(p => [p.lat, p.lon]);
    const track = L.polyline([], {
        color: color,
        weight: 3,
        opacity: 0.8,
    }).addTo(map);

    // Create boat marker (triangle pointing in direction of travel + label).
    const initials = teamInitials(boat?.team_name || boat?.boat_name || '');
    const initialCourse = gpsData[0]?.course || 0;
    const marker = L.marker([0, 0], {
        icon: createBoatIcon(color, initialCourse, initials),
        rotationOrigin: 'center center',
    }).addTo(map);
    marker.on('click', () => openBoatDrawer(deviceId));

    // Pre-compute cumulative distance (meters) per GPS sample so the
    // leaderboard can sort by progress rather than instantaneous speed.
    const cumDist = new Float32Array(gpsData.length);
    for (let i = 1; i < gpsData.length; i++) {
        const a = gpsData[i - 1];
        const b = gpsData[i];
        const seg = (a.lat && a.lon && b.lat && b.lon)
            ? haversineMeters(a.lat, a.lon, b.lat, b.lon)
            : 0;
        cumDist[i] = cumDist[i - 1] + seg;
    }

    // Pre-parse timestamps once so the trail window can walk back from the
    // current playback index without re-parsing ISO strings every frame.
    const times = new Float64Array(gpsData.length);
    for (let i = 0; i < gpsData.length; i++) {
        times[i] = new Date(gpsData[i].t).getTime();
    }

    boatLayers[deviceId] = {
        track,
        marker,
        data: gpsData,
        coords,
        times,
        cumDist,
        boat,
        color,
        initials,
        imu: imuData || [],   // for per-frame heel readout on the marker label
        visible: true,
    };
}

function updateBoatPositions(timeSeconds) {
    const startTime = currentRace ? new Date(currentRace.start_time).getTime() : 0;
    const targetTime = startTime + timeSeconds * 1000;

    for (const [deviceId, layer] of Object.entries(boatLayers)) {
        if (!layer.visible || !layer.data.length) continue;

        // Find closest data point + its index
        let closestIdx = 0;
        let minDiff = Infinity;
        for (let i = 0; i < layer.data.length; i++) {
            const pointTime = new Date(layer.data[i].t).getTime();
            const diff = Math.abs(pointTime - targetTime);
            if (diff < minDiff) {
                minDiff = diff;
                closestIdx = i;
            }
        }
        const closest = layer.data[closestIdx];

        // Update marker position and rotation
        if (closest && closest.lat && closest.lon) {
            layer.marker.setLatLng([closest.lat, closest.lon]);

            // Update boat icon (rotation + label with initials/speed/heel/TWA).
            // Heel is sourced from the IMU sample nearest playback time
            // (GPX-only boats have no IMU → omitted). TWA is computed from
            // the NOAA TWD at this moment minus the boat's COG, so it
            // works without an onboard wind sensor.
            const course = closest.course || 0;
            const speedKn = closest.speed_kn ?? null;
            const imuSample = nearestSampleAt(layer.imu, targetTime);
            const heelDeg = imuSample?.heel ?? null;
            const wSample = windAt(targetTime);
            const twaSigned = wSample ? (((wSample.twd - course + 540) % 360) - 180) : null;
            layer.marker.setIcon(createBoatIcon(layer.color, course, layer.initials, speedKn, heelDeg, twaSigned));

            // Cache current playback-time point + index so the leaderboard
            // reads the same value the map shows and can look up cumulative
            // distance traveled.
            layer.current = closest;
            layer.currentIdx = closestIdx;

            // Trim the trail polyline to the configured window around the
            // current index. Cheap — walks back at most ~window/sample_rate
            // points (60 at 1 Hz for the 1m default).
            applyTrailWindow(layer);
        }
    }

    // Refresh leaderboard + chart play cursors + drawer at playback time
    renderLeaderboard();
    updatePlayCursor(timeSeconds);
    updateWindBadge(targetTime);
    // Pivot the laylines to the wind at the current playback time. Cheap
    // — re-renders only when TWD has shifted ≥1° from the last drawn pair.
    syncLaylineWind(targetTime);
    // Re-frame the map around the leader + their next mark. Throttled
    // internally to one fly per ~700 ms so slider scrubbing or fast
    // playback doesn't ricochet the viewport.
    applyLeaderFollow(false, targetTime);
    updateBoatDrawer();
}

// Refresh the map's top-left wind picker (rotating arrow + TWD/TWS
// readout) and the per-station map roses. The leaderboard wind badge
// has been removed — the picker on the map is now the single source.
function updateWindBadge(targetTimeMs) {
    const sample = windAt(targetTimeMs);
    const arrow  = document.getElementById('map-wind-arrow');
    const twdEl  = document.getElementById('map-wind-twd');
    const twsEl  = document.getElementById('map-wind-tws');
    if (arrow && sample) {
        // Wind blows TO (twd + 180); arrow SVG points up (north) at 0°.
        const blowTo = (sample.twd + 180) % 360;
        arrow.style.transform = `rotate(${blowTo}deg)`;
        arrow.title = `True wind from ${weatherWindSource || 'NOAA'} (interpolated)`;
    }
    if (twdEl) twdEl.textContent = sample ? `${sample.twd.toFixed(0).padStart(3, '0')}°` : '---°';
    if (twsEl) twsEl.textContent = sample ? `${sample.tws.toFixed(1)} kn` : '-- kn';
    updateAllWindMarkers(targetTimeMs);
}

// Find the wind sample at a given time for ONE specific station (closest
// data point). Used to drive the multi-station map rose markers.
function stationWindAt(stationId, timeMs) {
    const buoy = raceBuoyData[stationId];
    if (!buoy?.data_points?.length) return null;
    let best = null, bestDiff = Infinity;
    for (const dp of buoy.data_points) {
        if (dp.wind_dir == null || dp.wind_speed_kts == null) continue;
        const t = dp.timestamp ? new Date(dp.timestamp).getTime() : (dp.unix_ts * 1000);
        if (!Number.isFinite(t)) continue;
        const diff = Math.abs(t - timeMs);
        if (diff < bestDiff) {
            bestDiff = diff;
            best = { tMs: t, twd: dp.wind_dir, tws: dp.wind_speed_kts };
        }
    }
    // Reject samples too far from the requested time (>2h, prevents
    // showing wildly stale data from buffer regions).
    return bestDiff < 7200_000 ? best : null;
}

function createWindRoseIcon(twd, tws, opts = {}) {
    const isSel = !!opts.selected;
    const sz = isSel ? 56 : 36;
    const arrow = isSel ? 44 : 30;
    const fontTws = isSel ? '0.85rem' : '0.65rem';
    const fontTwd = isSel ? '0.65rem' : '0.55rem';
    const color = isSel ? '#22d3ee' : (opts.color || '#9ca3af');
    const stroke = isSel ? 3 : 2;
    const opacity = isSel ? 1 : 0.78;
    const blowTo = (twd + 180) % 360;
    const tspeed = (tws ?? 0).toFixed(0);
    const tdir = (twd ?? 0).toFixed(0).padStart(3, '0');
    const html = `
        <div class="wind-rose ${isSel ? 'is-selected' : 'is-secondary'}" style="opacity:${opacity}">
            <div class="wind-rose-arrow" style="transform: rotate(${blowTo}deg); width:${arrow}px; height:${arrow}px">
                <svg width="${arrow}" height="${arrow}" viewBox="0 0 48 48">
                    <line x1="24" y1="40" x2="24" y2="10" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round"/>
                    <polygon points="24,4 17,16 31,16" fill="${color}"/>
                </svg>
            </div>
            <div class="wind-rose-label" style="color:${color}">
                <div class="wind-rose-tws" style="font-size:${fontTws}">${tspeed} kn</div>
                <div class="wind-rose-twd" style="font-size:${fontTwd}">${tdir}°</div>
            </div>
        </div>
    `;
    return L.divIcon({
        html, className: 'wind-rose-marker',
        iconSize: [sz + 36, sz],
        iconAnchor: [arrow / 2, arrow / 2],
    });
}

// Render or update markers for EVERY station with wind data. Selected
// station gets the cyan/large treatment; others render small + muted.
// Each marker rotates and updates with the playback cursor.
function updateAllWindMarkers(targetTimeMs) {
    if (!map) return;
    const present = new Set();
    for (const [sid, buoy] of Object.entries(raceBuoyData)) {
        if (!windStationStats[sid]) continue;
        // Skip stations hidden as duplicates of higher-priority sources.
        if (!visibleStationIds.has(sid)) continue;
        if (buoy.lat == null || buoy.lon == null) continue;
        present.add(sid);
        const sample = stationWindAt(sid, targetTimeMs);
        // Fall back to mean stats if no sample close enough
        const twd = sample?.twd ?? windStationStats[sid].meanTWD;
        const tws = sample?.tws ?? windStationStats[sid].avgTWS;
        const isSelected = sid === selectedWindStationId;
        const icon = createWindRoseIcon(twd, tws, {
            selected: isSelected,
            color: buoy.color || '#9ca3af',
        });
        if (windMarkers[sid]) {
            windMarkers[sid].setIcon(icon);
        } else {
            const m = L.marker([buoy.lat, buoy.lon], {
                icon,
                zIndexOffset: isSelected ? -50 : -150,
                interactive: true,
            });
            m.bindTooltip(buoy.name || sid, { sticky: true });
            m.on('click', () => setWindStation(sid));
            m.addTo(map);
            windMarkers[sid] = m;
        }
        windMarkers[sid].setTooltipContent(
            `${buoy.name || sid}: ${twd.toFixed(0)}° / ${tws.toFixed(1)} kn`
        );
    }
    // Remove any markers for stations no longer present
    for (const sid of Object.keys(windMarkers)) {
        if (!present.has(sid)) {
            map.removeLayer(windMarkers[sid]);
            delete windMarkers[sid];
        }
    }
}

function fitMapToBounds() {
    // Default landing view: zoom to the start line + first mark so the
    // pre-start area and the first beat are framed at race-load time.
    // This is what the user actually wants to see when they open a race
    // — the full-track bounds were too zoomed-out to read at a glance,
    // especially with multi-lap races covering the same water twice.
    // Falls back to the all-GPS bounds if course/start aren't defined.
    const corners = [];
    const sl = currentRace?.start_line;
    if (sl && sl.pin_lat != null && sl.boat_lat != null) {
        corners.push([sl.pin_lat, sl.pin_lon]);
        corners.push([sl.boat_lat, sl.boat_lon]);
    }
    const courseSeq = currentRace?.course || [];
    if (courseSeq.length) {
        const marksById = buildMarksById(currentRace);
        const firstMark = marksById[courseSeq[0]];
        if (firstMark && firstMark.lat != null && firstMark.lon != null) {
            corners.push([firstMark.lat, firstMark.lon]);
        }
    }

    if (corners.length >= 2) {
        const bounds = L.latLngBounds(corners);
        console.log('[Race] Fitting to start-line + first-mark bounds:', bounds.toBBoxString());
        // Tight zoom on the racing area: the start line and first
        // windward should fill the viewport so the user can read the
        // pre-start line set, the bias, and the layline geometry at a
        // glance. Smaller padding (60 px) + maxZoom 17 gets us in close.
        map.fitBounds(bounds, { padding: [60, 60], maxZoom: 17 });
        return;
    }

    // Fallback: full-race bounds (older races without a defined course).
    const allCoords = [];
    for (const layer of Object.values(boatLayers)) {
        if (layer.data) {
            for (const p of layer.data) {
                if (p.lat && p.lon) allCoords.push([p.lat, p.lon]);
            }
        }
    }
    console.log(`[Race] fitMapToBounds fallback: ${allCoords.length} coordinates`);
    if (allCoords.length > 0) {
        map.fitBounds(L.latLngBounds(allCoords), { padding: [50, 50] });
    } else {
        console.warn('[Race] No coordinates to fit map bounds');
    }
}

// --- Boat Legend ---

// Top-left fleet-tracker legend has been replaced by per-marker labels
// (initials + speed + heel) drawn beside the boat arrow. The leaderboard
// on the right is the canonical color/team key. No-op kept so call sites
// don't need editing.
function renderBoatLegend() {}

function updateLegendSpeed(deviceId, speed) {
    const el = document.getElementById(`legend-speed-${deviceId}`);
    if (el) {
        el.textContent = `${speed.toFixed(1)} kn`;
    }
}

function toggleBoatVisibility(deviceId) {
    const layer = boatLayers[deviceId];
    if (!layer) return;

    layer.visible = !layer.visible;

    if (layer.visible) {
        layer.track.addTo(map);
        layer.marker.addTo(map);
    } else {
        map.removeLayer(layer.track);
        map.removeLayer(layer.marker);
    }
}

// --- Leaderboard ---

function renderLeaderboard() {
    const container = document.getElementById('leaderboard');

    if (!currentRace || !raceData) {
        container.innerHTML = '<div class="leaderboard-empty">Select a race to view standings</div>';
        return;
    }

    // Get current positions based on distance or speed
    const positions = calculatePositions();

    // Sync laylines to the *trailing* boat's next mark — laylines stay
    // visible until the LAST boat rounds, so boats still approaching the
    // windward keep their tactical aid even after the leader is past.
    // Shifts to the next target (or hides, if that target is downwind)
    // only when every boat has rounded. Re-renders only on change.
    const newActiveLeg = positions.length
        ? Math.min(...positions.map(p => p.legsCompleted))
        : 0;
    if (newActiveLeg !== activeLeg) {
        activeLeg = newActiveLeg;
        renderLaylines();
    }

    const drawerActive = drawerDeviceId;
    container.innerHTML = positions.map((item, index) => {
        const pos = index + 1;
        const color = colorFor(item.deviceId);
        const posClass = pos <= 3 ? `p${pos}` : '';
        const activeClass = item.deviceId === drawerActive ? ' active' : '';
        const finClass = item.finished ? ' leaderboard-finished' : '';

        // Bottom-line stats. Finished boats show `FIN ✓` plus the time gap
        // to the winner ("+0:25") instead of live VMG/TWA/%pol/distance —
        // those numbers are meaningless once a boat has crossed.
        const subParts = [];
        if (item.finished) {
            subParts.push('FIN ✓');
            if (item.gapSec == null) {
                subParts.push(positions.length > 1 ? 'WIN' : '—');
            } else {
                subParts.push(`+${fmtMMSS(item.gapSec)}`);
            }
        } else {
            if (item.vmg !== null && item.vmg !== undefined) {
                const sign = item.vmg >= 0 ? '+' : '';
                subParts.push(`VMG ${sign}${item.vmg.toFixed(1)}`);
            }
            if (item.twa !== null && item.twa !== undefined) {
                const tack = item.twa < 0 ? 'P' : 'S';
                subParts.push(`${tack} ${Math.abs(item.twa).toFixed(0)}°`);
            }
            if (item.polarPct !== null && item.polarPct !== undefined) {
                subParts.push(`${item.polarPct.toFixed(0)}%pol`);
            }
            if (item.gap === null || item.gap === undefined) {
                subParts.push(positions.length > 1 ? 'LEAD' : '—');
            } else {
                const gap = item.gap;
                subParts.push(gap >= 1000
                    ? `−${(gap / 1000).toFixed(2)} km`
                    : `−${gap.toFixed(0)} m`);
            }
        }

        // Speed cell: live SOG normally; total elapsed M:SS when finished.
        const speedCell = item.finished && item.finishElapsedSec != null
            ? `<div class="leaderboard-speed leaderboard-finish-time" title="Total race time">${fmtMMSS(item.finishElapsedSec)}</div>`
            : `<div class="leaderboard-speed">${item.speed.toFixed(1)} kn</div>`;

        return `
            <div class="leaderboard-item${activeClass}${finClass}" data-device-id="${item.deviceId}">
                <div class="leaderboard-position ${posClass}">${pos}</div>
                <div class="leaderboard-boat-color" style="background: ${color}"></div>
                <div class="leaderboard-boat-info">
                    <div class="leaderboard-boat-name">${item.displayName}</div>
                    <div class="leaderboard-boat-subtitle">${item.subtitle}</div>
                </div>
                <div class="leaderboard-stats">
                    ${speedCell}
                    <div class="leaderboard-delta">${subParts.join(' · ')}</div>
                </div>
            </div>
        `;
    }).join('');

    // Click handler: open the per-boat drawer. Re-bind on every render
    // since innerHTML wiped the old listeners.
    for (const el of container.querySelectorAll('.leaderboard-item')) {
        el.addEventListener('click', () => {
            const id = el.getAttribute('data-device-id');
            if (id) openBoatDrawer(id);
        });
    }
}

// Binary-search the GPS index whose timestamp is closest to (and not
// after) targetMs, using the pre-parsed layer.times Float64Array. Used
// to "freeze" the leaderboard at a boat's finish moment — once a boat
// crosses the line, every subsequent leaderboard render reads the GPS
// sample at the finish time, not the live-playback time, so speed /
// COG / TWA / VMG / %pol all snap to the finish-state values.
function gpsIdxAt(layer, targetMs) {
    if (!layer?.times || !layer.times.length) return null;
    const ts = layer.times;
    if (targetMs <= ts[0]) return 0;
    if (targetMs >= ts[ts.length - 1]) return ts.length - 1;
    let lo = 0, hi = ts.length - 1;
    while (lo + 1 < hi) {
        const mid = (lo + hi) >> 1;
        if (ts[mid] <= targetMs) lo = mid; else hi = mid;
    }
    return lo;
}

function calculatePositions() {
    if (!raceData?.boats) return [];

    const positions = [];

    const courseSeq = currentRace?.course || [];
    const courseDefined = courseSeq.length > 0;
    const marksById = buildMarksById(currentRace);
    const startAnchor = startMidpoint(currentRace);
    const startTimeMs = currentRace ? new Date(currentRace.start_time).getTime() : 0;
    const targetTimeMs = startTimeMs + (playCursorSeconds * 1000);

    for (const [deviceId, boatData] of Object.entries(raceData.boats)) {
        if (boatData.error || !boatData.sensors?.gps?.length) continue;

        const layer = boatLayers[deviceId];
        const boat = boatData.boat;

        const gps = boatData.sensors.gps;

        // Race-finish state. legsCompletedAt() filters by playback time,
        // so a boat is "finished" only once the cursor passes its actual
        // finish-line crossing.
        const totalLegs = currentRace?._totalLegs ?? courseSeq.length;
        const liveLegs = layer ? legsCompletedAt(layer, targetTimeMs) : 0;
        const finished = courseDefined && totalLegs > 0 && liveLegs >= totalLegs;
        const finishTimeMs = (finished && layer?.roundingTimes && layer.roundingTimes[totalLegs - 1] != null)
            ? layer.roundingTimes[totalLegs - 1]
            : null;

        // Freeze: when finished, evaluate every per-boat metric at the
        // finish-line moment instead of the playback cursor. The boat's
        // ranking, speed, TWA, %pol, VMG all stop changing the instant
        // it crosses. Map marker keeps moving (the boat physically
        // continues sailing); the leaderboard does not.
        const evalTimeMs = (finished && finishTimeMs != null) ? finishTimeMs : targetTimeMs;
        let idx;
        let point;
        if (finished && finishTimeMs != null && layer?.times) {
            idx = gpsIdxAt(layer, finishTimeMs) ?? (gps.length - 1);
            point = layer.data?.[idx] || gps[idx] || gps[gps.length - 1];
        } else {
            idx = layer?.currentIdx ?? (gps.length - 1);
            point = layer?.current || gps[gps.length - 1];
        }
        const windNow = windAt(evalTimeMs);

        // Distance-only fallback for races without a defined course.
        const cumDistM = (layer?.cumDist && layer.cumDist[idx] !== undefined)
            ? layer.cumDist[idx] : 0;

        // Course-aware metrics (only when a course sequence is defined)
        let legsCompleted = liveLegs;
        let progressM = cumDistM;
        let vmg = null;
        let distToNext = null;
        let nextMarkName = null;
        if (courseDefined && layer && point && point.lat && point.lon) {
            progressM = progressMetersAt(point, courseSeq, marksById, legsCompleted,
                                         startAnchor || { lat: gps[0].lat, lon: gps[0].lon });
            if (legsCompleted < totalLegs) {
                const target = marksById[courseSeq[legsCompleted % courseSeq.length]];
                if (target) {
                    nextMarkName = target.name || target.mark_type || `Mark ${legsCompleted + 1}`;
                    distToNext = haversineMeters(point.lat, point.lon, target.lat, target.lon);
                    const brg = bearingDegrees(point.lat, point.lon, target.lat, target.lon);
                    const sog = point.speed_kn || 0;
                    const cog = point.course || 0;
                    // Signed angle (-180..180) from heading to mark bearing.
                    const angleDiff = ((brg - cog + 540) % 360) - 180;
                    vmg = sog * Math.cos(angleDiff * Math.PI / 180);
                }
            }
        }

        // Display team name if available, else boat name, else device ID
        const displayName = boat?.team_name || boat?.boat_name || deviceId;
        const subtitle = boat?.team_name && boat?.boat_name ? boat.boat_name : deviceId;

        // True Wind Angle (signed, port = negative). Requires NOAA wind.
        let twa = null;
        let polarPct = null;
        if (windNow && point) {
            const cog = point.course || 0;
            twa = ((windNow.twd - cog + 540) % 360) - 180;
            polarPct = polarPercent(point.speed_kn || 0, twa, windNow.tws);
        }

        const finishElapsedSec = (finished && finishTimeMs != null)
            ? (finishTimeMs - startTimeMs) / 1000
            : null;

        positions.push({
            deviceId,
            displayName,
            subtitle,
            speed: point?.speed_kn || 0,
            heading: point?.course || 0,
            cumDistM,
            progressM,
            legsCompleted,
            distToNext,
            nextMarkName,
            vmg,
            twa,
            polarPct,
            finished,
            finishTimeMs,
            finishElapsedSec,
            gapSec: null,    // filled in below for finished boats
            gap: null,       // filled in below
        });
    }

    // Rank: course-aware uses (legsCompleted DESC, then finishTime ASC for
    // boats that finished, then distToNext ASC for boats still racing).
    // Fallback (no course) is cumulative distance traveled.
    if (courseDefined) {
        positions.sort((a, b) => {
            if (b.legsCompleted !== a.legsCompleted) return b.legsCompleted - a.legsCompleted;
            if (a.finished && b.finished) {
                const ta = a.finishTimeMs ?? Infinity;
                const tb = b.finishTimeMs ?? Infinity;
                if (ta !== tb) return ta - tb;
            }
            const da = a.distToNext ?? Infinity;
            const db = b.distToNext ?? Infinity;
            return da - db;
        });
    } else {
        positions.sort((a, b) => b.cumDistM - a.cumDistM);
    }

    // Gap: along-course meters behind leader (course defined) or behind in
    // raw distance traveled (fallback). Leader keeps gap=null and the
    // renderer turns that into "LEAD". For finished boats we also fill
    // gapSec relative to the winner's finish moment — that's the
    // canonical sailing scoreboard delta ("+0:25 behind") that the
    // distance gap can't express once both boats have crossed.
    if (positions.length > 0) {
        const leader = positions[0];
        const baseField = courseDefined ? 'progressM' : 'cumDistM';
        const leaderFinishMs = leader.finished ? leader.finishTimeMs : null;
        for (let i = 1; i < positions.length; i++) {
            positions[i].gap = leader[baseField] - positions[i][baseField];
            if (positions[i].finished && leaderFinishMs != null && positions[i].finishTimeMs != null) {
                positions[i].gapSec = (positions[i].finishTimeMs - leaderFinishMs) / 1000;
            }
        }
    }

    return positions;
}

// --- Speed Chart ---

// Vertical play-cursor line drawn over each comparison chart.
// The cursor X is `playCursorSeconds` (seconds from race start), matching
// the X axis of all three charts so a single global value drives all of them.
const playCursorPlugin = {
    id: 'playCursor',
    afterDatasetsDraw: (chart) => {
        const xScale = chart.scales.x;
        const yScale = chart.scales.y;
        if (!xScale || !yScale) return;
        if (playCursorSeconds < xScale.min || playCursorSeconds > xScale.max) return;
        const x = xScale.getPixelForValue(playCursorSeconds);
        const ctx = chart.ctx;
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(x, yScale.top);
        ctx.lineTo(x, yScale.bottom);
        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(255,255,255,0.7)';
        ctx.setLineDash([3, 3]);
        ctx.stroke();
        ctx.restore();
    },
};
if (typeof Chart !== 'undefined') Chart.register(playCursorPlugin);

const COMPARISON_CHART_OPTIONS = (yLabel, ySuggestedMin, ySuggestedMax, yTickFormat) => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { intersect: false, mode: 'index' },
    plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
    },
    scales: {
        x: {
            type: 'linear',
            title: { display: false },
            grid: { color: 'rgba(255,255,255,0.05)' },
            ticks: {
                color: '#666',
                callback: (v) => formatChartTime(v),
                maxTicksLimit: 6,
            },
        },
        y: {
            title: { display: true, text: yLabel, color: '#888', font: { size: 10 } },
            grid: { color: 'rgba(255,255,255,0.08)' },
            ticks: yTickFormat
                ? { color: '#888', callback: yTickFormat }
                : { color: '#888' },
            suggestedMin: ySuggestedMin,
            suggestedMax: ySuggestedMax,
        },
    },
});

// Heel sign convention on the E1 fleet: positive = starboard down,
// negative = port down. Render as "S 12°" / "P 8°" — same P/S acronyms
// as TWA on the map labels, so the user has one mental model for tack
// notation across the dashboard.
const heelTickFormatter = (v) => {
    if (v === 0) return '0°';
    return v > 0 ? `S ${v}°` : `P ${-v}°`;
};

function formatChartTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function initSpeedChart() {
    const speedCtx = document.getElementById('speed-chart').getContext('2d');
    speedChart = new Chart(speedCtx, {
        type: 'line',
        data: { datasets: [] },
        options: COMPARISON_CHART_OPTIONS('Speed (kn)', 0, 12),
    });

    const heelCtx = document.getElementById('heel-chart').getContext('2d');
    heelChart = new Chart(heelCtx, {
        type: 'line',
        data: { datasets: [] },
        options: COMPARISON_CHART_OPTIONS('Heel', -30, 30, heelTickFormatter),
    });

    // Wind chart uses NOAA TWD instead of per-boat AWS. Single curve.
    const windCtx = document.getElementById('wind-chart').getContext('2d');
    windChart = new Chart(windCtx, {
        type: 'line',
        data: { datasets: [] },
        options: COMPARISON_CHART_OPTIONS('TWD (°)', 0, 360),
    });
}

// Build a downsampled (time-seconds, value) series for one boat's sensor data.
function buildSeries(samples, valueField, raceStartMs, maxPoints = 240) {
    if (!samples?.length) return [];
    const step = Math.max(1, Math.floor(samples.length / maxPoints));
    const out = [];
    for (let i = 0; i < samples.length; i += step) {
        const s = samples[i];
        if (s == null) continue;
        const t = new Date(s.t).getTime();
        const v = s[valueField];
        if (v == null || Number.isNaN(v)) continue;
        out.push({ x: (t - raceStartMs) / 1000, y: v });
    }
    return out;
}

function updateSpeedChart() {
    if (!raceData?.boats || !speedChart) return;
    if (!currentRace) return;
    const raceStartMs = new Date(currentRace.start_time).getTime();

    const speedSets = [];
    const heelSets = [];
    const windSets = [];

    const togglesContainer = document.getElementById('speed-chart-toggles');
    togglesContainer.innerHTML = '';

    // Iterate device ids in lexical order so the chart toggles render in
    // a stable position across page loads — the user can build muscle
    // memory for "purple = E5" regardless of API response order, and the
    // chart-toggle row matches the per-marker label colors on the map.
    const orderedEntries = Object.entries(raceData.boats)
        .sort(([a], [b]) => a.localeCompare(b));
    for (const [deviceId, boatData] of orderedEntries) {
        if (boatData.error || !boatData.sensors?.gps?.length) continue;
        const color = colorFor(deviceId);
        const baseDataset = (data) => ({
            label: deviceId,
            data,
            borderColor: color,
            backgroundColor: color + '20',
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.2,
            spanGaps: true,
        });

        speedSets.push(baseDataset(buildSeries(boatData.sensors.gps, 'speed_kn', raceStartMs)));

        // Polar target overlay (dashed, same color, lower opacity). Computed
        // per GPS sample using NOAA wind at that timestamp; downsampled to
        // ~240 points to match the speed line.
        if (polarOverlayVisible && weatherWindSamples.length) {
            const gpsArr = boatData.sensors.gps;
            const step = Math.max(1, Math.floor(gpsArr.length / 240));
            const polarPts = [];
            for (let i = 0; i < gpsArr.length; i += step) {
                const p = gpsArr[i];
                if (!p?.t) continue;
                const t = new Date(p.t).getTime();
                const w = windAt(t);
                if (!w) continue;
                const cog = p.course || 0;
                const twa = ((w.twd - cog + 540) % 360) - 180;
                const target = polarTargetSpeed(twa, w.tws);
                if (target != null && target > 0) {
                    polarPts.push({ x: (t - raceStartMs) / 1000, y: target });
                }
            }
            if (polarPts.length) {
                speedSets.push({
                    label: deviceId + ':polar',
                    data: polarPts,
                    borderColor: color + '88',  // 50% alpha
                    backgroundColor: 'transparent',
                    borderWidth: 1,
                    borderDash: [4, 3],
                    pointRadius: 0,
                    tension: 0.2,
                    spanGaps: false,
                });
            }
        }

        heelSets.push(baseDataset(buildSeries(boatData.sensors.imu, 'heel', raceStartMs)));
        // Wind chart: not per-boat. Filled from NOAA below; per-boat dataset
        // here is just a placeholder so the toggle dot still affects this
        // chart visually (kept hidden). Avoids visual clutter.
        windSets.push({ ...baseDataset([]), hidden: true });

        // One shared toggle controls all three charts for this boat.
        // Now displays the team initials inside the colored chip so a
        // user can map line color → boat without consulting the
        // leaderboard. Hover tooltip still shows the full team / boat name.
        const toggle = document.createElement('button');
        toggle.className = 'chart-toggle';
        toggle.style.borderColor = color;
        toggle.style.background = color;
        const team = boatData.boat?.team_name;
        const boatName = boatData.boat?.boat_name;
        const initials = teamInitials(team || boatName || deviceId);
        toggle.textContent = initials;
        toggle.title = team && boatName
            ? `${team} — ${boatName}`
            : (team || boatName || deviceId);
        toggle.addEventListener('click', () => {
            const sNew = !speedChart.data.datasets.find(d => d.label === deviceId)?.hidden;
            for (const ch of [speedChart, heelChart, windChart]) {
                const ds = ch.data.datasets.find(d => d.label === deviceId);
                if (ds) ds.hidden = sNew;
                ch.update('none');
            }
            toggle.classList.toggle('disabled', sNew);
        });
        togglesContainer.appendChild(toggle);
    }

    speedChart.data.datasets = speedSets;
    heelChart.data.datasets = heelSets;

    // Wind chart: NOAA Castle Island (or fallback) TWD as a single white
    // curve over the race window. Independent of any boat's onboard sensor.
    if (weatherWindSamples.length) {
        const twdSeries = weatherWindSamples
            .filter(s => s.tMs >= raceStartMs)
            .map(s => ({ x: (s.tMs - raceStartMs) / 1000, y: s.twd }));
        windSets.push({
            label: '__noaa_twd__',
            data: twdSeries,
            borderColor: '#e2e8f0',
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.1,
            spanGaps: false,
        });
    }
    windChart.data.datasets = windSets;

    // Update the wind-chart label to reflect the source
    const windHeader = document.querySelector('#analytics-panel .chart-section:nth-child(3) h3');
    if (windHeader) {
        windHeader.textContent = weatherWindSource
            ? `Wind direction (${weatherWindSource})`
            : 'Wind direction (no NOAA data)';
    }

    speedChart.update();
    heelChart.update();
    windChart.update();
}

// --- Mobile UX (tabs + collapsible menu) ---
//
// Activated by CSS media query at <=900px width. JS only needs to:
//   - flip the active tab (CSS handles which panel is visible)
//   - close the slide-down menu on selection
//   - tell Leaflet/Chart.js to re-measure when becoming visible
//     (otherwise they render with the wrong dimensions because they
//      were sized while their parent had display:none).
function setupMobileNav() {
    document.body.dataset.mobileTab = 'map';

    // Tab switching
    const tabs = document.getElementById('mobile-tabs');
    if (tabs) {
        for (const btn of tabs.querySelectorAll('button')) {
            btn.addEventListener('click', () => {
                const t = btn.dataset.mtab;
                document.body.dataset.mobileTab = t;
                for (const b of tabs.querySelectorAll('button')) {
                    b.classList.toggle('active', b === btn);
                }
                // The charts now live inside the desktop overlay container;
                // mirror the open/close state to the overlay's `hidden`
                // attribute so the mobile "Charts" tab keeps working.
                const overlay = document.getElementById('charts-overlay');
                if (overlay) overlay.hidden = (t !== 'charts');
                // Force re-measure so Leaflet/Chart.js fill the now-visible panel
                requestAnimationFrame(() => {
                    if (t === 'map' && map) map.invalidateSize();
                    if (t === 'charts') {
                        for (const ch of [speedChart, heelChart, windChart]) {
                            if (ch) ch.resize();
                        }
                    }
                });
            });
        }
    }

    // Slide-down menu toggle
    const menuBtn = document.getElementById('mobile-menu-btn');
    if (menuBtn) {
        menuBtn.addEventListener('click', () => {
            document.body.classList.toggle('mobile-menu-open');
        });
    }

    // Auto-close the menu on any race-controls click (selectors / buttons),
    // so picking a race or pressing Legs dismisses the overlay naturally.
    const ctrls = document.getElementById('race-controls');
    if (ctrls) {
        ctrls.addEventListener('click', (e) => {
            if (e.target.closest('button, select') && document.body.classList.contains('mobile-menu-open')) {
                document.body.classList.remove('mobile-menu-open');
            }
        });
        ctrls.addEventListener('change', () => {
            if (document.body.classList.contains('mobile-menu-open')) {
                document.body.classList.remove('mobile-menu-open');
            }
        });
    }
}

// --- Per-boat detail drawer ---
let drawerDeviceId = null;

function nearestSampleAt(samples, targetMs) {
    if (!samples?.length) return null;
    let best = null, bestDiff = Infinity;
    for (const s of samples) {
        const t = s.t ? new Date(s.t).getTime() : null;
        if (t == null) continue;
        const d = Math.abs(t - targetMs);
        if (d < bestDiff) { bestDiff = d; best = s; }
    }
    // Reject very stale matches (>30 s away from playback time)
    return bestDiff < 30000 ? best : null;
}

function openBoatDrawer(deviceId) {
    drawerDeviceId = deviceId;
    const el = document.getElementById('boat-drawer');
    if (el) el.classList.add('open');
    updateBoatDrawer();
    renderLeaderboard();  // re-render to highlight active row
}

function closeBoatDrawer() {
    drawerDeviceId = null;
    const el = document.getElementById('boat-drawer');
    if (el) el.classList.remove('open');
    renderLeaderboard();
}

function bearingToCardinal(deg) {
    const dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
    return dirs[Math.round(((deg % 360) / 22.5)) % 16];
}

function fmt(v, digits = 1, suffix = '') {
    if (v == null || !Number.isFinite(v)) return '—';
    return `${v.toFixed(digits)}${suffix}`;
}

function updateBoatDrawer() {
    if (!drawerDeviceId) return;
    const el = document.getElementById('boat-drawer');
    if (!el || !el.classList.contains('open')) return;

    const boatData = raceData?.boats?.[drawerDeviceId];
    const layer = boatLayers[drawerDeviceId];
    const point = layer?.current;
    if (!boatData || !point) {
        document.getElementById('drawer-body').innerHTML =
            '<div class="drawer-empty">No data at this time</div>';
        return;
    }

    const boat = boatData.boat;
    const team = boat?.team_name;
    const boatName = boat?.boat_name;
    document.getElementById('drawer-title').innerHTML = `
        <span class="drawer-color-bar" style="background:${BOAT_COLORS[drawerDeviceId] || '#888'}"></span>
        <span class="drawer-team">${team || boatName || drawerDeviceId}</span>
        ${(team && boatName) ? `<span class="drawer-boat">${boatName}</span>` : ''}
        <span class="drawer-device">(${drawerDeviceId})</span>
    `;

    const targetMs = new Date(point.t).getTime();
    const imu = nearestSampleAt(boatData.sensors?.imu, targetMs);
    const ownWind = nearestSampleAt(boatData.sensors?.wind, targetMs);
    const noaa = windAt(targetMs);

    const sog = point.speed_kn || 0;
    const cog = point.course || 0;
    const twa = noaa ? (((noaa.twd - cog + 540) % 360) - 180) : null;
    const polTarget = polarTargetSpeed(twa, noaa?.tws);
    const polPct = polarPercent(sog, twa, noaa?.tws);
    const tack = twa == null ? '—' : (twa < 0 ? 'Port' : 'Starboard');

    // Course-aware
    const courseSeq = currentRace?.course || [];
    const marksById = buildMarksById(currentRace);
    const startAnchor = startMidpoint(currentRace);
    const legsCompleted = legsCompletedAt(layer, targetMs);
    let nextMarkBlock = '';
    const totalLegsDrawer = currentRace?._totalLegs ?? courseSeq.length;
    if (courseSeq.length && legsCompleted < totalLegsDrawer) {
        const target = marksById[courseSeq[legsCompleted % courseSeq.length]];
        if (target && point.lat && point.lon) {
            const distToNext = haversineMeters(point.lat, point.lon, target.lat, target.lon);
            const brg = bearingDegrees(point.lat, point.lon, target.lat, target.lon);
            const angleDiff = ((brg - cog + 540) % 360) - 180;
            const vmgToMark = sog * Math.cos(angleDiff * Math.PI / 180);
            const ttm = (vmgToMark > 0.1)
                ? `${(distToNext / (vmgToMark * 0.5144)).toFixed(0)} s`
                : '—';
            nextMarkBlock = `
                <div class="drawer-section">
                    <div class="drawer-section-title">Next mark · ${target.name || target.mark_type || ('Mark ' + (legsCompleted + 1))}</div>
                    <div class="drawer-grid">
                        <div class="drawer-stat"><div class="drawer-label">Distance</div><div class="drawer-value">${fmt(distToNext, 0, ' m')}</div></div>
                        <div class="drawer-stat"><div class="drawer-label">Bearing</div><div class="drawer-value">${fmt(brg, 0, '°')} <span class="drawer-sub">${bearingToCardinal(brg)}</span></div></div>
                        <div class="drawer-stat"><div class="drawer-label">VMG</div><div class="drawer-value">${vmgToMark >= 0 ? '+' : ''}${fmt(vmgToMark, 1, ' kn')}</div></div>
                        <div class="drawer-stat"><div class="drawer-label">ETA</div><div class="drawer-value">${ttm}</div></div>
                    </div>
                </div>
            `;
        }
    }

    const ownWindBlock = ownWind ? `
        <div class="drawer-section">
            <div class="drawer-section-title">Onboard wind (Calypso)</div>
            <div class="drawer-grid">
                <div class="drawer-stat"><div class="drawer-label">AWS</div><div class="drawer-value">${fmt(ownWind.aws_kn, 1, ' kn')}</div></div>
                <div class="drawer-stat"><div class="drawer-label">AWA</div><div class="drawer-value">${fmt(ownWind.awa, 0, '°')}</div></div>
            </div>
        </div>
    ` : '';

    document.getElementById('drawer-body').innerHTML = `
        <div class="drawer-section">
            <div class="drawer-section-title">Motion</div>
            <div class="drawer-grid">
                <div class="drawer-stat"><div class="drawer-label">SOG</div><div class="drawer-value drawer-strong">${fmt(sog, 1, ' kn')}</div></div>
                <div class="drawer-stat"><div class="drawer-label">COG</div><div class="drawer-value">${fmt(cog, 0, '°')} <span class="drawer-sub">${bearingToCardinal(cog)}</span></div></div>
                <div class="drawer-stat"><div class="drawer-label">Heel</div><div class="drawer-value">${
                    imu?.heel != null && Number.isFinite(imu.heel)
                        ? `${imu.heel >= 0 ? 'S' : 'P'} ${Math.round(Math.abs(imu.heel))}°`
                        : '—'
                }</div></div>
                <div class="drawer-stat"><div class="drawer-label">Pitch</div><div class="drawer-value">${fmt(imu?.pitch, 0, '°')}</div></div>
            </div>
        </div>
        ${ownWindBlock}
        <div class="drawer-section">
            <div class="drawer-section-title">True wind${weatherWindSource ? ' · ' + weatherWindSource : ''}</div>
            <div class="drawer-grid">
                <div class="drawer-stat"><div class="drawer-label">TWD</div><div class="drawer-value">${fmt(noaa?.twd, 0, '°')} <span class="drawer-sub">${noaa ? bearingToCardinal(noaa.twd) : ''}</span></div></div>
                <div class="drawer-stat"><div class="drawer-label">TWS</div><div class="drawer-value">${fmt(noaa?.tws, 1, ' kn')}</div></div>
                <div class="drawer-stat"><div class="drawer-label">TWA</div><div class="drawer-value">${twa == null ? '—' : `${tack[0]} ${Math.abs(twa).toFixed(0)}°`}</div></div>
                <div class="drawer-stat"><div class="drawer-label">Tack</div><div class="drawer-value">${tack}</div></div>
            </div>
        </div>
        <div class="drawer-section">
            <div class="drawer-section-title">Polar (J/80)</div>
            <div class="drawer-grid">
                <div class="drawer-stat"><div class="drawer-label">Target</div><div class="drawer-value">${fmt(polTarget, 1, ' kn')}</div></div>
                <div class="drawer-stat"><div class="drawer-label">% polar</div><div class="drawer-value drawer-strong">${fmt(polPct, 0, '%')}</div></div>
            </div>
        </div>
        ${nextMarkBlock}
    `;
}

// --- Leg summary ---

function computeLegSummary() {
    if (!currentRace || !raceData?.boats) return [];
    const courseSeq = currentRace.course || [];
    if (!courseSeq.length) return [];
    const startTimeMs = new Date(currentRace.start_time).getTime();
    const rows = [];

    for (const [deviceId, boatData] of Object.entries(raceData.boats)) {
        const layer = boatLayers[deviceId];
        if (!layer?.data?.length || !layer.roundingTimes) continue;
        const team = boatData.boat?.team_name || boatData.boat?.boat_name || deviceId;

        // Boundaries for completed legs only.
        const bounds = [startTimeMs];
        for (const t of layer.roundingTimes) {
            if (t !== undefined) bounds.push(t); else break;
        }
        if (bounds.length < 2) continue;

        for (let leg = 0; leg < bounds.length - 1; leg++) {
            const tStart = bounds[leg], tEnd = bounds[leg + 1];
            const samples = layer.data.filter(p => {
                const t = new Date(p.t).getTime();
                return t >= tStart && t < tEnd && p.lat && p.lon;
            });
            if (samples.length < 2) continue;

            const sumSog = samples.reduce((s, p) => s + (p.speed_kn || 0), 0);
            const avgSog = sumSog / samples.length;

            let polSum = 0, polN = 0;
            for (const p of samples) {
                const t = new Date(p.t).getTime();
                const w = windAt(t);
                if (!w) continue;
                const twa = ((w.twd - (p.course || 0) + 540) % 360) - 180;
                const pp = polarPercent(p.speed_kn || 0, twa, w.tws);
                if (pp != null) { polSum += pp; polN++; }
            }
            const avgPol = polN > 0 ? polSum / polN : null;

            let dist = 0;
            for (let i = 1; i < samples.length; i++) {
                dist += haversineMeters(samples[i-1].lat, samples[i-1].lon, samples[i].lat, samples[i].lon);
            }

            rows.push({
                deviceId, team,
                leg: leg + 1,
                durationSec: (tEnd - tStart) / 1000,
                avgSog, avgPolPct: avgPol, distM: dist,
            });
        }
    }
    return rows;
}

function fmtMMSS(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return '—';
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function openLegModal() {
    const body = document.getElementById('leg-modal-body');
    if (!body) return;
    const rows = computeLegSummary();
    if (!rows.length) {
        body.innerHTML = '<div class="modal-empty">No leg data — race needs a defined course with mark roundings.</div>';
    } else {
        // Group by leg, then sort within each leg by duration ASC
        const byLeg = {};
        for (const r of rows) (byLeg[r.leg] = byLeg[r.leg] || []).push(r);
        const legs = Object.keys(byLeg).map(Number).sort((a, b) => a - b);

        let html = '';
        for (const leg of legs) {
            const group = byLeg[leg].sort((a, b) => a.durationSec - b.durationSec);
            const fastest = group[0]?.durationSec || 0;
            html += `<h3 class="leg-section-title">Leg ${leg}</h3>
                <table class="data-table">
                    <thead>
                        <tr><th>#</th><th>Team</th><th>Time</th><th>Δ leader</th><th>Avg SOG</th><th>Avg %pol</th><th>Distance</th></tr>
                    </thead><tbody>`;
            group.forEach((r, i) => {
                const delta = r.durationSec - fastest;
                html += `<tr class="${i === 0 ? 'leg-leader' : ''}">
                    <td>${i + 1}</td>
                    <td><span class="lb-color" style="background:${BOAT_COLORS[r.deviceId] || '#888'}"></span>${r.team}</td>
                    <td>${fmtMMSS(r.durationSec)}</td>
                    <td>${i === 0 ? '—' : '+' + fmtMMSS(delta)}</td>
                    <td>${r.avgSog.toFixed(1)} kn</td>
                    <td>${r.avgPolPct != null ? r.avgPolPct.toFixed(0) + '%' : '—'}</td>
                    <td>${(r.distM / 1000).toFixed(2)} km</td>
                </tr>`;
            });
            html += '</tbody></table>';
        }
        body.innerHTML = html;
    }
    document.getElementById('leg-modal').style.display = 'flex';
}

// --- Maneuver detection (tacks & gybes) ---
//
// Heuristic, but tuned for J/80 racing on flat-ish water:
//   1. Walk each boat's GPS track. At every sample, compute the heading
//      change relative to ~10s earlier.
//   2. When |Δheading| > 60° within a 30s window AND speed in that
//      window dipped below 70% of the pre-window average, classify it
//      as a maneuver.
//   3. Use NOAA TWD at the entry to classify tack vs gybe by absolute
//      TWA before the maneuver (<90° upwind = tack, >90° downwind = gybe).

function detectManeuversForLayer(layer) {
    const out = [];
    const data = layer.data;
    if (!data || data.length < 30) return out;

    const tMs = data.map(p => new Date(p.t).getTime());
    const speeds = data.map(p => p.speed_kn || 0);
    const cogs = data.map(p => p.course || 0);

    let i = 10;
    while (i < data.length - 30) {
        const before = speeds.slice(i - 10, i);
        const avgBefore = before.reduce((s, v) => s + v, 0) / before.length;
        if (avgBefore < 2) { i++; continue; }

        let maxDh = 0, endIdx = i;
        for (let j = i + 1; j < Math.min(data.length, i + 30); j++) {
            const dh = Math.abs(((cogs[j] - cogs[i] + 540) % 360) - 180);
            if (dh > maxDh) { maxDh = dh; endIdx = j; }
        }
        if (maxDh < 60) { i++; continue; }

        // Speed dip inside [i, endIdx]
        let minSpd = Infinity;
        for (let j = i; j <= endIdx; j++) if (speeds[j] < minSpd) minSpd = speeds[j];
        if (minSpd > avgBefore * 0.7) { i++; continue; }

        const after = speeds.slice(endIdx, Math.min(data.length, endIdx + 10));
        const avgAfter = after.reduce((s, v) => s + v, 0) / Math.max(1, after.length);

        const wEntry = windAt(tMs[i]);
        let type = 'rounding', twaBefore = null, twaAfter = null;
        if (wEntry) {
            const a = ((wEntry.twd - cogs[i] + 540) % 360) - 180;
            const b = ((wEntry.twd - cogs[endIdx] + 540) % 360) - 180;
            twaBefore = a; twaAfter = b;
            if (Math.abs(a) < 90 && Math.abs(b) < 90) type = 'tack';
            else if (Math.abs(a) > 90 && Math.abs(b) > 90) type = 'gybe';
            else type = 'rounding';
        }

        out.push({
            tStart: tMs[i], tEnd: tMs[endIdx],
            durationSec: (tMs[endIdx] - tMs[i]) / 1000,
            speedBefore: avgBefore, speedAfter: avgAfter, speedMin: minSpd,
            loss: Math.max(0, avgBefore - avgAfter),
            headingChange: maxDh,
            twaBefore, twaAfter, type,
        });
        i = endIdx + 10;  // skip past this maneuver
    }
    return out;
}

function openManeuverModal() {
    const body = document.getElementById('maneuver-modal-body');
    if (!body) return;
    if (!raceData?.boats) {
        body.innerHTML = '<div class="modal-empty">No race data loaded.</div>';
        document.getElementById('maneuver-modal').style.display = 'flex';
        return;
    }

    // Aggregate by team × type (tack / gybe)
    const summary = [];
    const allManeuvers = [];
    for (const [deviceId, boatData] of Object.entries(raceData.boats)) {
        const layer = boatLayers[deviceId];
        if (!layer?.data?.length) continue;
        const team = boatData.boat?.team_name || boatData.boat?.boat_name || deviceId;
        const ms = detectManeuversForLayer(layer);
        for (const m of ms) allManeuvers.push({ deviceId, team, ...m });

        const tacks = ms.filter(m => m.type === 'tack');
        const gybes = ms.filter(m => m.type === 'gybe');
        summary.push({
            deviceId, team,
            tacksCount: tacks.length,
            tacksAvgLoss: tacks.length ? tacks.reduce((s, m) => s + m.loss, 0) / tacks.length : null,
            tacksAvgDur:  tacks.length ? tacks.reduce((s, m) => s + m.durationSec, 0) / tacks.length : null,
            gybesCount: gybes.length,
            gybesAvgLoss: gybes.length ? gybes.reduce((s, m) => s + m.loss, 0) / gybes.length : null,
            gybesAvgDur:  gybes.length ? gybes.reduce((s, m) => s + m.durationSec, 0) / gybes.length : null,
        });
    }

    if (!summary.length) {
        body.innerHTML = '<div class="modal-empty">No boat data.</div>';
        document.getElementById('maneuver-modal').style.display = 'flex';
        return;
    }

    summary.sort((a, b) => (a.tacksAvgLoss ?? 99) - (b.tacksAvgLoss ?? 99));

    let html = `<h3 class="maneuver-section-title">Per-team summary (sorted by tack loss)</h3>
        <table class="data-table">
            <thead>
                <tr><th>Team</th>
                    <th>Tacks</th><th>Avg loss</th><th>Avg dur</th>
                    <th>Gybes</th><th>Avg loss</th><th>Avg dur</th></tr>
            </thead><tbody>`;
    for (const s of summary) {
        html += `<tr>
            <td><span class="lb-color" style="background:${BOAT_COLORS[s.deviceId] || '#888'}"></span>${s.team}</td>
            <td>${s.tacksCount}</td>
            <td>${s.tacksAvgLoss != null ? s.tacksAvgLoss.toFixed(2) + ' kn' : '—'}</td>
            <td>${s.tacksAvgDur != null ? s.tacksAvgDur.toFixed(1) + ' s' : '—'}</td>
            <td>${s.gybesCount}</td>
            <td>${s.gybesAvgLoss != null ? s.gybesAvgLoss.toFixed(2) + ' kn' : '—'}</td>
            <td>${s.gybesAvgDur != null ? s.gybesAvgDur.toFixed(1) + ' s' : '—'}</td>
        </tr>`;
    }
    html += '</tbody></table>';

    // Per-maneuver detail
    allManeuvers.sort((a, b) => a.tStart - b.tStart);
    if (allManeuvers.length) {
        html += `<h3 class="maneuver-section-title" style="margin-top:1.5rem">Every maneuver, in order</h3>
            <table class="data-table">
                <thead>
                    <tr><th>Time</th><th>Team</th><th>Type</th>
                        <th>Δ heading</th><th>TWA in → out</th>
                        <th>SOG before</th><th>min</th><th>after</th>
                        <th>Loss</th><th>Duration</th></tr>
                </thead><tbody>`;
        const raceStart = new Date(currentRace.start_time).getTime();
        for (const m of allManeuvers) {
            const elapsed = (m.tStart - raceStart) / 1000;
            const twaIn = m.twaBefore == null ? '—' : `${m.twaBefore < 0 ? 'P' : 'S'}${Math.abs(m.twaBefore).toFixed(0)}°`;
            const twaOut = m.twaAfter == null ? '—' : `${m.twaAfter < 0 ? 'P' : 'S'}${Math.abs(m.twaAfter).toFixed(0)}°`;
            const typeClass = m.type === 'tack' ? 'mtype-tack' : (m.type === 'gybe' ? 'mtype-gybe' : 'mtype-other');
            html += `<tr>
                <td>${fmtMMSS(elapsed)}</td>
                <td><span class="lb-color" style="background:${BOAT_COLORS[m.deviceId] || '#888'}"></span>${m.team}</td>
                <td><span class="${typeClass}">${m.type}</span></td>
                <td>${m.headingChange.toFixed(0)}°</td>
                <td>${twaIn} → ${twaOut}</td>
                <td>${m.speedBefore.toFixed(1)}</td>
                <td>${m.speedMin.toFixed(1)}</td>
                <td>${m.speedAfter.toFixed(1)}</td>
                <td>${m.loss.toFixed(2)} kn</td>
                <td>${m.durationSec.toFixed(1)} s</td>
            </tr>`;
        }
        html += '</tbody></table>';
    }

    body.innerHTML = html;
    document.getElementById('maneuver-modal').style.display = 'flex';
}

// Move the dashed play cursor on each chart without redrawing the data lines.
function updatePlayCursor(seconds) {
    playCursorSeconds = seconds;
    for (const ch of [speedChart, heelChart, windChart]) {
        if (ch) ch.draw();
    }
}

// --- Playback ---

function setupPlaybackControls() {
    const playBtn = document.getElementById('btn-play');
    const slider = document.getElementById('timeline-slider');
    const speedSelect = document.getElementById('playback-speed');

    playBtn.addEventListener('click', togglePlayback);

    slider.addEventListener('input', (e) => {
        const position = parseInt(e.target.value) / 1000;
        seekTo(position);
    });

    speedSelect.addEventListener('change', (e) => {
        playbackSpeed = parseFloat(e.target.value);
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

        if (e.code === 'Space') {
            e.preventDefault();
            togglePlayback();
        } else if (e.code === 'ArrowLeft') {
            seekTo(Math.max(0, currentTime / raceDuration - 0.01));
        } else if (e.code === 'ArrowRight') {
            seekTo(Math.min(1, currentTime / raceDuration + 0.01));
        }
    });
}

function togglePlayback() {
    isPlaying = !isPlaying;
    const playBtn = document.getElementById('btn-play');
    playBtn.textContent = isPlaying ? '⏸' : '▶';

    if (isPlaying) {
        startPlayback();
    } else {
        stopPlayback();
    }
}

function startPlayback() {
    if (playbackInterval) clearInterval(playbackInterval);

    playbackInterval = setInterval(() => {
        currentTime += 0.1 * playbackSpeed;

        if (currentTime >= raceDuration) {
            currentTime = 0;
            stopPlayback();
            return;
        }

        updatePlaybackPosition();
    }, 100);
}

function stopPlayback() {
    isPlaying = false;
    document.getElementById('btn-play').textContent = '▶';
    if (playbackInterval) {
        clearInterval(playbackInterval);
        playbackInterval = null;
    }
}

function seekTo(position) {
    currentTime = position * raceDuration;
    updatePlaybackPosition();
}

function updatePlaybackPosition() {
    // Update slider
    const slider = document.getElementById('timeline-slider');
    slider.value = (currentTime / raceDuration) * 1000;

    // Update time display
    document.getElementById('time-current').textContent = formatTime(currentTime);
    document.getElementById('elapsed-time').textContent = formatTime(currentTime);

    // Update boat positions on map
    updateBoatPositions(currentTime);

    // Update leaderboard
    renderLeaderboard();
}

function formatTime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// --- Data Loading ---

async function loadRegattas() {
    try {
        const resp = await fetch(`${API_BASE}/api/regattas`);
        const data = await resp.json();
        regattas = data.regattas || [];

        // Populate regatta selects
        const regattaSelect = document.getElementById('regatta-select');
        const regattaInput = document.getElementById('regatta-input');

        const options = regattas.map(r =>
            `<option value="${r.regatta_id}">${r.name}</option>`
        ).join('');

        regattaSelect.innerHTML = '<option value="">Select Regatta...</option>' +
            '<option value="__all__">All Races</option>' + options;
        regattaInput.innerHTML = '<option value="">None</option>' + options;

        // Clear dependent selects
        document.getElementById('raceday-select').innerHTML = '<option value="">Select Day...</option>';
        document.getElementById('race-select').innerHTML = '<option value="">Select Race...</option>';

    } catch (err) {
        console.error('[Race] Failed to load regattas:', err);
    }
}

async function loadRaceDays(regattaId) {
    const raceDaySelect = document.getElementById('raceday-select');
    const raceSelect = document.getElementById('race-select');

    if (!regattaId) {
        raceDaySelect.innerHTML = '<option value="">Select Day...</option>';
        raceSelect.innerHTML = '<option value="">Select Race...</option>';
        raceDays = [];
        races = [];
        return;
    }

    try {
        // Load races - either for specific regatta or all races
        const url = regattaId === '__all__'
            ? `${API_BASE}/api/races`
            : `${API_BASE}/api/races?regatta_id=${regattaId}`;
        const resp = await fetch(url);
        const data = await resp.json();
        const allRaces = data.races || [];

        // Group by date to get race days
        const dayMap = {};
        for (const race of allRaces) {
            if (!dayMap[race.date]) {
                dayMap[race.date] = [];
            }
            dayMap[race.date].push(race);
        }

        // Sort dates and create race days
        raceDays = Object.keys(dayMap).sort().map(date => ({
            date: date,
            races: dayMap[date].sort((a, b) => a.start_time.localeCompare(b.start_time)),
        }));

        // Populate race day select
        raceDaySelect.innerHTML = '<option value="">Select Day...</option>' +
            raceDays.map(d => {
                const raceCount = d.races.length;
                const dayName = new Date(d.date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
                return `<option value="${d.date}">${dayName} (${raceCount} race${raceCount !== 1 ? 's' : ''})</option>`;
            }).join('');

        // Clear race select
        raceSelect.innerHTML = '<option value="">Select Race...</option>';
        races = [];

        console.log('[Race] Loaded race days:', raceDays);

    } catch (err) {
        console.error('[Race] Failed to load race days:', err);
    }
}

function loadRacesForDay(date) {
    const raceSelect = document.getElementById('race-select');

    if (!date) {
        raceSelect.innerHTML = '<option value="">Select Race...</option>';
        races = [];
        currentRaceDay = null;
        return;
    }

    // Find the race day
    currentRaceDay = raceDays.find(d => d.date === date);
    if (!currentRaceDay) {
        raceSelect.innerHTML = '<option value="">Select Race...</option>';
        races = [];
        return;
    }

    races = currentRaceDay.races;

    // Populate race select with race name and start time (local time)
    raceSelect.innerHTML = '<option value="">Select Race...</option>' +
        races.map(r => {
            const startLocal = new Date(r.start_time);
            const startTime = startLocal.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
            return `<option value="${r.race_id}">${r.name} @ ${startTime}</option>`;
        }).join('');

    console.log('[Race] Loaded races for', date, ':', races);
}

async function loadRaceData(raceId) {
    try {
        // Load race definition
        const raceResp = await fetch(`${API_BASE}/api/races/${raceId}`);
        currentRace = await raceResp.json();

        // Update UI with local time
        document.getElementById('race-name').textContent = currentRace.name;
        const startLocal = new Date(currentRace.start_time);
        const localTimeStr = startLocal.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
        document.getElementById('race-time').textContent = `${currentRace.date} ${localTimeStr}`;
        document.getElementById('btn-edit-race').disabled = false;
        const editCourseBtn = document.getElementById('btn-edit-course');
        if (editCourseBtn) editCourseBtn.disabled = false;

        // Load sensor data for all boats
        const dataResp = await fetch(`${API_BASE}/api/races/${raceId}/data?sensors=gps,imu,wind`);
        raceData = await dataResp.json();

        console.log('[Race] Race time window:', currentRace.start_time, 'to', currentRace.end_time);
        console.log('[Race] Loaded data:', raceData);

        // Calculate race duration
        const start = new Date(currentRace.start_time).getTime();
        const end = new Date(currentRace.end_time).getTime();
        raceDuration = (end - start) / 1000;

        // Update time display
        document.getElementById('time-total').textContent = formatTime(raceDuration);

        // Clear existing layers and add new ones
        clearBoatLayers();
        clearCourseLayers();

        let totalGpsPoints = 0;
        for (const [deviceId, boatData] of Object.entries(raceData.boats)) {
            if (boatData.error || !boatData.sensors?.gps?.length) {
                console.warn(`[Race] No GPS data for ${deviceId}:`, boatData.error || 'empty array');
                continue;
            }

            const gpsCount = boatData.sensors.gps.length;
            totalGpsPoints += gpsCount;
            console.log(`[Race] ${deviceId}: ${gpsCount} GPS points, first:`, boatData.sensors.gps[0]);
            addBoatTrack(deviceId, boatData.sensors.gps, boatData.boat, boatData.sensors.imu || []);
        }

        console.log(`[Race] Total GPS points: ${totalGpsPoints}, boatLayers:`, Object.keys(boatLayers));

        // Initial framing: always zoom to start line + first mark on
        // race load — that's where the action begins regardless of
        // whether follow-mode is enabled. The follow-mode throttle is
        // armed (lastFollowPanMs = now) so the first updateBoatPositions
        // tick doesn't immediately re-fly past this framing; subsequent
        // playback ticks then take over once enough time has passed.
        fitMapToBounds();
        lastFollowPanMs = Date.now();

        // Render course (marks + start/finish lines) if present
        renderCourseViewLayer(currentRace);

        // Pre-compute course progress (mark roundings + leg lengths) per
        // boat. Cheap to do once, drives the leaderboard ranking and VMG.
        precomputeAllRoundings();

        // Fetch nearby NOAA wind (Castle Island / Logan / Boston 16NM).
        // Awaited so laylines + the wind chart can use it on first render.
        await loadRaceWindData(currentRace.start_time, currentRace.end_time);

        // Render legend and leaderboard
        renderBoatLegend();
        renderLeaderboard();

        // Lay out laylines from the next windward mark using race-average TWD.
        renderLaylines();

        // Update speed/heel/wind charts (wind chart now uses NOAA TWD)
        updateSpeedChart();

        // Reset playback
        currentTime = 0;
        updatePlaybackPosition();

        console.log('[Race] Loaded race data:', currentRace.name);

    } catch (err) {
        console.error('[Race] Failed to load race data:', err);
        alert('Failed to load race data. Check console for details.');
    }
}

// --- Race Editor Modal ---

async function loadAvailableSessions() {
    try {
        const resp = await fetch(`${API_BASE}/api/sessions`);
        const data = await resp.json();
        const sessions = data.sessions || [];

        // Group sessions by device
        availableSessions = {};
        for (const session of sessions) {
            const deviceId = session.device_id;
            if (!availableSessions[deviceId]) {
                availableSessions[deviceId] = [];
            }
            // Full session path is "date-session_id" (e.g., "2026-04-19-154818")
            const fullPath = `${session.date}-${session.session_id}`;

            // Format start time in LOCAL time (not UTC)
            let startTimeStr = '';
            if (session.start_time) {
                const startDate = new Date(session.start_time);
                startTimeStr = startDate.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: true
                });
            }

            // Get duration in minutes
            let durationMin = '?';
            if (session.duration_minutes !== undefined && session.duration_minutes !== null) {
                durationMin = session.duration_minutes;
            } else if (session.duration_sec !== undefined && session.duration_sec !== null) {
                durationMin = Math.round(session.duration_sec / 60);
            }

            availableSessions[deviceId].push({
                path: fullPath,
                label: `${session.date} @ ${startTimeStr} (${durationMin}min)`,
                name: session.name || '',
            });
        }
        console.log('[Race] Loaded sessions:', availableSessions);
    } catch (err) {
        console.error('[Race] Failed to load sessions:', err);
    }
}

async function openRaceModal(race = null) {
    const modal = document.getElementById('race-modal');
    const title = document.getElementById('modal-title');
    const deleteBtn = document.getElementById('btn-delete-race');

    // Reset staged GPX files whenever modal opens
    pendingGpxFiles = {};

    // Load available sessions for dropdown
    await loadAvailableSessions();

    if (race) {
        title.textContent = 'Edit Race';
        populateRaceForm(race);
        deleteBtn.style.display = IS_ADMIN ? 'block' : 'none';  // Show delete button for admins only
    } else {
        title.textContent = 'New Race';
        clearRaceForm();
        deleteBtn.style.display = 'none';   // Hide delete button for new races
    }

    modal.style.display = 'flex';
}

function closeRaceModal() {
    document.getElementById('race-modal').style.display = 'none';
}

function handleGpxFileSelect(event, deviceId) {
    const file = event.target.files[0];
    if (!file) return;

    pendingGpxFiles[deviceId] = file;

    const row = document.querySelector(`.boat-assignment[data-device="${deviceId}"]`);
    if (!row) return;

    row.dataset.gpxPath = '';  // Will be set by server after upload
    row.querySelector('.session-select').classList.add('hidden');
    row.querySelector('.gpx-badge').classList.remove('hidden');
    row.querySelector('.gpx-badge-name').textContent = file.name;
}

function handleGpxClear(deviceId) {
    delete pendingGpxFiles[deviceId];

    const row = document.querySelector(`.boat-assignment[data-device="${deviceId}"]`);
    if (!row) return;

    row.dataset.gpxPath = '';
    row.querySelector('.session-select').classList.remove('hidden');
    row.querySelector('.gpx-badge').classList.add('hidden');
    row.querySelector('.gpx-badge-name').textContent = '';

    const fileInput = row.querySelector('.gpx-file-input');
    if (fileInput) fileInput.value = '';
}

async function uploadPendingGpxFiles(raceId) {
    for (const [deviceId, file] of Object.entries(pendingGpxFiles)) {
        const formData = new FormData();
        formData.append('file', file);
        try {
            const resp = await fetch(`${API_BASE}/api/races/${raceId}/boats/${deviceId}/gpx`, {
                method: 'POST',
                body: formData,
            });
            if (resp.ok) {
                const result = await resp.json();
                console.log(`[Race] GPX uploaded for ${deviceId}: ${result.points} points`);
            } else {
                console.error(`[Race] GPX upload failed for ${deviceId}:`, await resp.text());
            }
        } catch (err) {
            console.error(`[Race] GPX upload error for ${deviceId}:`, err);
        }
    }
    pendingGpxFiles = {};
}

function clearRaceForm() {
    document.getElementById('race-name-input').value = '';
    document.getElementById('race-date-input').value = new Date().toISOString().split('T')[0];
    document.getElementById('start-time-input').value = '18:00';
    document.getElementById('end-time-input').value = '18:30';
    document.getElementById('regatta-input').value = '';

    // Default boat assignments (6 boats)
    renderBoatAssignments([
        { device_id: 'E1', boat_name: '', team_name: '', sail_number: '' },
        { device_id: 'E2', boat_name: '', team_name: '', sail_number: '' },
        { device_id: 'E3', boat_name: '', team_name: '', sail_number: '' },
        { device_id: 'E4', boat_name: '', team_name: '', sail_number: '' },
        { device_id: 'E5', boat_name: '', team_name: '', sail_number: '' },
        { device_id: 'E6', boat_name: '', team_name: '', sail_number: '' },
    ]);
}

function populateRaceForm(race) {
    document.getElementById('race-name-input').value = race.name || '';
    document.getElementById('race-date-input').value = race.date || '';

    // Convert UTC times to local time for display
    if (race.start_time) {
        const startLocal = new Date(race.start_time);
        document.getElementById('start-time-input').value =
            startLocal.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } else {
        document.getElementById('start-time-input').value = '';
    }

    if (race.end_time) {
        const endLocal = new Date(race.end_time);
        document.getElementById('end-time-input').value =
            endLocal.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } else {
        document.getElementById('end-time-input').value = '';
    }

    document.getElementById('regatta-input').value = race.regatta_id || '';

    renderBoatAssignments(race.boats || []);
    renderFinishOrder(race.finish_order || [], race.boats || []);
}

function renderBoatAssignments(boats) {
    const container = document.getElementById('boat-assignments');

    // Ensure all 6 devices
    const allDevices = ['E1', 'E2', 'E3', 'E4', 'E5', 'E6'];
    const boatMap = {};
    for (const b of boats) {
        boatMap[b.device_id] = b;
    }

    // Build datalist options for autocomplete
    const boatOptions = FLEET_BOATS.map(b => `<option value="${b}">`).join('');
    const teamOptions = FLEET_TEAMS.map(t => `<option value="${t}">`).join('');

    container.innerHTML = `
        <datalist id="boat-names">${boatOptions}</datalist>
        <datalist id="team-names">${teamOptions}</datalist>
    ` + allDevices.map(deviceId => {
        const boat = boatMap[deviceId] || { device_id: deviceId, boat_name: '', team_name: '', sail_number: '', session_path: '', gpx_path: '' };
        const color = BOAT_COLORS[deviceId];
        const sessions = availableSessions[deviceId] || [];

        // Build session dropdown options
        const sessionOptions = sessions.map(s => {
            const selected = boat.session_path === s.path ? 'selected' : '';
            const label = s.name ? `${s.label} - ${s.name}` : s.label;
            return `<option value="${s.path}" ${selected}>${label}</option>`;
        }).join('');

        const gpxActive = !!(boat.gpx_path || pendingGpxFiles[deviceId]);
        const gpxLabel = pendingGpxFiles[deviceId]
            ? pendingGpxFiles[deviceId].name
            : (boat.gpx_path ? 'GPX uploaded' : '');

        return `
            <div class="boat-assignment" data-device="${deviceId}" data-gpx-path="${boat.gpx_path || ''}">
                <div class="boat-assignment-device">
                    <span class="boat-assignment-color" style="background: ${color}"></span>
                    <span>${deviceId}</span>
                </div>
                <input type="text" placeholder="Team" value="${boat.team_name || ''}" data-field="team_name" list="team-names">
                <input type="text" placeholder="Boat" value="${boat.boat_name || ''}" data-field="boat_name" list="boat-names">
                <div class="session-or-gpx">
                    <select data-field="session_path" class="session-select${gpxActive ? ' hidden' : ''}">
                        <option value="">Select session...</option>
                        ${sessionOptions}
                    </select>
                    <div class="gpx-badge${gpxActive ? '' : ' hidden'}">
                        <span class="gpx-badge-name">${gpxLabel}</span>
                        <button class="btn-gpx-clear" type="button" title="Remove GPX">&times;</button>
                    </div>
                    <label class="btn-gpx" title="Upload GPX track">GPX<input type="file" accept=".gpx" class="gpx-file-input" style="display:none"></label>
                </div>
            </div>
        `;
    }).join('');

    // Attach GPX file input and clear button listeners
    container.querySelectorAll('.gpx-file-input').forEach(input => {
        const deviceId = input.closest('.boat-assignment').dataset.device;
        input.addEventListener('change', (e) => handleGpxFileSelect(e, deviceId));
    });
    container.querySelectorAll('.btn-gpx-clear').forEach(btn => {
        const deviceId = btn.closest('.boat-assignment').dataset.device;
        btn.addEventListener('click', () => handleGpxClear(deviceId));
    });
}

function renderFinishOrder(order, boats) {
    const container = document.getElementById('finish-order');

    // Build list of boats with positions
    const boatMap = {};
    for (const b of boats) {
        boatMap[b.device_id] = b;
    }

    // Use order if provided, otherwise use boats array order
    const orderedDevices = order.length > 0 ? order : boats.map(b => b.device_id);

    container.innerHTML = orderedDevices.map((deviceId, index) => {
        const boat = boatMap[deviceId] || { device_id: deviceId, boat_name: deviceId };
        const color = BOAT_COLORS[deviceId];

        return `
            <div class="finish-order-item" draggable="true" data-device="${deviceId}">
                <span class="finish-order-position">${index + 1}</span>
                <div class="finish-order-boat">
                    <span class="boat-assignment-color" style="background: ${color}"></span>
                    <span>${boat.boat_name || deviceId}</span>
                </div>
            </div>
        `;
    }).join('');

    // Setup drag and drop
    setupFinishOrderDragDrop();
}

function setupFinishOrderDragDrop() {
    const container = document.getElementById('finish-order');
    let draggedItem = null;

    container.querySelectorAll('.finish-order-item').forEach(item => {
        item.addEventListener('dragstart', () => {
            draggedItem = item;
            item.style.opacity = '0.5';
        });

        item.addEventListener('dragend', () => {
            draggedItem = null;
            item.style.opacity = '1';
            updateFinishOrderPositions();
        });

        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            const afterElement = getDragAfterElement(container, e.clientY);
            if (afterElement == null) {
                container.appendChild(draggedItem);
            } else {
                container.insertBefore(draggedItem, afterElement);
            }
        });
    });
}

function getDragAfterElement(container, y) {
    const elements = [...container.querySelectorAll('.finish-order-item:not(.dragging)')];

    return elements.reduce((closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
            return { offset, element: child };
        } else {
            return closest;
        }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
}

function updateFinishOrderPositions() {
    const items = document.querySelectorAll('.finish-order-item');
    items.forEach((item, index) => {
        item.querySelector('.finish-order-position').textContent = index + 1;
    });
}

function getFormData() {
    const date = document.getElementById('race-date-input').value;
    const startTime = document.getElementById('start-time-input').value || '00:00';
    const endTime = document.getElementById('end-time-input').value || '00:30';

    // Validate date
    if (!date) {
        throw new Error('Date is required');
    }

    // Convert local time to UTC ISO string
    // Input is in local time (user's timezone), we need to convert to UTC for storage
    const startLocal = new Date(`${date}T${startTime}`);
    const endLocal = new Date(`${date}T${endTime}`);

    // Validate dates
    if (isNaN(startLocal.getTime())) {
        throw new Error('Invalid start time');
    }
    if (isNaN(endLocal.getTime())) {
        throw new Error('Invalid end time');
    }

    // toISOString() returns UTC
    const startUTC = startLocal.toISOString();
    const endUTC = endLocal.toISOString();

    // Build boats array from form
    const boats = [];
    document.querySelectorAll('.boat-assignment').forEach(row => {
        const deviceId = row.dataset.device;
        const teamName = row.querySelector('[data-field="team_name"]')?.value || '';
        const boatName = row.querySelector('[data-field="boat_name"]')?.value || '';
        const gpxPath = row.dataset.gpxPath || null;
        const hasPendingGpx = !!pendingGpxFiles[deviceId];
        const isGpxActive = hasPendingGpx || !!gpxPath;
        // When GPX is active, clear session; when session active, clear gpx_path
        const sessionPath = isGpxActive ? null : (row.querySelector('[data-field="session_path"]')?.value || null);

        if (teamName || boatName || sessionPath || isGpxActive) {
            boats.push({
                device_id: deviceId,
                team_name: teamName,
                boat_name: boatName,
                session_path: sessionPath,
                gpx_path: isGpxActive ? gpxPath : null,
            });
        }
    });

    // Get finish order
    const finishOrder = [];
    document.querySelectorAll('.finish-order-item').forEach(item => {
        finishOrder.push(item.dataset.device);
    });

    return {
        name: document.getElementById('race-name-input').value,
        date: date,
        start_time: startUTC,
        end_time: endUTC,
        regatta_id: document.getElementById('regatta-input').value || null,
        boats,
        finish_order: finishOrder,
    };
}

async function saveRace() {
    let formData;
    try {
        formData = getFormData();
    } catch (err) {
        alert(err.message);
        return;
    }

    try {
        let resp;
        if (currentRace?.race_id) {
            // Update existing
            resp = await fetch(`${API_BASE}/api/races/${currentRace.race_id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData),
            });
        } else {
            // Create new
            resp = await fetch(`${API_BASE}/api/races`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData),
            });
        }

        if (!resp.ok) {
            const errorText = await resp.text();
            console.error('[Race] API error:', resp.status, errorText);
            throw new Error(`HTTP ${resp.status}: ${errorText}`);
        }

        const savedRace = await resp.json();
        console.log('[Race] Saved race:', savedRace);

        // Upload any GPX tracks staged for this race
        if (Object.keys(pendingGpxFiles).length > 0) {
            await uploadPendingGpxFiles(savedRace.race_id);
        }

        closeRaceModal();

        // Directly load the saved race data (this will update map, charts, etc.)
        await loadRaceData(savedRace.race_id);

        // Update dropdown selections to reflect current race
        const regattaId = savedRace.regatta_id || '__all__';
        document.getElementById('regatta-select').value = regattaId;
        await loadRaceDays(regattaId);
        if (savedRace.date) {
            document.getElementById('raceday-select').value = savedRace.date;
            loadRacesForDay(savedRace.date);
            document.getElementById('race-select').value = savedRace.race_id;
        }

    } catch (err) {
        console.error('[Race] Failed to save race:', err);
        alert(`Failed to save race: ${err.message}`);
    }
}

async function matchSessions() {
    if (!currentRace?.race_id) {
        alert('Save the race first before matching sessions.');
        return;
    }

    try {
        const resp = await fetch(`${API_BASE}/api/races/${currentRace.race_id}/match-sessions`, {
            method: 'POST',
        });

        const result = await resp.json();
        console.log('[Race] Matched sessions:', result);

        // Reload race to get updated session paths
        const raceResp = await fetch(`${API_BASE}/api/races/${currentRace.race_id}`);
        const updatedRace = await raceResp.json();

        renderBoatAssignments(updatedRace.boats || []);

        alert(`Matched ${result.matched.filter(m => m.session_path).length} sessions.`);

    } catch (err) {
        console.error('[Race] Failed to match sessions:', err);
        alert('Failed to match sessions. Check console for details.');
    }
}

async function deleteRace() {
    if (!currentRace?.race_id) {
        return;
    }

    const raceName = currentRace.name || 'this race';
    if (!confirm(`Delete "${raceName}"? This cannot be undone.`)) {
        return;
    }

    try {
        const resp = await fetch(`${API_BASE}/api/races/${currentRace.race_id}`, {
            method: 'DELETE',
        });

        if (!resp.ok) {
            const errorText = await resp.text();
            throw new Error(`HTTP ${resp.status}: ${errorText}`);
        }

        console.log('[Race] Deleted race:', currentRace.race_id);

        // Close modal
        closeRaceModal();

        // Clear current race state
        const regattaId = currentRace.regatta_id;
        const raceDate = currentRace.date;
        currentRace = null;
        raceData = null;

        // Clear map and UI
        clearBoatLayers();
        document.getElementById('leaderboard').innerHTML = '<div class="leaderboard-empty">Select a race to view standings</div>';
        document.getElementById('race-name').textContent = 'No race selected';
        document.getElementById('race-time').textContent = '';
        document.getElementById('btn-edit-race').disabled = true;

        // Reload race days and races for current regatta
        if (regattaId) {
            await loadRaceDays(regattaId);
            if (raceDate) {
                document.getElementById('raceday-select').value = raceDate;
                loadRacesForDay(raceDate);
            }
        }

        // Reset race selector
        document.getElementById('race-select').value = '';

    } catch (err) {
        console.error('[Race] Failed to delete race:', err);
        alert(`Failed to delete race: ${err.message}`);
    }
}

// --- Course Editor ---

let editCourseMode = false;
let courseDraft = null;
let courseEditLayer = null;
let courseViewLayer = null;
let markEditors = {};
let lineEditors = {};

const MARK_TYPE_COLORS = {
    windward: '#f4212e',
    leeward: '#00ba7c',
    gate_port: '#a855f7',
    gate_stbd: '#f59e0b',
    offset: '#22d3ee',
    custom: '#ffffff',
};
const MARK_TYPES = ['windward', 'leeward', 'gate_port', 'gate_stbd', 'offset', 'custom'];

// Human-readable label per mark type. Shown in the editor dropdown so it
// reads as plain English rather than internal jargon.
const MARK_TYPE_LABELS = {
    windward:   'Windward (top mark)',
    leeward:    'Leeward (bottom mark)',
    gate_port:  'Leeward gate · port (left)',
    gate_stbd:  'Leeward gate · stbd (right)',
    offset:     'Offset (small mark below windward)',
    custom:     'Custom',
};
const LINE_COLORS = { start_line: '#22d3ee', finish_line: '#f4212e' };

function markTypeColor(type) {
    return MARK_TYPE_COLORS[type] || '#ffffff';
}

function markIcon(type, editable = false) {
    const color = markTypeColor(type);
    const size = editable ? 22 : 14;
    const border = editable ? '3px solid #fff' : '2px solid #fff';
    const html = `<div class="course-mark-dot" style="background:${color};width:${size}px;height:${size}px;border:${border};"></div>`;
    return L.divIcon({ html, className: 'course-mark-divicon', iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
}

function lineEndIcon(kind, editable = false) {
    const color = kind === 'pin' ? '#ffd93d' : '#f97316';
    const size = editable ? 20 : 12;
    const radius = kind === 'pin' ? '50%' : '3px';
    const html = `<div class="course-line-end" style="background:${color};width:${size}px;height:${size}px;border-radius:${radius};border:2px solid #fff;"></div>`;
    return L.divIcon({ html, className: 'course-line-divicon', iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
}

function clearCourseLayers() {
    if (courseEditLayer) { map.removeLayer(courseEditLayer); courseEditLayer = null; }
    if (courseViewLayer) { map.removeLayer(courseViewLayer); courseViewLayer = null; }
    markEditors = {};
    lineEditors = {};
}

function renderCourseViewLayer(race) {
    if (!race) return;
    if (courseViewLayer) { map.removeLayer(courseViewLayer); }
    courseViewLayer = L.featureGroup().addTo(map);

    for (const kind of ['start_line', 'finish_line']) {
        const line = race[kind];
        if (!line || line.pin_lat == null) continue;
        const color = LINE_COLORS[kind];
        L.polyline([[line.pin_lat, line.pin_lon], [line.boat_lat, line.boat_lon]], {
            color, weight: 3, dashArray: '6 4', opacity: 0.85,
        }).bindTooltip(kind === 'start_line' ? 'Start' : 'Finish').addTo(courseViewLayer);
        L.marker([line.pin_lat, line.pin_lon], { icon: lineEndIcon('pin') })
            .bindTooltip(`${kind === 'start_line' ? 'Start' : 'Finish'} pin`).addTo(courseViewLayer);
        L.marker([line.boat_lat, line.boat_lon], { icon: lineEndIcon('boat') })
            .bindTooltip(`${kind === 'start_line' ? 'Start' : 'Finish'} committee`).addTo(courseViewLayer);
    }

    for (const m of (race.marks || [])) {
        L.marker([m.lat, m.lon], { icon: markIcon(m.mark_type) })
            .bindTooltip(m.name || m.mark_type, { permanent: false })
            .addTo(courseViewLayer);
    }
}

function enterCourseEditMode() {
    if (!currentRace) return;
    editCourseMode = true;
    courseDraft = {
        start_line: currentRace.start_line ? { ...currentRace.start_line } : null,
        finish_line: currentRace.finish_line ? { ...currentRace.finish_line } : null,
        marks: (currentRace.marks || []).map(m => ({ ...m })),
        course: [...(currentRace.course || [])],
    };

    if (courseViewLayer) { map.removeLayer(courseViewLayer); courseViewLayer = null; }

    document.getElementById('course-toolbar').style.display = 'flex';
    document.getElementById('mark-list').style.display = 'block';
    document.body.classList.add('course-editing');

    if (courseEditLayer) { map.removeLayer(courseEditLayer); }
    courseEditLayer = L.featureGroup().addTo(map);
    markEditors = {};
    lineEditors = {};

    if (courseDraft.start_line) renderEditableLine('start_line');
    if (courseDraft.finish_line) renderEditableLine('finish_line');
    for (const m of courseDraft.marks) renderEditableMark(m);

    renderMarkList();
}

function exitCourseEditMode() {
    editCourseMode = false;
    courseDraft = null;
    if (courseEditLayer) { map.removeLayer(courseEditLayer); courseEditLayer = null; }
    markEditors = {};
    lineEditors = {};
    document.getElementById('course-toolbar').style.display = 'none';
    document.getElementById('mark-list').style.display = 'none';
    document.body.classList.remove('course-editing');
    renderCourseViewLayer(currentRace);
}

function renderEditableLine(kind) {
    const line = courseDraft[kind];
    if (!line) return;
    if (lineEditors[kind]) {
        const e = lineEditors[kind];
        map.removeLayer(e.pinMarker);
        map.removeLayer(e.boatMarker);
        map.removeLayer(e.polyline);
    }
    const color = LINE_COLORS[kind];
    const pinMarker = L.marker([line.pin_lat, line.pin_lon], {
        icon: lineEndIcon('pin', true), draggable: true,
    }).bindTooltip(`${kind === 'start_line' ? 'Start' : 'Finish'} pin`, { permanent: true, direction: 'right', offset: [10, 0] }).addTo(courseEditLayer);
    const boatMarker = L.marker([line.boat_lat, line.boat_lon], {
        icon: lineEndIcon('boat', true), draggable: true,
    }).bindTooltip(`${kind === 'start_line' ? 'Start' : 'Finish'} committee`, { permanent: true, direction: 'right', offset: [10, 0] }).addTo(courseEditLayer);
    const poly = L.polyline([[line.pin_lat, line.pin_lon], [line.boat_lat, line.boat_lon]], {
        color, weight: 3, dashArray: '6 4',
    }).addTo(courseEditLayer);

    const update = () => {
        const pl = pinMarker.getLatLng();
        const bl = boatMarker.getLatLng();
        courseDraft[kind] = { pin_lat: pl.lat, pin_lon: pl.lng, boat_lat: bl.lat, boat_lon: bl.lng };
        poly.setLatLngs([[pl.lat, pl.lng], [bl.lat, bl.lng]]);
        updateLineListRow(kind);
    };
    pinMarker.on('drag', update);
    boatMarker.on('drag', update);
    lineEditors[kind] = { pinMarker, boatMarker, polyline: poly };
}

function renderEditableMark(mark) {
    const marker = L.marker([mark.lat, mark.lon], {
        icon: markIcon(mark.mark_type, true), draggable: true,
    }).bindTooltip(mark.name || mark.mark_type, { permanent: true, direction: 'right', offset: [12, 0] })
      .addTo(courseEditLayer);
    marker.on('drag', (e) => {
        const ll = e.target.getLatLng();
        mark.lat = ll.lat;
        mark.lon = ll.lng;
        updateMarkListRow(mark.mark_id);
    });
    markEditors[mark.mark_id] = marker;
}

function placeStartLine() {
    if (!courseDraft) return;
    if (courseDraft.start_line) return;
    const c = map.getCenter();
    const dLat = 25 / 111320;
    courseDraft.start_line = {
        pin_lat: c.lat - dLat, pin_lon: c.lng - 0.0004,
        boat_lat: c.lat + dLat, boat_lon: c.lng - 0.0004,
    };
    renderEditableLine('start_line');
    renderMarkList();
}

function placeFinishLine() {
    if (!courseDraft) return;
    if (courseDraft.finish_line) return;
    const c = map.getCenter();
    const dLat = 25 / 111320;
    courseDraft.finish_line = {
        pin_lat: c.lat - dLat, pin_lon: c.lng + 0.0004,
        boat_lat: c.lat + dLat, boat_lon: c.lng + 0.0004,
    };
    renderEditableLine('finish_line');
    renderMarkList();
}

function addMarkAtMapCenter() {
    if (!courseDraft) return;
    const c = map.getCenter();
    const idx = courseDraft.marks.length + 1;
    const mark = {
        mark_id: `m_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        name: `Mark ${idx}`,
        mark_type: idx % 2 === 1 ? 'windward' : 'leeward',
        lat: c.lat,
        lon: c.lng,
    };
    courseDraft.marks.push(mark);
    courseDraft.course.push(mark.mark_id);
    renderEditableMark(mark);
    renderMarkList();
}

async function autoStartLineFromTracks() {
    if (!currentRace?.race_id || !courseDraft) return;
    try {
        const resp = await fetch(`${API_BASE}/api/races/${currentRace.race_id}/auto-start-line`, { method: 'POST' });
        if (!resp.ok) { alert(`Auto start line failed: ${await resp.text()}`); return; }
        const data = await resp.json();
        courseDraft.start_line = data.start_line;
        renderEditableLine('start_line');
        renderMarkList();
        const l = data.start_line;
        map.panTo([(l.pin_lat + l.boat_lat) / 2, (l.pin_lon + l.boat_lon) / 2]);
    } catch (err) {
        console.error('[Race] Auto start line error:', err);
        alert('Auto start line failed. Check console.');
    }
}

async function autoSuggestMarksFromTracks() {
    if (!currentRace?.race_id || !courseDraft) return;
    try {
        const resp = await fetch(`${API_BASE}/api/races/${currentRace.race_id}/suggest-marks`, { method: 'POST' });
        if (!resp.ok) { alert(`Suggest marks failed: ${await resp.text()}`); return; }
        const data = await resp.json();
        if (!data.marks || data.marks.length === 0) {
            alert(`No mark roundings detected (found ${data.roundings_found || 0} course changes, ${data.clusters_found || 0} clusters).`);
            return;
        }
        for (const m of data.marks) {
            const mark = {
                mark_id: `m_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
                name: m.name,
                mark_type: m.mark_type,
                lat: m.lat,
                lon: m.lon,
            };
            courseDraft.marks.push(mark);
            courseDraft.course.push(mark.mark_id);
            renderEditableMark(mark);
        }
        renderMarkList();
    } catch (err) {
        console.error('[Race] Suggest marks error:', err);
        alert('Suggest marks failed. Check console.');
    }
}

function deleteMark(markId) {
    if (!courseDraft) return;
    courseDraft.marks = courseDraft.marks.filter(m => m.mark_id !== markId);
    courseDraft.course = courseDraft.course.filter(id => id !== markId);
    if (markEditors[markId]) {
        map.removeLayer(markEditors[markId]);
        delete markEditors[markId];
    }
    renderMarkList();
}

function clearLine(kind) {
    if (!courseDraft) return;
    courseDraft[kind] = null;
    if (lineEditors[kind]) {
        map.removeLayer(lineEditors[kind].pinMarker);
        map.removeLayer(lineEditors[kind].boatMarker);
        map.removeLayer(lineEditors[kind].polyline);
        delete lineEditors[kind];
    }
    renderMarkList();
}

function renderMarkList() {
    const el = document.getElementById('mark-list');
    if (!el || !courseDraft) return;
    const rows = [];
    if (courseDraft.start_line) rows.push(renderLineRow('start_line', 'Start Line'));
    if (courseDraft.finish_line) rows.push(renderLineRow('finish_line', 'Finish Line'));
    for (const m of courseDraft.marks) rows.push(renderMarkRow(m));
    const body = rows.length > 0 ? rows.join('') : '<div class="mark-empty">No lines or marks yet. Use the toolbar above.</div>';
    el.innerHTML = `<div class="mark-list-header"><h3>Course</h3><small>Drag on map to reposition</small></div>${body}`;

    for (const m of courseDraft.marks) {
        const row = el.querySelector(`[data-mark-id="${m.mark_id}"]`);
        if (!row) continue;
        row.querySelector('[data-field="name"]')?.addEventListener('input', (e) => {
            m.name = e.target.value;
            const marker = markEditors[m.mark_id];
            if (marker) marker.setTooltipContent(m.name || m.mark_type);
        });
        row.querySelector('[data-field="type"]')?.addEventListener('change', (e) => {
            m.mark_type = e.target.value;
            const marker = markEditors[m.mark_id];
            if (marker) marker.setIcon(markIcon(m.mark_type, true));
            row.querySelector('.mark-swatch').style.background = markTypeColor(m.mark_type);
        });
        row.querySelector('[data-action="delete"]')?.addEventListener('click', () => deleteMark(m.mark_id));
    }
    for (const kind of ['start_line', 'finish_line']) {
        const lineRow = el.querySelector(`[data-line="${kind}"]`);
        if (!lineRow) continue;
        lineRow.querySelector('[data-action="delete"]')?.addEventListener('click', () => clearLine(kind));
    }
}

function renderLineRow(kind, label) {
    const line = courseDraft[kind];
    const color = LINE_COLORS[kind];
    return `
        <div class="mark-row line-row" data-line="${kind}">
            <span class="mark-swatch" style="background:${color}"></span>
            <div class="mark-fields">
                <strong>${label}</strong>
                <small class="line-coords">Pin ${line.pin_lat.toFixed(5)}, ${line.pin_lon.toFixed(5)} · Boat ${line.boat_lat.toFixed(5)}, ${line.boat_lon.toFixed(5)}</small>
            </div>
            <button class="btn-mark-delete" data-action="delete" title="Remove line">✕</button>
        </div>
    `;
}

function renderMarkRow(mark) {
    const opts = MARK_TYPES.map(t =>
        `<option value="${t}" ${t === mark.mark_type ? 'selected' : ''}>${MARK_TYPE_LABELS[t] || t}</option>`
    ).join('');
    const color = markTypeColor(mark.mark_type);
    return `
        <div class="mark-row" data-mark-id="${mark.mark_id}">
            <span class="mark-swatch" style="background:${color}"></span>
            <div class="mark-fields">
                <input type="text" data-field="name" value="${mark.name || ''}" placeholder="Name">
                <select data-field="type">${opts}</select>
                <small class="mark-coords">${mark.lat.toFixed(5)}, ${mark.lon.toFixed(5)}</small>
            </div>
            <button class="btn-mark-delete" data-action="delete" title="Remove mark">✕</button>
        </div>
    `;
}

function updateMarkListRow(markId) {
    const m = courseDraft?.marks.find(x => x.mark_id === markId);
    if (!m) return;
    const el = document.querySelector(`[data-mark-id="${markId}"] .mark-coords`);
    if (el) el.textContent = `${m.lat.toFixed(5)}, ${m.lon.toFixed(5)}`;
}

function updateLineListRow(kind) {
    const line = courseDraft?.[kind];
    if (!line) return;
    const el = document.querySelector(`[data-line="${kind}"] .line-coords`);
    if (el) el.textContent = `Pin ${line.pin_lat.toFixed(5)}, ${line.pin_lon.toFixed(5)} · Boat ${line.boat_lat.toFixed(5)}, ${line.boat_lon.toFixed(5)}`;
}

async function saveCourseDraft() {
    if (!currentRace?.race_id || !courseDraft) return;
    try {
        const body = {
            start_line: courseDraft.start_line,
            finish_line: courseDraft.finish_line,
            marks: courseDraft.marks,
            course: courseDraft.course,
        };
        const resp = await fetch(`${API_BASE}/api/races/${currentRace.race_id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
        currentRace = await resp.json();
        exitCourseEditMode();
    } catch (err) {
        console.error('[Race] Failed to save course:', err);
        alert(`Failed to save course: ${err.message}`);
    }
}

// --- Event Listeners ---

function setupEventListeners() {
    // Regatta selection -> load race days
    document.getElementById('regatta-select').addEventListener('change', (e) => {
        loadRaceDays(e.target.value || null);
    });

    // Race day selection -> load races for that day
    document.getElementById('raceday-select').addEventListener('change', (e) => {
        loadRacesForDay(e.target.value || null);
    });

    // Race selection -> load race data
    document.getElementById('race-select').addEventListener('change', (e) => {
        if (e.target.value) {
            loadRaceData(e.target.value);
        }
    });

    // New race button
    document.getElementById('btn-new-race').addEventListener('click', () => {
        currentRace = null;
        openRaceModal();
    });

    // Edit race button
    document.getElementById('btn-edit-race').addEventListener('click', () => {
        if (currentRace) {
            openRaceModal(currentRace);
        }
    });

    // Edit course button (toggles on-map editing)
    const btnEditCourse = document.getElementById('btn-edit-course');
    if (btnEditCourse) {
        btnEditCourse.addEventListener('click', () => {
            if (!currentRace) return;
            if (editCourseMode) exitCourseEditMode();
            else enterCourseEditMode();
        });
    }

    // Course editor toolbar
    document.getElementById('btn-course-start-line')?.addEventListener('click', placeStartLine);
    document.getElementById('btn-course-finish-line')?.addEventListener('click', placeFinishLine);
    document.getElementById('btn-course-add-mark')?.addEventListener('click', addMarkAtMapCenter);
    document.getElementById('btn-course-auto-start')?.addEventListener('click', autoStartLineFromTracks);
    document.getElementById('btn-course-auto-marks')?.addEventListener('click', autoSuggestMarksFromTracks);
    document.getElementById('btn-course-done')?.addEventListener('click', saveCourseDraft);
    document.getElementById('btn-course-cancel')?.addEventListener('click', () => exitCourseEditMode());

    // Modal controls
    document.getElementById('modal-close').addEventListener('click', closeRaceModal);
    document.getElementById('btn-cancel').addEventListener('click', closeRaceModal);
    document.getElementById('btn-save-race').addEventListener('click', saveRace);
    document.getElementById('btn-match-sessions').addEventListener('click', matchSessions);
    document.getElementById('btn-delete-race').addEventListener('click', deleteRace);

    // Close modal on backdrop click
    document.querySelector('.modal-backdrop').addEventListener('click', closeRaceModal);

    // Map expand button
    const btnExpand = document.getElementById('btn-expand-map');
    const mapPanel = document.getElementById('map-panel');
    if (btnExpand && mapPanel) {
        btnExpand.addEventListener('click', () => {
            mapPanel.classList.toggle('expanded');
            document.body.classList.toggle('map-expanded');
            // Trigger map resize after expansion
            setTimeout(() => {
                if (map) {
                    map.invalidateSize();
                }
            }, 350);
        });
    }

    // Playback controls
    setupPlaybackControls();
}
