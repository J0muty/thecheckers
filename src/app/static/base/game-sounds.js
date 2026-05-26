(function () {
    const SOUND_PATHS = {
        gameFound: '/static/base/sounds/game-found.wav',
        victory: '/static/base/sounds/victory.wav',
        defeat: '/static/base/sounds/defeat.wav',
        draw: '/static/base/sounds/draw.wav',
        checkerMove: '/static/base/sounds/checker-move.wav',
        checkerCapture: '/static/base/sounds/checker-capture.wav',
        checkerPromotion: '/static/base/sounds/checker-promotion.wav',
    };

    const DEFAULT_VOLUME = 0.72;
    const DEFAULT_ONCE_TTL_MS = 24 * 60 * 60 * 1000;
    const SOUND_DEBUG_ENDPOINT = '/api/debug/sound_log';
    const audioCache = new Map();
    let unlocked = false;

    function navigationType() {
        try {
            return performance.getEntriesByType('navigation')[0]?.type || 'unknown';
        } catch (_) {
            return 'unknown';
        }
    }

    function debugLog(event, details = {}) {
        const payload = {
            event,
            details,
            path: location.pathname,
            href: location.href,
            visibility: document.visibilityState,
            hasFocus: typeof document.hasFocus === 'function' ? document.hasFocus() : null,
            navType: navigationType(),
            userAgent: navigator.userAgent,
            ts: Date.now(),
        };
        try {
            const body = JSON.stringify(payload);
            if (navigator.sendBeacon) {
                const blob = new Blob([body], {type: 'application/json'});
                if (navigator.sendBeacon(SOUND_DEBUG_ENDPOINT, blob)) return;
            }
            fetch(SOUND_DEBUG_ENDPOINT, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body,
                keepalive: true,
            }).catch(() => {});
        } catch (_) {}
    }

    function isEnabled() {
        if (typeof window.checkerSoundsEnabled === 'boolean') {
            return window.checkerSoundsEnabled;
        }
        try {
            const stored = localStorage.getItem('checkerSoundsEnabled');
            if (stored !== null) return stored !== '0' && stored !== 'false';
        } catch (_) {}
        return true;
    }

    function setEnabled(enabled) {
        window.checkerSoundsEnabled = enabled !== false;
        try {
            localStorage.setItem('checkerSoundsEnabled', window.checkerSoundsEnabled ? '1' : '0');
        } catch (_) {}
        debugLog('set_enabled', {enabled: window.checkerSoundsEnabled});
        return window.checkerSoundsEnabled;
    }

    function getAudio(name) {
        const src = SOUND_PATHS[name];
        if (!src) return null;
        if (!audioCache.has(name)) {
            const audio = new Audio(src);
            audio.preload = 'auto';
            audioCache.set(name, audio);
        }
        return audioCache.get(name);
    }

    function hasFreshOnceValue(value, ttlMs) {
        if (!value) return false;
        const timestamp = Number(value);
        if (!Number.isFinite(timestamp) || timestamp < 1000000000000) return true;
        return Date.now() - timestamp <= ttlMs;
    }

    function rememberOnce(onceKey, ttlMs = DEFAULT_ONCE_TTL_MS) {
        if (!onceKey) return false;
        const timestamp = String(Date.now());
        try {
            const stored = sessionStorage.getItem(onceKey);
            if (hasFreshOnceValue(stored, ttlMs)) {
                try {
                    localStorage.setItem(onceKey, Number(stored) >= 1000000000000 ? stored : timestamp);
                } catch (_) {}
                debugLog('once_skip_session', {onceKey, stored, ttlMs});
                return true;
            }
        } catch (_) {}
        try {
            const stored = localStorage.getItem(onceKey);
            if (hasFreshOnceValue(stored, ttlMs)) {
                try {
                    sessionStorage.setItem(onceKey, stored);
                } catch (_) {}
                debugLog('once_skip_local', {onceKey, stored, ttlMs});
                return true;
            }
        } catch (_) {}
        try {
            sessionStorage.setItem(onceKey, timestamp);
        } catch (_) {}
        try {
            localStorage.setItem(onceKey, timestamp);
        } catch (_) {}
        debugLog('once_marked', {onceKey, timestamp, ttlMs});
        return false;
    }

    function play(name, options = {}) {
        debugLog('play_requested', {
            name,
            onceKey: options.onceKey || null,
            onceTtlMs: options.onceTtlMs || null,
            enabled: isEnabled(),
        });
        if (!isEnabled()) {
            debugLog('play_skipped_disabled', {name});
            return false;
        }
        if (rememberOnce(options.onceKey, options.onceTtlMs)) {
            debugLog('play_skipped_once', {name, onceKey: options.onceKey || null});
            return false;
        }
        const audio = getAudio(name);
        if (!audio) {
            debugLog('play_skipped_missing_audio', {name});
            return false;
        }

        audio.pause();
        audio.currentTime = 0;
        audio.volume = typeof options.volume === 'number' ? options.volume : DEFAULT_VOLUME;

        const playPromise = audio.play();
        if (playPromise && typeof playPromise.catch === 'function') {
            playPromise
                .then(() => debugLog('play_resolved', {name, currentTime: audio.currentTime, volume: audio.volume}))
                .catch(error => debugLog('play_rejected', {
                    name,
                    errorName: error?.name || null,
                    errorMessage: error?.message || String(error),
                }));
        }
        debugLog('play_started', {name, volume: audio.volume, src: audio.currentSrc || audio.src});
        return true;
    }

    function preload(names = Object.keys(SOUND_PATHS)) {
        if (!isEnabled()) {
            debugLog('preload_skipped_disabled', {names});
            return;
        }
        debugLog('preload_requested', {names});
        names.forEach(name => {
            const audio = getAudio(name);
            if (audio) {
                audio.load();
                debugLog('preload_audio', {name, src: audio.currentSrc || audio.src});
            }
        });
    }

    function resultSoundName(status, playerColor) {
        if (status === 'draw') return 'draw';
        if (status !== 'white_win' && status !== 'black_win') return null;

        const winner = status === 'white_win' ? 'white' : 'black';
        if (playerColor === 'white' || playerColor === 'black') {
            return playerColor === winner ? 'victory' : 'defeat';
        }
        return null;
    }

    function playResult(status, playerColor, options = {}) {
        const name = resultSoundName(status, playerColor);
        debugLog('play_result_requested', {status, playerColor, soundName: name, onceKey: options.onceKey || null});
        return name ? play(name, options) : false;
    }

    function unlock() {
        if (!isEnabled()) {
            debugLog('unlock_skipped_disabled');
            return;
        }
        if (unlocked) {
            debugLog('unlock_skipped_already_unlocked');
            return;
        }
        unlocked = true;
        debugLog('unlock_marked_without_audio_playback');
    }

    ['pointerdown', 'touchstart'].forEach(eventName => {
        document.addEventListener(eventName, unlock, { once: true, passive: true });
    });

    window.CheckersSound = {
        play,
        playResult,
        preload,
        unlock,
        isEnabled,
        setEnabled,
        resultSoundName,
        debugLog,
    };
    debugLog('module_loaded', {enabled: isEnabled(), soundNames: Object.keys(SOUND_PATHS)});
})();
