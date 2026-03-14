/**
 * Emergency Chat Module
 * Handles real-time doctor-patient communication via WebSocket
 */

class EmergencyChat {
    constructor(alertId, userType, userName) {
        this.alertId = alertId;
        this.userType = userType; // 'doctor' or 'patient'
        this.userName = userName;
        this.socket = null;
        this.connected = false;
        this.messageCallbacks = [];
        this.statusCallbacks = [];
    }

    /**
     * Connect to WebSocket server
     */
    connect() {
        console.log(`[CHAT] Connecting to WebSocket server...`);
        
        // Connect to WebSocket server on port 5001
        this.socket = io('http://localhost:5001', {
            transports: ['websocket', 'polling']
        });

        // Connection established
        this.socket.on('connect', () => {
            console.log('[CHAT] Connected to WebSocket server');
            this.connected = true;
            this.joinEmergencyRoom();
            this.notifyStatus('connected');
        });

        // Connection failed
        this.socket.on('connect_error', (error) => {
            console.error('[CHAT] Connection error:', error);
            this.connected = false;
            this.notifyStatus('error');
        });

        // Disconnected
        this.socket.on('disconnect', () => {
            console.log('[CHAT] Disconnected from server');
            this.connected = false;
            this.notifyStatus('disconnected');
        });

        // User joined
        this.socket.on('user_joined', (data) => {
            console.log(`[CHAT] ${data.user_type} joined:`, data.user_name);
            this.notifyStatus('user_joined', data);
        });

        // New message received
        this.socket.on('new_message', (message) => {
            console.log('[CHAT] New message:', message);
            this.messageCallbacks.forEach(callback => callback(message));
        });

        // Location update
        this.socket.on('location_update', (data) => {
            console.log('[CHAT] Location update:', data);
            window.dispatchEvent(new CustomEvent('location_update', { detail: data }));
        });

        // Timeline updated
        this.socket.on('timeline_updated', (data) => {
            console.log('[CHAT] Timeline updated:', data);
            window.dispatchEvent(new CustomEvent('timeline_updated', { detail: data }));
        });

        // Doctor/Patient connection status
        this.socket.on('doctor_disconnected', () => {
            this.notifyStatus('doctor_disconnected');
        });

        this.socket.on('patient_disconnected', () => {
            this.notifyStatus('patient_disconnected');
        });
    }

    /**
     * Join emergency room for this alert
     */
    joinEmergencyRoom() {
        if (!this.socket || !this.connected) return;

        this.socket.emit('join_emergency', {
            alert_id: this.alertId,
            user_type: this.userType,
            user_name: this.userName
        });

        console.log(`[CHAT] Joined emergency room ${this.alertId} as ${this.userType}`);
    }

    /**
     * Send chat message
     */
    sendMessage(message) {
        if (!this.socket || !this.connected) {
            console.error('[CHAT] Not connected to server');
            return false;
        }

        if (!message || !message.trim()) {
            console.error('[CHAT] Empty message');
            return false;
        }

        this.socket.emit('send_message', {
            alert_id: this.alertId,
            sender_type: this.userType,
            sender_name: this.userName,
            message: message.trim()
        });

        console.log('[CHAT] Message sent:', message);
        return true;
    }

    /**
     * Update live location
     */
    updateLocation(latitude, longitude, accuracy = 0) {
        if (!this.socket || !this.connected) return;

        this.socket.emit('update_location', {
            alert_id: this.alertId,
            latitude: latitude,
            longitude: longitude,
            accuracy: accuracy
        });

        console.log(`[CHAT] Location updated: (${latitude}, ${longitude})`);
    }

    /**
     * Add timeline event
     */
    addTimelineEvent(eventType, description = '') {
        if (!this.socket || !this.connected) return;

        this.socket.emit('add_timeline_event', {
            alert_id: this.alertId,
            event_type: eventType,
            description: description
        });

        console.log(`[CHAT] Timeline event: ${eventType}`);
    }

    /**
     * Register callback for new messages
     */
    onMessage(callback) {
        this.messageCallbacks.push(callback);
    }

    /**
     * Register callback for status changes
     */
    onStatusChange(callback) {
        this.statusCallbacks.push(callback);
    }

    /**
     * Notify status change
     */
    notifyStatus(status, data = null) {
        this.statusCallbacks.forEach(callback => callback(status, data));
    }

    /**
     * Load chat history from server
     */
    async loadHistory() {
        try {
            const response = await fetch(`http://localhost:5001/chat-history/${this.alertId}`);
            const data = await response.json();
            
            if (data.success) {
                console.log(`[CHAT] Loaded ${data.messages.length} messages`);
                return data.messages;
            }
        } catch (error) {
            console.error('[CHAT] Error loading history:', error);
        }
        return [];
    }

    /**
     * Disconnect from server
     */
    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
            this.connected = false;
            console.log('[CHAT] Disconnected');
        }
    }
}

// Export for use in other files
window.EmergencyChat = EmergencyChat;
