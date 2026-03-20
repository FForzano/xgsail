/**
 * VideoPlayer - HLS video playback synchronized with timeline
 * Simplified: videos play independently, only sync on manual seek
 */
class VideoPlayer {
    constructor() {
        this.hlsInstances = {
            cockpit: null,
            sails: null
        };
        this.videoElements = {
            cockpit: document.getElementById('video-cockpit'),
            sails: document.getElementById('video-sails')
        };
        this.videoContainer = document.getElementById('video-container');
        this.streamInfo = null;
        this.videosReady = { cockpit: false, sails: false };

        this._setupControls();
    }

    _setupControls() {
        // Sync only on manual timeline scrub
        const timeline = document.getElementById('timeline');
        if (timeline) {
            timeline.addEventListener('change', () => {
                const currentTime = window.timeController.getCurrentTime();
                if (currentTime) {
                    this._seekVideos(currentTime);
                }
            });
        }

        // Play/pause with main controls
        const btnPlay = document.getElementById('btn-play');
        if (btnPlay) {
            btnPlay.addEventListener('click', () => {
                // Small delay to let TimeController state update
                setTimeout(() => {
                    if (window.timeController.isPlaying()) {
                        this._playAll();
                    } else {
                        this._pauseAll();
                    }
                }, 50);
            });
        }

        // Keyboard space bar
        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space' && e.target.tagName !== 'INPUT') {
                setTimeout(() => {
                    if (window.timeController.isPlaying()) {
                        this._playAll();
                    } else {
                        this._pauseAll();
                    }
                }, 50);
            }
        });

        // Speed changes
        const speedSelect = document.getElementById('playback-speed');
        if (speedSelect) {
            speedSelect.addEventListener('change', (e) => {
                const rate = parseFloat(e.target.value);
                this._setPlaybackRate(rate);
            });
        }
    }

    /**
     * Load video streams for a session
     */
    async loadStreams(deviceId, date) {
        try {
            const response = await fetch(`/api/video/${deviceId}/${date}`);
            if (!response.ok) {
                console.warn('No video available for this session');
                this.videoContainer.style.display = 'none';
                return;
            }

            const data = await response.json();
            this.streamInfo = data.streams;

            // Check if any streams available
            const hasStreams = Object.values(this.streamInfo).some(s => s && s.playlist_url);
            if (!hasStreams) {
                this.videoContainer.style.display = 'none';
                return;
            }

            this.videoContainer.style.display = 'flex';

            // Initialize HLS for each stream
            for (const [camera, info] of Object.entries(this.streamInfo)) {
                if (info && info.playlist_url) {
                    this._initHLS(camera, info);
                }
            }
        } catch (error) {
            console.error('Error loading video streams:', error);
            this.videoContainer.style.display = 'none';
        }
    }

    _initHLS(camera, streamInfo) {
        const video = this.videoElements[camera];
        if (!video) return;

        // Destroy existing HLS instance
        if (this.hlsInstances[camera]) {
            this.hlsInstances[camera].destroy();
        }

        this.videosReady[camera] = false;

        if (Hls.isSupported()) {
            const hls = new Hls({
                enableWorker: true,
                lowLatencyMode: false,
                // Large buffer for smooth playback
                maxBufferLength: 60,
                maxMaxBufferLength: 120,
                maxBufferSize: 120 * 1000 * 1000,
                // Stability settings
                fragLoadingTimeOut: 20000,
                manifestLoadingTimeOut: 10000,
                levelLoadingTimeOut: 10000
            });

            hls.loadSource(streamInfo.playlist_url);
            hls.attachMedia(video);

            hls.on(Hls.Events.MANIFEST_PARSED, () => {
                console.log(`HLS ready: ${camera}`);
                this.videosReady[camera] = true;

                // Initial seek to current timeline position
                const currentTime = window.timeController.getCurrentTime();
                if (currentTime && streamInfo.start_time) {
                    const streamStart = new Date(streamInfo.start_time).getTime();
                    const offsetSeconds = (currentTime.getTime() - streamStart) / 1000;
                    if (offsetSeconds >= 0 && offsetSeconds <= video.duration) {
                        video.currentTime = offsetSeconds;
                    }
                }
            });

            hls.on(Hls.Events.ERROR, (event, data) => {
                if (data.fatal) {
                    console.error(`HLS error ${camera}:`, data.type);
                    if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
                        hls.startLoad();
                    } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
                        hls.recoverMediaError();
                    }
                }
            });

            this.hlsInstances[camera] = hls;
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
            video.src = streamInfo.playlist_url;
            video.addEventListener('loadedmetadata', () => {
                this.videosReady[camera] = true;
            });
        }
    }

    _seekVideos(time) {
        if (!time || !this.streamInfo) return;

        for (const [camera, info] of Object.entries(this.streamInfo)) {
            if (!info || !info.start_time) continue;

            const video = this.videoElements[camera];
            if (!video || !this.videosReady[camera]) continue;

            const streamStart = new Date(info.start_time).getTime();
            const offsetSeconds = (time.getTime() - streamStart) / 1000;

            if (offsetSeconds >= 0 && video.duration && offsetSeconds <= video.duration) {
                video.currentTime = offsetSeconds;
            }
        }
    }

    _playAll() {
        // Sync position before playing
        const currentTime = window.timeController.getCurrentTime();
        if (currentTime) {
            this._seekVideos(currentTime);
        }

        Object.entries(this.videoElements).forEach(([camera, video]) => {
            if (video && this.videosReady[camera]) {
                video.play().catch(e => console.warn(`Play failed ${camera}:`, e.message));
            }
        });
    }

    _pauseAll() {
        Object.values(this.videoElements).forEach(video => {
            if (video) video.pause();
        });
    }

    _setPlaybackRate(rate) {
        Object.values(this.videoElements).forEach(video => {
            if (video) video.playbackRate = rate;
        });
    }

    /**
     * Cleanup
     */
    destroy() {
        Object.values(this.hlsInstances).forEach(hls => {
            if (hls) hls.destroy();
        });
        this.hlsInstances = { cockpit: null, sails: null };
    }
}

window.VideoPlayer = VideoPlayer;
