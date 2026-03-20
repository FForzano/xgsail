/**
 * Timeline - Playback controls and scrubber
 */
class Timeline {
    constructor() {
        this.slider = document.getElementById('timeline');
        this.btnPlay = document.getElementById('btn-play');
        this.speedSelect = document.getElementById('playback-speed');
        this.timeCurrent = document.getElementById('time-current');
        this.timeDuration = document.getElementById('time-duration');
        this.timeAbsolute = document.getElementById('time-absolute');

        this._setupControls();
        this._setupTimeSync();
        this._setupMapCollapse();
    }

    _setupControls() {
        // Play/pause button
        this.btnPlay.addEventListener('click', () => {
            window.timeController.toggle();
        });

        // Speed selector
        this.speedSelect.addEventListener('change', (e) => {
            const rate = parseFloat(e.target.value);
            window.timeController.setPlaybackRate(rate);

            // Also update video playback rate
            if (window.videoPlayer) {
                window.videoPlayer.setPlaybackRate(rate);
            }
        });

        // Timeline scrubber
        this.slider.addEventListener('input', (e) => {
            const position = parseFloat(e.target.value) / 100;
            window.timeController.seekToPosition(position);
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

            switch (e.code) {
                case 'Space':
                    e.preventDefault();
                    window.timeController.toggle();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    this._seekRelative(-5000); // -5 seconds
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    this._seekRelative(5000); // +5 seconds
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    this._changeSpeed(1);
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    this._changeSpeed(-1);
                    break;
            }
        });
    }

    _setupTimeSync() {
        window.timeController.addEventListener('session-loaded', (e) => {
            this.timeDuration.textContent = this._formatDuration(e.detail.duration);
            this.slider.value = 0;
        });

        window.timeController.addEventListener('time-change', (e) => {
            // Update slider position
            this.slider.value = e.detail.position * 100;

            // Update current time display (elapsed)
            this.timeCurrent.textContent = this._formatDuration(e.detail.elapsed);

            // Update absolute time display
            if (e.detail.time && this.timeAbsolute) {
                this.timeAbsolute.textContent = this._formatAbsoluteTime(e.detail.time);
            }
        });

        window.timeController.addEventListener('play', () => {
            this._updatePlayButton(true);
        });

        window.timeController.addEventListener('pause', () => {
            this._updatePlayButton(false);
        });
    }

    _updatePlayButton(isPlaying) {
        const iconPlay = this.btnPlay.querySelector('.icon-play');
        const iconPause = this.btnPlay.querySelector('.icon-pause');

        if (isPlaying) {
            iconPlay.style.display = 'none';
            iconPause.style.display = 'inline';
        } else {
            iconPlay.style.display = 'inline';
            iconPause.style.display = 'none';
        }
    }

    _seekRelative(deltaMs) {
        const current = window.timeController.getCurrentTime();
        if (current) {
            window.timeController.seek(new Date(current.getTime() + deltaMs));
        }
    }

    _changeSpeed(direction) {
        const options = Array.from(this.speedSelect.options);
        const currentIndex = this.speedSelect.selectedIndex;
        const newIndex = Math.max(0, Math.min(options.length - 1, currentIndex + direction));

        if (newIndex !== currentIndex) {
            this.speedSelect.selectedIndex = newIndex;
            this.speedSelect.dispatchEvent(new Event('change'));
        }
    }

    _formatDuration(ms) {
        const totalSeconds = Math.floor(ms / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;

        const pad = (n) => n.toString().padStart(2, '0');

        if (hours > 0) {
            return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
        }
        return `${pad(minutes)}:${pad(seconds)}`;
    }

    _formatAbsoluteTime(date) {
        if (!date) return '--:--:--';
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        const seconds = date.getSeconds().toString().padStart(2, '0');
        return `${hours}:${minutes}:${seconds}`;
    }

    _setupMapCollapse() {
        const mapPanel = document.getElementById('map-panel');
        const btnCollapse = document.getElementById('btn-collapse-map');
        const resizeHandle = document.getElementById('map-resize-handle');

        if (!mapPanel || !btnCollapse) return;

        // Toggle collapse
        btnCollapse.addEventListener('click', () => {
            mapPanel.classList.toggle('collapsed');
            // Trigger map resize after animation
            setTimeout(() => {
                if (window.mapView && window.mapView.map) {
                    window.mapView.map.invalidateSize();
                }
            }, 350);
        });

        // Resize functionality
        if (resizeHandle) {
            let isResizing = false;
            let startX, startWidth;

            resizeHandle.addEventListener('mousedown', (e) => {
                isResizing = true;
                startX = e.clientX;
                startWidth = mapPanel.offsetWidth;
                resizeHandle.classList.add('resizing');
                document.body.style.cursor = 'ew-resize';
                document.body.style.userSelect = 'none';
                e.preventDefault();
            });

            document.addEventListener('mousemove', (e) => {
                if (!isResizing) return;
                const delta = e.clientX - startX;
                const newWidth = Math.max(200, Math.min(startWidth + delta, window.innerWidth * 0.6));
                mapPanel.style.flexBasis = newWidth + 'px';
            });

            document.addEventListener('mouseup', () => {
                if (isResizing) {
                    isResizing = false;
                    resizeHandle.classList.remove('resizing');
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                    // Trigger map resize
                    if (window.mapView && window.mapView.map) {
                        window.mapView.map.invalidateSize();
                    }
                }
            });
        }
    }
}

window.Timeline = Timeline;
