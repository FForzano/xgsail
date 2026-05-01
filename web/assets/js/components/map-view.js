/**
 * MapView - GPS track visualization with Leaflet
 * Includes NOAA buoy markers with time-synced wind data
 */
class MapView {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.map = null;
        this.trackLayer = null;
        this.positionMarker = null;
        this.data = [];
        this.dataIndex = {};

        // PPK data
        this.ppkData = [];
        this.ppkDataIndex = {};
        this.ppkTrackLayer = null;
        this.ppkVisible = false;
        this.gpsVisible = true;

        // 10Hz GPS data
        this.gps10HzData = [];
        this.gps10HzDataIndex = {};
        this.gps10HzTrackLayer = null;
        this.gps10HzVisible = false;

        // Buoy data
        this.buoys = [];
        this.buoyData = {};
        this.buoyMarkers = {};
        this.currentTime = null;

        // Wind data for overlay
        this.windData = [];
        this.windDataIndex = {};

        this._init();
        this._setupTimeSync();
        this._initWindOverlay();
    }

    _init() {
        // Initialize Leaflet map
        this.map = L.map(this.container, {
            center: [42.35, -71.05], // Boston Harbor default
            zoom: 13,
            zoomControl: true,
            maxZoom: 20  // Allow deep zoom regardless of tile layer limits
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
                attribution: '&copy; OpenStreetMap &copy; CartoDB',
                maxZoom: 19
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

        // Overlay layers
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

        // Add default layer (NOAA Charts)
        baseLayers['NOAA Charts'].addTo(this.map);

        // Add layer control
        L.control.layers(baseLayers, overlayLayers, {
            position: 'topright',
            collapsed: true,
        }).addTo(this.map);

        // Track polyline (interactive for click-to-seek)
        this.trackLayer = L.polyline([], {
            color: '#1d9bf0',
            weight: 3,
            opacity: 0.8,
            interactive: true
        }).addTo(this.map);

        // PPK track polyline (orange, initially hidden)
        this.ppkTrackLayer = L.polyline([], {
            color: '#f59e0b',
            weight: 3,
            opacity: 0.9,
            interactive: true
        });
        // Not added to map until toggled on

        // 10Hz GPS track polyline (cyan, initially hidden)
        this.gps10HzTrackLayer = L.polyline([], {
            color: '#22d3ee',
            weight: 2,
            opacity: 0.8,
            interactive: true
        });
        // Not added to map until toggled on

        // Click on track to jump timeline
        this.trackLayer.on('click', (e) => this._handleTrackClick(e));
        this.trackLayer.on('mouseover', () => {
            this.map.getContainer().style.cursor = 'crosshair';
        });
        this.trackLayer.on('mouseout', () => {
            this.map.getContainer().style.cursor = '';
        });

        // Click on 10Hz track to jump timeline (using 10Hz data for more precise seeking)
        this.gps10HzTrackLayer.on('click', (e) => this._handleTrack10HzClick(e));
        this.gps10HzTrackLayer.on('mouseover', () => {
            this.map.getContainer().style.cursor = 'crosshair';
        });
        this.gps10HzTrackLayer.on('mouseout', () => {
            this.map.getContainer().style.cursor = '';
        });

        // Boat position marker
        const boatIcon = L.divIcon({
            className: 'boat-marker',
            html: `<svg viewBox="0 0 24 24" width="24" height="24">
                <path fill="#00ba7c" d="M12 2L4 22h16L12 2z"/>
            </svg>`,
            iconSize: [24, 24],
            iconAnchor: [12, 12]
        });

        this.positionMarker = L.marker([0, 0], {
            icon: boatIcon,
            rotationOrigin: 'center center'
        }).addTo(this.map);

        // Add marker rotation support
        this._addMarkerRotation();
    }

    _addMarkerRotation() {
        // Rotation support that preserves Leaflet's translate transform
        const marker = this.positionMarker;
        marker._rotationAngle = 0;

        marker.setRotation = function(angle) {
            this._rotationAngle = angle;
            const icon = this.getElement();
            if (icon) {
                // Find the SVG inside and rotate only that, not the container
                const svg = icon.querySelector('svg');
                if (svg) {
                    svg.style.transform = `rotate(${angle}deg)`;
                    svg.style.transformOrigin = 'center center';
                }
            }
        };
    }

    _setupTimeSync() {
        window.timeController.addEventListener('time-change', (e) => {
            this.updatePosition(e.detail.time);
            this.currentTime = e.detail.time;
            this._updateBuoyMarkers();
        });
    }

    /**
     * Create wind arrow SVG for buoy marker
     * Wind direction is meteorological (where wind comes FROM), so add 180° to show where it's blowing TO
     */
    _createWindArrowSvg(dir, speed, color) {
        const rotation = dir != null ? (dir + 180) % 360 : 0;
        const opacity = speed ? 1 : 0.3;
        const speedText = speed ? Math.round(speed) : '?';
        return `
            <svg width="32" height="32" viewBox="0 0 32 32" style="transform: rotate(${rotation}deg)">
                <circle cx="16" cy="16" r="14" fill="${color}" fill-opacity="0.2" stroke="${color}" stroke-width="2"/>
                <polygon points="16,4 20,16 16,13 12,16" fill="${color}" fill-opacity="${opacity}"/>
                <text x="16" y="26" text-anchor="middle" fill="white" font-size="8" font-weight="bold">${speedText}</text>
            </svg>
        `;
    }

    /**
     * Interpolate buoy value at current time
     */
    _interpolateBuoyValue(dataPoints, targetTs, field) {
        if (!dataPoints || dataPoints.length === 0) return null;

        let before = null;
        let after = null;

        for (const p of dataPoints) {
            if (p.unix_ts <= targetTs) before = p;
            else if (!after) after = p;
        }

        if (!before && !after) return null;
        if (!before) return after[field];
        if (!after) return before[field];
        if (!(field in before) || !(field in after)) return before[field] || after[field];

        const ratio = (targetTs - before.unix_ts) / (after.unix_ts - before.unix_ts);
        return before[field] + ratio * (after[field] - before[field]);
    }

    /**
     * Set buoy metadata and data
     */
    setBuoyData(buoyData) {
        this.buoyData = buoyData || {};
        console.log('[MapView] setBuoyData called with', Object.keys(this.buoyData).length, 'buoys');

        // Create/update markers for each buoy
        for (const [stationId, buoy] of Object.entries(this.buoyData)) {
            if (!buoy.lat || !buoy.lon) continue;

            // Get initial values from first data point
            const dataPoints = buoy.data_points || [];
            const firstPoint = dataPoints[0] || {};
            const windDir = firstPoint.wind_dir;
            const windSpeed = firstPoint.wind_speed_kts;

            console.log(`[MapView] Creating buoy marker: ${stationId} at [${buoy.lat}, ${buoy.lon}], wind=${windDir}° @ ${windSpeed}kt`);

            const icon = L.divIcon({
                html: this._createWindArrowSvg(windDir, windSpeed, buoy.color || '#888'),
                iconSize: [32, 32],
                iconAnchor: [16, 16],
                className: 'buoy-marker'
            });

            if (this.buoyMarkers[stationId]) {
                // Update existing marker
                this.buoyMarkers[stationId].setIcon(icon);
            } else {
                // Create new marker
                const marker = L.marker([buoy.lat, buoy.lon], { icon })
                    .addTo(this.map);
                this.buoyMarkers[stationId] = marker;
            }
        }

        // Update markers with current time if available
        if (this.currentTime) {
            this._updateBuoyMarkers();
        }
    }

    /**
     * Update buoy markers with interpolated values at current time
     */
    _updateBuoyMarkers() {
        if (!this.currentTime) return;

        const targetTs = this.currentTime.getTime() / 1000;

        for (const [stationId, buoy] of Object.entries(this.buoyData)) {
            const marker = this.buoyMarkers[stationId];
            if (!marker) continue;

            const dataPoints = buoy.data_points || [];

            // Interpolate values
            const windDir = this._interpolateBuoyValue(dataPoints, targetTs, 'wind_dir');
            const windSpeed = this._interpolateBuoyValue(dataPoints, targetTs, 'wind_speed_kts');
            const windGust = this._interpolateBuoyValue(dataPoints, targetTs, 'wind_gust_kts');
            const pressure = this._interpolateBuoyValue(dataPoints, targetTs, 'pressure_hpa');
            const airTemp = this._interpolateBuoyValue(dataPoints, targetTs, 'air_temp_c');
            const waterTemp = this._interpolateBuoyValue(dataPoints, targetTs, 'water_temp_c');
            const waveHeight = this._interpolateBuoyValue(dataPoints, targetTs, 'wave_height_m');

            // Update marker icon with wind arrow
            const icon = L.divIcon({
                html: this._createWindArrowSvg(windDir, windSpeed, buoy.color || '#888'),
                iconSize: [32, 32],
                iconAnchor: [16, 16],
                className: 'buoy-marker'
            });
            marker.setIcon(icon);

            // Build popup content
            let popup = `<div style="min-width: 120px">
                <b style="color: ${buoy.color}">${buoy.name}</b><br/>
                <small>${stationId}</small><hr style="margin: 4px 0"/>`;

            if (windDir != null && windSpeed != null) {
                popup += `<b>Wind:</b> ${Math.round(windDir)}° @ ${windSpeed.toFixed(1)} kt<br/>`;
            }
            if (windGust != null) {
                popup += `<b>Gust:</b> ${windGust.toFixed(1)} kt<br/>`;
            }
            if (pressure != null) {
                popup += `<b>Pressure:</b> ${pressure.toFixed(1)} hPa<br/>`;
            }
            if (airTemp != null) {
                popup += `<b>Air:</b> ${airTemp.toFixed(1)}°C<br/>`;
            }
            if (waterTemp != null) {
                popup += `<b>Water:</b> ${waterTemp.toFixed(1)}°C<br/>`;
            }
            if (waveHeight != null) {
                popup += `<b>Waves:</b> ${waveHeight.toFixed(2)} m<br/>`;
            }
            popup += '</div>';

            marker.bindPopup(popup);
        }
    }

    /**
     * Load GPS track data
     */
    setData(gpsData) {
        this.data = gpsData || [];

        // Build time index for fast lookup
        this.dataIndex = {};
        this.data.forEach((point, i) => {
            const key = point.t.substring(0, 19); // Truncate to second
            this.dataIndex[key] = i;
        });

        // Draw full track
        const latlngs = this.data.map(p => [p.lat, p.lon]);
        this.trackLayer.setLatLngs(latlngs);

        // Fit bounds
        if (latlngs.length > 0) {
            this.map.fitBounds(this.trackLayer.getBounds(), {
                padding: [50, 50]
            });
        }

        // Set initial position
        if (this.data.length > 0) {
            const first = this.data[0];
            this.positionMarker.setLatLng([first.lat, first.lon]);
            if (first.course) {
                this.positionMarker.setRotation(first.course);
            }
        }
    }

    /**
     * Load PPK track data
     */
    setPPKData(ppkData) {
        this.ppkData = ppkData || [];

        // Build time index
        this.ppkDataIndex = {};
        this.ppkData.forEach((point, i) => {
            const key = point.t.substring(0, 19);
            this.ppkDataIndex[key] = i;
        });

        // Filter to only fix (Q=1) and float (Q=2) quality points
        // Single (Q=5) solutions can have 2-30m errors and cause wild outliers
        const goodPoints = this.ppkData.filter(p => p.quality === 1 || p.quality === 2);
        const latlngs = goodPoints.map(p => [p.lat, p.lon]);
        this.ppkTrackLayer.setLatLngs(latlngs);

        // Update toggle buttons with data info
        this._updateTrackToggles();
    }

    /**
     * Load 10Hz GPS track data
     */
    setGPS10HzData(gps10HzData) {
        this.gps10HzData = gps10HzData || [];

        // Build time index
        this.gps10HzDataIndex = {};
        this.gps10HzData.forEach((point, i) => {
            const key = point.t.substring(0, 23); // Include milliseconds
            this.gps10HzDataIndex[key] = i;
        });

        // Draw 10Hz track
        const latlngs = this.gps10HzData.map(p => [p.lat, p.lon]);
        this.gps10HzTrackLayer.setLatLngs(latlngs);

        console.log(`[MapView] setGPS10HzData: ${this.gps10HzData.length} points`);

        // Update toggle buttons with data info
        this._updateTrackToggles();
    }

    /**
     * Toggle GPS track visibility
     */
    toggleGPS(visible) {
        this.gpsVisible = visible;
        if (visible) {
            if (!this.map.hasLayer(this.trackLayer)) this.trackLayer.addTo(this.map);
        } else {
            if (this.map.hasLayer(this.trackLayer)) this.map.removeLayer(this.trackLayer);
        }
    }

    /**
     * Toggle PPK track visibility
     */
    togglePPK(visible) {
        this.ppkVisible = visible;
        if (visible) {
            if (!this.map.hasLayer(this.ppkTrackLayer)) this.ppkTrackLayer.addTo(this.map);
        } else {
            if (this.map.hasLayer(this.ppkTrackLayer)) this.map.removeLayer(this.ppkTrackLayer);
        }
    }

    /**
     * Toggle 10Hz GPS track visibility
     */
    toggleGPS10Hz(visible) {
        this.gps10HzVisible = visible;
        if (visible) {
            if (!this.map.hasLayer(this.gps10HzTrackLayer)) this.gps10HzTrackLayer.addTo(this.map);
        } else {
            if (this.map.hasLayer(this.gps10HzTrackLayer)) this.map.removeLayer(this.gps10HzTrackLayer);
        }
    }

    /**
     * Update track toggle buttons with accuracy info
     */
    _updateTrackToggles() {
        const gpsToggle = document.getElementById('toggle-gps-track');
        const gps10hzToggle = document.getElementById('toggle-gps10hz-track');
        const ppkToggle = document.getElementById('toggle-ppk-track');

        if (gpsToggle) {
            const count = this.data.length;
            gpsToggle.title = `GNSS 1Hz: ${count} pts, ~2-5m accuracy`;
        }

        // 10Hz GPS toggle
        if (gps10hzToggle && this.gps10HzData.length > 0) {
            const total = this.gps10HzData.length;
            gps10hzToggle.title = `GNSS 10Hz: ${total} pts, ~2-5m accuracy`;
            gps10hzToggle.disabled = false;
            gps10hzToggle.classList.remove('disabled');
        } else if (gps10hzToggle) {
            gps10hzToggle.title = 'GNSS 10Hz: no data';
            gps10hzToggle.disabled = true;
            gps10hzToggle.classList.add('disabled');
        }

        // PPK toggle
        if (ppkToggle && this.ppkData.length > 0) {
            const fixPts = this.ppkData.filter(p => p.quality === 1).length;
            const floatPts = this.ppkData.filter(p => p.quality === 2).length;
            const singlePts = this.ppkData.filter(p => p.quality !== 1 && p.quality !== 2).length;
            const goodPts = fixPts + floatPts;

            // Calculate accuracy only from good points
            const goodPoints = this.ppkData.filter(p => p.quality === 1 || p.quality === 2);
            const avgSdn = goodPoints.length > 0 ? goodPoints.reduce((s, p) => s + (p.sdn || 0), 0) / goodPoints.length : 0;
            const avgSde = goodPoints.length > 0 ? goodPoints.reduce((s, p) => s + (p.sde || 0), 0) / goodPoints.length : 0;
            const hAcc = Math.sqrt(avgSdn * avgSdn + avgSde * avgSde);

            let label = `GNSS PPK: ${goodPts} pts shown`;
            if (fixPts > 0) label += `, ${fixPts} fix`;
            if (floatPts > 0) label += `, ${floatPts} float`;
            if (singlePts > 0) label += ` (${singlePts} single hidden)`;
            if (hAcc > 0 && hAcc < 1) label += `, ~${(hAcc * 100).toFixed(1)}cm`;
            else if (hAcc >= 1) label += `, ~${hAcc.toFixed(1)}m`;

            ppkToggle.title = label;
            ppkToggle.disabled = false;
            ppkToggle.classList.remove('disabled');

            // Auto-show PPK if available
            ppkToggle.classList.add('active');
            this.togglePPK(true);
        } else if (ppkToggle) {
            ppkToggle.title = 'GNSS PPK 1Hz: no data';
            ppkToggle.disabled = true;
            ppkToggle.classList.add('disabled');
        }
    }

    /**
     * Update position based on current time
     */
    updatePosition(time) {
        if (!time || this.data.length === 0) return;

        const point = this._findClosestPoint(time);
        if (!point) return;

        this.positionMarker.setLatLng([point.lat, point.lon]);

        if (point.course !== undefined) {
            this.positionMarker.setRotation(point.course);
        }

        // Update stats display
        const speedEl = document.getElementById('stat-speed');
        const courseEl = document.getElementById('stat-course');
        const gpsFixEl = document.getElementById('stat-gps-fix');
        const ppkQualityEl = document.getElementById('stat-ppk-quality');

        if (speedEl) speedEl.textContent = point.speed_kn?.toFixed(1) || '--';
        if (courseEl) courseEl.textContent = point.course?.toFixed(0) || '--';

        // GPS fix type labels
        if (gpsFixEl) {
            const fixLabels = ['None', 'GPS', 'DGPS', 'PPS', 'RTK', 'Float', 'DR'];
            gpsFixEl.textContent = fixLabels[point.fix] || '--';
        }

        // PPK quality - look up by timestamp
        if (ppkQualityEl) {
            const timeKey = point.t?.substring(0, 19);
            const ppkIdx = this.ppkDataIndex[timeKey];
            if (ppkIdx !== undefined && this.ppkData[ppkIdx]) {
                const quality = this.ppkData[ppkIdx].quality;
                const ppkLabels = { 1: 'Fix', 2: 'Float', 3: 'SBAS', 4: 'DGPS', 5: 'Single', 6: 'PPP' };
                ppkQualityEl.textContent = ppkLabels[quality] || '--';
            } else {
                ppkQualityEl.textContent = '--';
            }
        }

        // Update wind overlay
        this._updateWindOverlay(time, point);
    }

    /**
     * Handle click on track polyline - seek timeline to clicked position
     */
    _handleTrackClick(e) {
        if (this.data.length === 0) return;

        const clickLatLng = e.latlng;
        let minDist = Infinity;
        let closest = null;

        for (const point of this.data) {
            const dist = clickLatLng.distanceTo(L.latLng(point.lat, point.lon));
            if (dist < minDist) {
                minDist = dist;
                closest = point;
            }
        }

        if (closest && closest.t) {
            window.timeController.seek(new Date(closest.t));
        }
    }

    /**
     * Handle click on 10Hz track polyline - seek timeline with higher precision
     */
    _handleTrack10HzClick(e) {
        if (this.gps10HzData.length === 0) return;

        const clickLatLng = e.latlng;
        let minDist = Infinity;
        let closest = null;

        for (const point of this.gps10HzData) {
            const dist = clickLatLng.distanceTo(L.latLng(point.lat, point.lon));
            if (dist < minDist) {
                minDist = dist;
                closest = point;
            }
        }

        if (closest && closest.t) {
            window.timeController.seek(new Date(closest.t));
        }
    }

    /**
     * Find closest data point to given time
     */
    _findClosestPoint(time) {
        const timeStr = time.toISOString().substring(0, 19);

        // Try exact match first
        if (this.dataIndex[timeStr] !== undefined) {
            return this.data[this.dataIndex[timeStr]];
        }

        // Binary search for closest
        const targetMs = time.getTime();
        let low = 0;
        let high = this.data.length - 1;

        while (low < high) {
            const mid = Math.floor((low + high) / 2);
            const midTime = new Date(this.data[mid].t).getTime();

            if (midTime < targetMs) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }

        return this.data[low] || this.data[this.data.length - 1];
    }

    /**
     * Initialize wind overlay arrows
     */
    _initWindOverlay() {
        const apparentArrow = document.getElementById('wind-arrow-apparent');
        const trueArrow = document.getElementById('wind-arrow-true');

        if (apparentArrow) {
            apparentArrow.innerHTML = this._createWindArrowSvgForBoat('#f4212e');
        }
        if (trueArrow) {
            trueArrow.innerHTML = this._createWindArrowSvgForBoat('#22d3ee');
        }
    }

    /**
     * Create wind arrow SVG for boat overlay (points where wind is going TO)
     */
    _createWindArrowSvgForBoat(color) {
        return `
            <svg viewBox="0 0 40 40" style="transform: rotate(0deg)">
                <circle cx="20" cy="20" r="18" fill="none" stroke="${color}" stroke-width="2" opacity="0.3"/>
                <polygon points="20,4 26,20 20,16 14,20" fill="${color}"/>
            </svg>
        `;
    }

    /**
     * Set wind data for the session
     */
    setWindData(windData) {
        this.windData = windData || [];

        // Build time index for fast lookup
        this.windDataIndex = {};
        this.windData.forEach((point, i) => {
            const key = point.t.substring(0, 19);
            this.windDataIndex[key] = i;
        });

        console.log('[MapView] setWindData called with', this.windData.length, 'points');
    }

    /**
     * Find closest wind data point to given time
     */
    _findClosestWindPoint(time) {
        if (this.windData.length === 0) return null;

        const timeStr = time.toISOString().substring(0, 19);

        // Try exact match first
        if (this.windDataIndex[timeStr] !== undefined) {
            return this.windData[this.windDataIndex[timeStr]];
        }

        // Binary search for closest
        const targetMs = time.getTime();
        let low = 0;
        let high = this.windData.length - 1;

        while (low < high) {
            const mid = Math.floor((low + high) / 2);
            const midTime = new Date(this.windData[mid].t).getTime();

            if (midTime < targetMs) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }

        return this.windData[low] || this.windData[this.windData.length - 1];
    }

    /**
     * Update wind overlay display
     */
    _updateWindOverlay(time, gpsPoint) {
        const windPoint = this._findClosestWindPoint(time);

        // Get DOM elements
        const awaEl = document.getElementById('stat-awa');
        const awsEl = document.getElementById('stat-aws');
        const twaEl = document.getElementById('stat-twa');
        const twsEl = document.getElementById('stat-tws');
        const twdEl = document.getElementById('stat-twd');
        const apparentArrow = document.getElementById('wind-arrow-apparent');
        const trueArrow = document.getElementById('wind-arrow-true');

        if (!windPoint) {
            // No wind data
            if (awaEl) awaEl.textContent = '--';
            if (awsEl) awsEl.textContent = '--';
            if (twaEl) twaEl.textContent = '--';
            if (twsEl) twsEl.textContent = '--';
            if (twdEl) twdEl.textContent = '--';
            return;
        }

        const awa = windPoint.awa;
        const aws = windPoint.aws_kn;
        const sog = gpsPoint?.speed_kn || 0;
        const cog = gpsPoint?.course || 0;

        // Update AWA/AWS
        if (awaEl) awaEl.textContent = awa != null ? Math.round(awa) : '--';
        if (awsEl) awsEl.textContent = aws != null ? aws.toFixed(1) : '--';

        // Calculate true wind
        if (awa != null && aws != null && sog != null) {
            const awaRad = awa * Math.PI / 180;
            const awX = aws * Math.cos(awaRad) - sog;
            const awY = aws * Math.sin(awaRad);
            const tws = Math.sqrt(awX * awX + awY * awY);
            const twaRad = Math.atan2(awY, awX);
            let twa = twaRad * 180 / Math.PI;

            // Normalize TWA to -180 to +180
            if (twa > 180) twa -= 360;
            if (twa < -180) twa += 360;

            // Calculate TWD
            let twd = (cog + twa + 360) % 360;

            if (twaEl) twaEl.textContent = Math.round(twa);
            if (twsEl) twsEl.textContent = tws.toFixed(1);
            if (twdEl) twdEl.textContent = Math.round(twd);

            // Update arrow rotations
            // AWA arrow: rotate to show where apparent wind is coming FROM relative to boat
            // For display, 0° = ahead, positive = starboard
            if (apparentArrow) {
                const svg = apparentArrow.querySelector('svg');
                if (svg) {
                    // Wind arrow points where wind goes TO, so add 180° to AWA
                    const rotation = (awa + 180) % 360;
                    svg.style.transform = `rotate(${rotation}deg)`;
                }
            }

            // TWA arrow: same treatment
            if (trueArrow) {
                const svg = trueArrow.querySelector('svg');
                if (svg) {
                    // Normalize TWA for rotation (0-360 range)
                    let twaNorm = twa;
                    if (twaNorm < 0) twaNorm += 360;
                    const rotation = (twaNorm + 180) % 360;
                    svg.style.transform = `rotate(${rotation}deg)`;
                }
            }
        } else {
            if (twaEl) twaEl.textContent = '--';
            if (twsEl) twsEl.textContent = '--';
            if (twdEl) twdEl.textContent = '--';
        }
    }
}

window.MapView = MapView;
