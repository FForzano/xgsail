/**
 * ChartPanel - Time-series charts with Chart.js
 */
class ChartPanel {
    constructor() {
        this.charts = {};
        this.data = {};
        this.dataIndex = {};
        this.rawData = {};  // Store raw data arrays for stats
        this.verticalLinePlugin = this._createVerticalLinePlugin();
        this.fullscreenChart = null;
        this.fullscreenOverlay = null;

        this._init();
        this._setupTimeSync();
        this._setupFullscreen();
    }

    _createVerticalLinePlugin() {
        return {
            id: 'verticalLine',
            afterDraw: (chart) => {
                if (chart.verticalLineX === undefined) return;

                const ctx = chart.ctx;
                const x = chart.verticalLineX;
                const topY = chart.chartArea.top;
                const bottomY = chart.chartArea.bottom;

                ctx.save();
                ctx.beginPath();
                ctx.moveTo(x, topY);
                ctx.lineTo(x, bottomY);
                ctx.lineWidth = 2;
                ctx.strokeStyle = '#00ba7c';
                ctx.stroke();
                ctx.restore();
            }
        };
    }

    _init() {
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#8b98a5',
                        boxWidth: 12,
                        padding: 8,
                        font: { size: 10 }
                    }
                },
                tooltip: { enabled: false }
            },
            scales: {
                x: {
                    display: false
                },
                y: {
                    ticks: { color: '#8b98a5', font: { size: 10 } },
                    grid: { color: 'rgba(47, 51, 54, 0.5)' }
                }
            },
            elements: {
                point: { radius: 0 },
                line: { borderWidth: 2 }
            }
        };

        // Attitude chart (heel/pitch)
        this.charts.attitude = new Chart(
            document.getElementById('chart-attitude'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Heel',
                            data: [],
                            borderColor: '#1d9bf0',
                            backgroundColor: 'rgba(29, 155, 240, 0.1)',
                            fill: true
                        },
                        {
                            label: 'Pitch',
                            data: [],
                            borderColor: '#ffad1f',
                            backgroundColor: 'transparent'
                        }
                    ]
                },
                options: {
                    ...chartOptions,
                    scales: {
                        ...chartOptions.scales,
                        y: {
                            ...chartOptions.scales.y,
                            min: -30,
                            max: 30
                        }
                    }
                },
                plugins: [this.verticalLinePlugin]
            }
        );

        // Wind chart
        this.charts.wind = new Chart(
            document.getElementById('chart-wind'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'AWS (kn)',
                            data: [],
                            borderColor: '#00ba7c',
                            backgroundColor: 'rgba(0, 186, 124, 0.1)',
                            fill: true,
                            yAxisID: 'y'
                        },
                        {
                            label: 'AWA',
                            data: [],
                            borderColor: '#f4212e',
                            backgroundColor: 'transparent',
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    ...chartOptions,
                    scales: {
                        x: { display: false },
                        y: {
                            position: 'left',
                            ticks: { color: '#8b98a5', font: { size: 10 } },
                            grid: { color: 'rgba(47, 51, 54, 0.5)' },
                            min: 0,
                            max: 30
                        },
                        y1: {
                            position: 'right',
                            ticks: { color: '#8b98a5', font: { size: 10 } },
                            grid: { display: false },
                            min: 0,
                            max: 180
                        }
                    }
                },
                plugins: [this.verticalLinePlugin]
            }
        );

        // Speed chart
        this.charts.speed = new Chart(
            document.getElementById('chart-speed'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'SOG (kn)',
                            data: [],
                            borderColor: '#1d9bf0',
                            backgroundColor: 'rgba(29, 155, 240, 0.1)',
                            fill: true
                        }
                    ]
                },
                options: {
                    ...chartOptions,
                    scales: {
                        ...chartOptions.scales,
                        y: {
                            ...chartOptions.scales.y,
                            min: 0
                        }
                    }
                },
                plugins: [this.verticalLinePlugin]
            }
        );

        // Pressure chart
        this.charts.pressure = new Chart(
            document.getElementById('chart-pressure'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'hPa',
                            data: [],
                            borderColor: '#9333ea',
                            backgroundColor: 'rgba(147, 51, 234, 0.1)',
                            fill: true
                        }
                    ]
                },
                options: chartOptions,
                plugins: [this.verticalLinePlugin]
            }
        );

        // Heading chart (IMU + GPS)
        this.charts.heading = new Chart(
            document.getElementById('chart-heading'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'IMU Heading',
                            data: [],
                            borderColor: '#1d9bf0',
                            backgroundColor: 'transparent'
                        },
                        {
                            label: 'GPS Course',
                            data: [],
                            borderColor: '#ffad1f',
                            backgroundColor: 'transparent'
                        }
                    ]
                },
                options: {
                    ...chartOptions,
                    scales: {
                        ...chartOptions.scales,
                        y: {
                            ...chartOptions.scales.y,
                            min: 0,
                            max: 360
                        }
                    }
                },
                plugins: [this.verticalLinePlugin]
            }
        );

        // Acceleration X/Y chart
        this.charts.accelXY = new Chart(
            document.getElementById('chart-accel-xy'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Accel X',
                            data: [],
                            borderColor: '#f4212e',
                            backgroundColor: 'transparent'
                        },
                        {
                            label: 'Accel Y',
                            data: [],
                            borderColor: '#00ba7c',
                            backgroundColor: 'transparent'
                        }
                    ]
                },
                options: {
                    ...chartOptions,
                    scales: {
                        ...chartOptions.scales,
                        y: {
                            ...chartOptions.scales.y,
                            min: -5,
                            max: 5
                        }
                    }
                },
                plugins: [this.verticalLinePlugin]
            }
        );

        // Acceleration Z chart
        this.charts.accelZ = new Chart(
            document.getElementById('chart-accel-z'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Accel Z',
                            data: [],
                            borderColor: '#1d9bf0',
                            backgroundColor: 'rgba(29, 155, 240, 0.1)',
                            fill: true
                        }
                    ]
                },
                options: {
                    ...chartOptions,
                    scales: {
                        ...chartOptions.scales,
                        y: {
                            ...chartOptions.scales.y,
                            min: 5,
                            max: 15
                        }
                    }
                },
                plugins: [this.verticalLinePlugin]
            }
        );

        // Temperature chart (pressure sensor + wind sensor)
        this.charts.temperature = new Chart(
            document.getElementById('chart-temperature'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Pressure Sensor',
                            data: [],
                            borderColor: '#9333ea',
                            backgroundColor: 'transparent'
                        },
                        {
                            label: 'Wind Sensor',
                            data: [],
                            borderColor: '#00ba7c',
                            backgroundColor: 'transparent'
                        }
                    ]
                },
                options: chartOptions,
                plugins: [this.verticalLinePlugin]
            }
        );

        // Wind compass chart
        this.charts.windCompass = new Chart(
            document.getElementById('chart-wind-compass'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Compass',
                            data: [],
                            borderColor: '#ffad1f',
                            backgroundColor: 'rgba(255, 173, 31, 0.1)',
                            fill: true
                        }
                    ]
                },
                options: {
                    ...chartOptions,
                    scales: {
                        ...chartOptions.scales,
                        y: {
                            ...chartOptions.scales.y,
                            min: 0,
                            max: 360
                        }
                    }
                },
                plugins: [this.verticalLinePlugin]
            }
        );

        // Wind meta (temp & battery)
        this.charts.windMeta = new Chart(
            document.getElementById('chart-wind-meta'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Temp (°C)',
                            data: [],
                            borderColor: '#f4212e',
                            backgroundColor: 'transparent',
                            yAxisID: 'y'
                        },
                        {
                            label: 'Battery (%)',
                            data: [],
                            borderColor: '#00ba7c',
                            backgroundColor: 'transparent',
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    ...chartOptions,
                    scales: {
                        x: { display: false },
                        y: {
                            position: 'left',
                            ticks: { color: '#8b98a5', font: { size: 10 } },
                            grid: { color: 'rgba(47, 51, 54, 0.5)' }
                        },
                        y1: {
                            position: 'right',
                            ticks: { color: '#8b98a5', font: { size: 10 } },
                            grid: { display: false },
                            min: 0,
                            max: 100
                        }
                    }
                },
                plugins: [this.verticalLinePlugin]
            }
        );
    }

    _setupTimeSync() {
        window.timeController.addEventListener('time-change', (e) => {
            this.updateCursor(e.detail.time);
            this._updateFullscreenStats(e.detail.time);
        });
    }

    _setupFullscreen() {
        // Chart metadata for fullscreen display
        this.chartMeta = {
            attitude: { title: 'Heel & Pitch', unit: '°', datasets: ['Heel', 'Pitch'] },
            wind: { title: 'Wind Speed & Angle', unit: '', datasets: ['AWS (kn)', 'AWA (°)'] },
            speed: { title: 'Speed Over Ground', unit: 'kn', datasets: ['SOG'] },
            pressure: { title: 'Barometric Pressure', unit: 'hPa', datasets: ['Pressure'] },
            heading: { title: 'Heading', unit: '°', datasets: ['IMU Heading', 'GPS Course'] },
            accelXY: { title: 'Acceleration X/Y', unit: 'm/s²', datasets: ['Accel X', 'Accel Y'] },
            accelZ: { title: 'Acceleration Z', unit: 'm/s²', datasets: ['Accel Z'] },
            temperature: { title: 'Temperature', unit: '°C', datasets: ['Pressure Sensor', 'Wind Sensor'] },
            windCompass: { title: 'Wind Compass Heading', unit: '°', datasets: ['Compass'] },
            windMeta: { title: 'Wind Sensor Status', unit: '', datasets: ['Temp (°C)', 'Battery (%)'] }
        };

        // Add click handlers to all chart boxes
        document.querySelectorAll('.chart-box').forEach(box => {
            box.addEventListener('click', (e) => {
                const canvas = box.querySelector('canvas');
                if (canvas) {
                    const chartId = canvas.id.replace('chart-', '').replace(/-/g, '');
                    // Map IDs to chart keys
                    const idMap = {
                        'attitude': 'attitude',
                        'wind': 'wind',
                        'speed': 'speed',
                        'pressure': 'pressure',
                        'heading': 'heading',
                        'accelxy': 'accelXY',
                        'accelz': 'accelZ',
                        'temperature': 'temperature',
                        'windcompass': 'windCompass',
                        'windmeta': 'windMeta'
                    };
                    const key = idMap[chartId];
                    if (key && this.charts[key]) {
                        this._openFullscreen(key);
                    }
                }
            });
        });

        // ESC to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.fullscreenOverlay) {
                this._closeFullscreen();
            }
        });
    }

    _openFullscreen(chartKey) {
        const chart = this.charts[chartKey];
        const meta = this.chartMeta[chartKey];
        if (!chart || !meta) return;

        // Create overlay
        const overlay = document.createElement('div');
        overlay.className = 'chart-fullscreen-overlay';
        overlay.innerHTML = `
            <div class="chart-fullscreen-header">
                <h2>${meta.title}</h2>
                <button class="chart-fullscreen-close">✕ Close (ESC)</button>
            </div>
            <div class="chart-fullscreen-content">
                <div class="chart-fullscreen-canvas">
                    <canvas id="fullscreen-chart"></canvas>
                </div>
                <div class="chart-fullscreen-stats" id="fullscreen-stats"></div>
            </div>
        `;
        document.body.appendChild(overlay);
        this.fullscreenOverlay = overlay;

        // Close button
        overlay.querySelector('.chart-fullscreen-close').addEventListener('click', () => {
            this._closeFullscreen();
        });

        // Click outside to close
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                this._closeFullscreen();
            }
        });

        // Create fullscreen chart
        const canvas = document.getElementById('fullscreen-chart');
        const ctx = canvas.getContext('2d');

        // Clone chart config but with larger display
        const originalConfig = chart.config;
        this.fullscreenChart = new Chart(ctx, {
            type: 'line',
            data: JSON.parse(JSON.stringify(chart.data)),
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: '#e7e9ea',
                            boxWidth: 16,
                            padding: 16,
                            font: { size: 14 }
                        }
                    },
                    tooltip: {
                        enabled: true,
                        mode: 'index',
                        intersect: false
                    }
                },
                scales: {
                    x: {
                        display: true,
                        ticks: {
                            color: '#8b98a5',
                            font: { size: 11 },
                            maxTicksLimit: 20,
                            callback: function(value, index) {
                                const label = this.getLabelForValue(value);
                                if (label) {
                                    const d = new Date(label);
                                    return d.toLocaleTimeString();
                                }
                                return '';
                            }
                        },
                        grid: { color: 'rgba(47, 51, 54, 0.5)' }
                    },
                    y: {
                        display: true,
                        ticks: {
                            color: '#8b98a5',
                            font: { size: 12 }
                        },
                        grid: { color: 'rgba(47, 51, 54, 0.5)' }
                    }
                },
                elements: {
                    point: { radius: 0 },
                    line: { borderWidth: 2 }
                }
            },
            plugins: [this.verticalLinePlugin]
        });

        // Copy scales from original if they exist
        if (originalConfig.options.scales.y1) {
            this.fullscreenChart.options.scales.y1 = {
                ...originalConfig.options.scales.y1,
                display: true,
                ticks: { color: '#8b98a5', font: { size: 12 } }
            };
        }

        this.fullscreenChartKey = chartKey;
        this._renderFullscreenStats(chartKey);

        // Sync cursor position
        const currentTime = window.timeController.getCurrentTime();
        if (currentTime) {
            this._updateFullscreenCursor(currentTime);
        }
    }

    _closeFullscreen() {
        if (this.fullscreenChart) {
            this.fullscreenChart.destroy();
            this.fullscreenChart = null;
        }
        if (this.fullscreenOverlay) {
            this.fullscreenOverlay.remove();
            this.fullscreenOverlay = null;
        }
        this.fullscreenChartKey = null;
    }

    _renderFullscreenStats(chartKey) {
        const statsContainer = document.getElementById('fullscreen-stats');
        if (!statsContainer || !this.rawData[chartKey]) return;

        const data = this.rawData[chartKey];
        const meta = this.chartMeta[chartKey];
        let html = '';

        data.forEach((dataset, i) => {
            const values = dataset.filter(v => v !== null && !isNaN(v));
            if (values.length === 0) return;

            const min = Math.min(...values).toFixed(1);
            const max = Math.max(...values).toFixed(1);
            const avg = (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1);
            const label = meta.datasets[i] || `Dataset ${i + 1}`;

            html += `
                <div class="chart-stat-group">
                    <span class="label">${label} Min</span>
                    <span class="value min">${min}</span>
                </div>
                <div class="chart-stat-group">
                    <span class="label">${label} Max</span>
                    <span class="value max">${max}</span>
                </div>
                <div class="chart-stat-group">
                    <span class="label">${label} Avg</span>
                    <span class="value avg">${avg}</span>
                </div>
            `;
        });

        // Add current value placeholder
        html += `
            <div class="chart-stat-group" id="fullscreen-current">
                <span class="label">Current</span>
                <span class="value current">--</span>
            </div>
        `;

        statsContainer.innerHTML = html;
    }

    _updateFullscreenStats(time) {
        if (!this.fullscreenChart || !this.fullscreenChartKey) return;

        const currentEl = document.getElementById('fullscreen-current');
        if (!currentEl) return;

        const timeStr = time.toISOString().substring(0, 19);
        let index = this.dataIndex[timeStr];
        if (index === undefined) {
            index = this._findClosestIndex(time);
        }

        if (index !== undefined && this.rawData[this.fullscreenChartKey]) {
            const data = this.rawData[this.fullscreenChartKey];
            const values = data.map(d => d[index]).filter(v => v !== null && !isNaN(v));
            if (values.length > 0) {
                currentEl.querySelector('.value').textContent = values.map(v => v.toFixed(1)).join(' / ');
            }
        }

        this._updateFullscreenCursor(time);
    }

    _updateFullscreenCursor(time) {
        if (!this.fullscreenChart || !this.data.labels) return;

        const timeStr = time.toISOString().substring(0, 19);
        let index = this.dataIndex[timeStr];
        if (index === undefined) {
            index = this._findClosestIndex(time);
        }

        if (index !== undefined) {
            const meta = this.fullscreenChart.getDatasetMeta(0);
            if (meta.data[index]) {
                this.fullscreenChart.verticalLineX = meta.data[index].x;
                this.fullscreenChart.draw();
            }
        }
    }

    /**
     * Load session data
     */
    setData(sessionData) {
        const data = sessionData.data || [];

        // Reset
        this.data = {};
        this.dataIndex = {};

        // Extract data arrays
        const labels = [];
        const imuHeel = [], imuPitch = [], imuHeading = [];
        const imuAccelX = [], imuAccelY = [], imuAccelZ = [];
        const windAws = [], windAwa = [], windCompass = [];
        const windTemp = [], windBattery = [];
        const gpsSpeed = [], gpsCourse = [];
        const pressure = [], pressureTemp = [];

        data.forEach((point, i) => {
            labels.push(point.t);
            this.dataIndex[point.t.substring(0, 19)] = i;

            // IMU data
            if (point.imu) {
                imuHeel.push(point.imu.heel);
                imuPitch.push(point.imu.pitch);
                imuHeading.push(point.imu.heading);
                imuAccelX.push(point.imu.accel_x);
                imuAccelY.push(point.imu.accel_y);
                imuAccelZ.push(point.imu.accel_z);
            } else {
                imuHeel.push(null);
                imuPitch.push(null);
                imuHeading.push(null);
                imuAccelX.push(null);
                imuAccelY.push(null);
                imuAccelZ.push(null);
            }

            // Wind data
            if (point.wind) {
                windAws.push(point.wind.aws_kn);
                windAwa.push(point.wind.awa);
                windCompass.push(point.wind.compass);
                windTemp.push(point.wind.temp_c);
                windBattery.push(point.wind.battery);
            } else {
                windAws.push(null);
                windAwa.push(null);
                windCompass.push(null);
                windTemp.push(null);
                windBattery.push(null);
            }

            // GPS data
            if (point.gps) {
                gpsSpeed.push(point.gps.speed_kn);
                gpsCourse.push(point.gps.course);
            } else {
                gpsSpeed.push(null);
                gpsCourse.push(null);
            }

            // Pressure data
            if (point.pressure) {
                pressure.push(point.pressure.hpa);
                pressureTemp.push(point.pressure.temp_c);
            } else {
                pressure.push(null);
                pressureTemp.push(null);
            }
        });

        this.data.labels = labels;

        // Update basic charts
        this.charts.attitude.data.labels = labels;
        this.charts.attitude.data.datasets[0].data = imuHeel;
        this.charts.attitude.data.datasets[1].data = imuPitch;
        this.charts.attitude.update('none');

        this.charts.wind.data.labels = labels;
        this.charts.wind.data.datasets[0].data = windAws;
        this.charts.wind.data.datasets[1].data = windAwa;
        this.charts.wind.update('none');

        this.charts.speed.data.labels = labels;
        this.charts.speed.data.datasets[0].data = gpsSpeed;
        this.charts.speed.update('none');

        this.charts.pressure.data.labels = labels;
        this.charts.pressure.data.datasets[0].data = pressure;
        this.charts.pressure.update('none');

        // Update new charts
        this.charts.heading.data.labels = labels;
        this.charts.heading.data.datasets[0].data = imuHeading;
        this.charts.heading.data.datasets[1].data = gpsCourse;
        this.charts.heading.update('none');

        this.charts.accelXY.data.labels = labels;
        this.charts.accelXY.data.datasets[0].data = imuAccelX;
        this.charts.accelXY.data.datasets[1].data = imuAccelY;
        this.charts.accelXY.update('none');

        this.charts.accelZ.data.labels = labels;
        this.charts.accelZ.data.datasets[0].data = imuAccelZ;
        this.charts.accelZ.update('none');

        this.charts.temperature.data.labels = labels;
        this.charts.temperature.data.datasets[0].data = pressureTemp;
        this.charts.temperature.data.datasets[1].data = windTemp;
        this.charts.temperature.update('none');

        this.charts.windCompass.data.labels = labels;
        this.charts.windCompass.data.datasets[0].data = windCompass;
        this.charts.windCompass.update('none');

        this.charts.windMeta.data.labels = labels;
        this.charts.windMeta.data.datasets[0].data = windTemp;
        this.charts.windMeta.data.datasets[1].data = windBattery;
        this.charts.windMeta.update('none');

        // Store raw data for fullscreen stats
        this.rawData = {
            attitude: [imuHeel, imuPitch],
            wind: [windAws, windAwa],
            speed: [gpsSpeed],
            pressure: [pressure],
            heading: [imuHeading, gpsCourse],
            accelXY: [imuAccelX, imuAccelY],
            accelZ: [imuAccelZ],
            temperature: [pressureTemp, windTemp],
            windCompass: [windCompass],
            windMeta: [windTemp, windBattery]
        };
    }

    /**
     * Update cursor position on all charts
     */
    updateCursor(time) {
        if (!time || !this.data.labels) return;

        const timeStr = time.toISOString().substring(0, 19);
        let index = this.dataIndex[timeStr];

        if (index === undefined) {
            // Find closest
            index = this._findClosestIndex(time);
        }

        if (index === undefined) return;

        // Update vertical line on each chart
        Object.values(this.charts).forEach(chart => {
            const meta = chart.getDatasetMeta(0);
            if (meta.data[index]) {
                chart.verticalLineX = meta.data[index].x;
                chart.draw();
            }
        });
    }

    _findClosestIndex(time) {
        if (!this.data.labels || this.data.labels.length === 0) return undefined;

        const targetMs = time.getTime();
        let closest = 0;
        let minDiff = Infinity;

        this.data.labels.forEach((label, i) => {
            const diff = Math.abs(new Date(label).getTime() - targetMs);
            if (diff < minDiff) {
                minDiff = diff;
                closest = i;
            }
        });

        return closest;
    }
}

window.ChartPanel = ChartPanel;
