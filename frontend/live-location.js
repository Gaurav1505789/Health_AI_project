/**
 * Live Location Tracker
 * Tracks patient location in real-time and sends updates via WebSocket
 */

class LiveLocationTracker {
    constructor(alertId, chat) {
        this.alertId = alertId;
        this.chat = chat; // EmergencyChat instance
        this.watchId = null;
        this.updateInterval = null;
        this.currentLocation = null;
        this.isTracking = false;
        this.updateFrequency = 10000; // 10 seconds
    }

    /**
     * Start tracking location
     */
    startTracking() {
        if (this.isTracking) {
            console.log('[LOCATION] Already tracking');
            return;
        }

        if (!navigator.geolocation) {
            console.error('[LOCATION] Geolocation not supported');
            alert('⚠️ Geolocation not supported by your browser');
            return;
        }

        console.log('[LOCATION] Starting location tracking...');
        this.isTracking = true;

        // Get initial location immediately
        this.getCurrentLocation();

        // Watch position changes
        this.watchId = navigator.geolocation.watchPosition(
            (position) => this.handleLocationUpdate(position),
            (error) => this.handleLocationError(error),
            {
                enableHighAccuracy: true,
                timeout: 5000,
                maximumAge: 0
            }
        );

        // Send updates every 10 seconds
        this.updateInterval = setInterval(() => {
            if (this.currentLocation) {
                this.sendLocationUpdate();
            }
        }, this.updateFrequency);

        console.log('[LOCATION] Tracking started');
    }

    /**
     * Get current location once
     */
    getCurrentLocation() {
        navigator.geolocation.getCurrentPosition(
            (position) => this.handleLocationUpdate(position),
            (error) => this.handleLocationError(error),
            {
                enableHighAccuracy: true,
                timeout: 5000,
                maximumAge: 0
            }
        );
    }

    /**
     * Handle location update from browser
     */
    handleLocationUpdate(position) {
        this.currentLocation = {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy,
            timestamp: new Date(position.timestamp).toISOString()
        };

        console.log(`[LOCATION] Updated: (${this.currentLocation.latitude.toFixed(6)}, ${this.currentLocation.longitude.toFixed(6)})`);
        
        // Trigger custom event for UI updates
        window.dispatchEvent(new CustomEvent('patient_location_update', {
            detail: this.currentLocation
        }));
    }

    /**
     * Handle location error
     */
    handleLocationError(error) {
        console.error('[LOCATION] Error:', error.message);
        
        let errorMessage = 'Location error: ';
        switch (error.code) {
            case error.PERMISSION_DENIED:
                errorMessage += 'Permission denied. Please enable location access.';
                break;
            case error.POSITION_UNAVAILABLE:
                errorMessage += 'Position unavailable.';
                break;
            case error.TIMEOUT:
                errorMessage += 'Request timeout.';
                break;
            default:
                errorMessage += 'Unknown error.';
        }

        window.dispatchEvent(new CustomEvent('location_error', {
            detail: { error: errorMessage }
        }));
    }

    /**
     * Send location update via WebSocket
     */
    sendLocationUpdate() {
        if (!this.currentLocation || !this.chat) return;

        this.chat.updateLocation(
            this.currentLocation.latitude,
            this.currentLocation.longitude,
            this.currentLocation.accuracy
        );

        console.log('[LOCATION] Sent update to server');
    }

    /**
     * Stop tracking location
     */
    stopTracking() {
        if (!this.isTracking) return;

        if (this.watchId) {
            navigator.geolocation.clearWatch(this.watchId);
            this.watchId = null;
        }

        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }

        this.isTracking = false;
        console.log('[LOCATION] Tracking stopped');
    }

    /**
     * Get current location data
     */
    getLocation() {
        return this.currentLocation;
    }
}

/**
 * Live Location Map Display
 * Shows patient location on Leaflet map with real-time updates
 */
class LiveLocationMap {
    constructor(mapElementId) {
        this.mapElementId = mapElementId;
        this.map = null;
        this.patientMarker = null;
        this.pathPolyline = null;
        this.pathCoordinates = [];
        this.initialized = false;
    }

    /**
     * Initialize map
     */
    initialize(latitude, longitude) {
        if (this.initialized) {
            this.updateLocation(latitude, longitude);
            return;
        }

        const mapElement = document.getElementById(this.mapElementId);
        if (!mapElement) {
            console.error(`[MAP] Element ${this.mapElementId} not found`);
            return;
        }

        // Create map
        this.map = L.map(this.mapElementId).setView([latitude, longitude], 15);

        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 19
        }).addTo(this.map);

        // Add patient marker
        const patientIcon = L.divIcon({
            html: '<div style="background: #ff4444; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 20px; border: 3px solid white; box-shadow: 0 2px 8px rgba(0,0,0,0.3); animation: pulse 2s infinite;">🆘</div>',
            iconSize: [40, 40],
            className: 'patient-live-marker'
        });

        this.patientMarker = L.marker([latitude, longitude], { icon: patientIcon })
            .bindPopup('<b>🆘 Patient Live Location</b><br>Emergency Active')
            .addTo(this.map);

        // Initialize path polyline
        this.pathPolyline = L.polyline([], {
            color: '#ff4444',
            weight: 3,
            opacity: 0.7,
            dashArray: '5, 10'
        }).addTo(this.map);

        this.initialized = true;
        console.log('[MAP] Initialized');
    }

    /**
     * Update patient location on map
     */
    updateLocation(latitude, longitude) {
        if (!this.map || !this.patientMarker) {
            this.initialize(latitude, longitude);
            return;
        }

        const newLatLng = [latitude, longitude];

        // Update marker position
        this.patientMarker.setLatLng(newLatLng);

        // Add to path
        this.pathCoordinates.push(newLatLng);
        this.pathPolyline.setLatLngs(this.pathCoordinates);

        // Center map on patient (smooth pan)
        this.map.panTo(newLatLng, { animate: true, duration: 1 });

        console.log(`[MAP] Location updated: (${latitude.toFixed(6)}, ${longitude.toFixed(6)})`);
    }

    /**
     * Clear path
     */
    clearPath() {
        this.pathCoordinates = [];
        if (this.pathPolyline) {
            this.pathPolyline.setLatLngs([]);
        }
    }

    /**
     * Fit map to show all path
     */
    fitToPath() {
        if (this.pathCoordinates.length > 1 && this.map) {
            const bounds = L.latLngBounds(this.pathCoordinates);
            this.map.fitBounds(bounds, { padding: [50, 50] });
        }
    }
}

// Export for use in other files
window.LiveLocationTracker = LiveLocationTracker;
window.LiveLocationMap = LiveLocationMap;
