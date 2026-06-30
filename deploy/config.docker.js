// Frontend config for the self-hosted (Docker/MinIO) deployment.
// Baked over web/config.js in the Docker image. Empty API URL makes every
// page fall back to window.location.origin, so the browser talks to the
// same uvicorn that served the page. The committed web/config.js (with the
// AWS API Gateway URL) is left intact for the cloud deployment.
window.SAILFRAMES_API_URL = '';

// Read fleet.html / battery.html status files through the API proxy
// (/api/fleet/*) instead of directly from the bucket. MinIO stays private.
window.SAILFRAMES_FLEET_VIA_API = true;

// Analytics disabled in self-hosted mode (analytics.js no-ops when empty).
window.SAILFRAMES_GA_ID = '';

// AI coach / chat features are out of scope for the self-hosted stack.
// Leaving these empty makes the coach pages degrade gracefully.
window.SAILFRAMES_COACH_API = '';
window.SAILFRAMES_GOOGLE_CLIENT_ID = '';
