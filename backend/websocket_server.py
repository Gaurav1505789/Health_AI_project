"""
WebSocket Server for Real-Time Emergency Communication
Handles:
- Doctor-Patient Chat
- Live Location Updates
- Emergency Timeline Events
- Connection Status
"""

from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import json
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
app.config['SECRET_KEY'] = 'health_ai_emergency_2026'
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CHAT_FILE = DATA_DIR / "emergency_chats.json"
TIMELINE_FILE = DATA_DIR / "emergency_timeline.json"
LOCATION_FILE = DATA_DIR / "live_locations.json"

# In-memory storage for active connections
active_connections = {}  # {alert_id: {'doctor': sid, 'patient': sid}}

def _load_json(file_path):
    """Load JSON file or create if not exists"""
    if not file_path.exists():
        file_path.write_text(json.dumps({"data": []}, indent=2))
    return json.loads(file_path.read_text())

def _save_json(file_path, data):
    """Save JSON file"""
    file_path.write_text(json.dumps(data, indent=2))

# ===== WEBSOCKET EVENTS =====

@socketio.on('connect')
def handle_connect():
    """Client connected"""
    print(f'[WEBSOCKET] Client connected: {request.sid}')
    emit('connection_status', {'status': 'connected', 'sid': request.sid})

@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected"""
    print(f'[WEBSOCKET] Client disconnected: {request.sid}')
    # Remove from active connections
    for alert_id, connections in list(active_connections.items()):
        if connections.get('doctor') == request.sid:
            connections['doctor'] = None
            emit('doctor_disconnected', {'alert_id': alert_id}, room=f'emergency_{alert_id}')
        if connections.get('patient') == request.sid:
            connections['patient'] = None
            emit('patient_disconnected', {'alert_id': alert_id}, room=f'emergency_{alert_id}')

@socketio.on('join_emergency')
def handle_join_emergency(data):
    """Join emergency room for real-time updates"""
    alert_id = data.get('alert_id')
    user_type = data.get('user_type')  # 'doctor' or 'patient'
    user_name = data.get('user_name', 'Unknown')
    
    if not alert_id:
        return
    
    room = f'emergency_{alert_id}'
    join_room(room)
    
    # Track connection
    if alert_id not in active_connections:
        active_connections[alert_id] = {'doctor': None, 'patient': None}
    
    active_connections[alert_id][user_type] = request.sid
    
    print(f'[WEBSOCKET] {user_type} {user_name} joined emergency {alert_id}')
    
    # Notify room
    emit('user_joined', {
        'alert_id': alert_id,
        'user_type': user_type,
        'user_name': user_name,
        'timestamp': datetime.now().isoformat()
    }, room=room)
    
    # Add timeline event
    _add_timeline_event(alert_id, f'{user_type.title()} Connected', user_name)

@socketio.on('send_message')
def handle_send_message(data):
    """Handle chat message"""
    alert_id = data.get('alert_id')
    sender_type = data.get('sender_type')  # 'doctor' or 'patient'
    sender_name = data.get('sender_name')
    message = data.get('message', '').strip()
    
    if not all([alert_id, sender_type, sender_name, message]):
        return
    
    # Save message
    chat_data = _load_json(CHAT_FILE)
    message_record = {
        'id': len(chat_data['data']) + 1,
        'alert_id': alert_id,
        'sender_type': sender_type,
        'sender_name': sender_name,
        'message': message,
        'timestamp': datetime.now().isoformat()
    }
    chat_data['data'].append(message_record)
    _save_json(CHAT_FILE, chat_data)
    
    # Broadcast to room
    room = f'emergency_{alert_id}'
    emit('new_message', message_record, room=room)
    
    print(f'[CHAT] {sender_name} ({sender_type}): {message[:50]}...')

@socketio.on('update_location')
def handle_update_location(data):
    """Handle live location update"""
    alert_id = data.get('alert_id')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    accuracy = data.get('accuracy', 0)
    
    if not all([alert_id, latitude, longitude]):
        return
    
    # Save location
    location_data = _load_json(LOCATION_FILE)
    
    # Update or create location record
    location_record = None
    for loc in location_data['data']:
        if loc['alert_id'] == alert_id:
            location_record = loc
            break
    
    if location_record:
        location_record['latitude'] = latitude
        location_record['longitude'] = longitude
        location_record['accuracy'] = accuracy
        location_record['updated_at'] = datetime.now().isoformat()
    else:
        location_record = {
            'alert_id': alert_id,
            'latitude': latitude,
            'longitude': longitude,
            'accuracy': accuracy,
            'updated_at': datetime.now().isoformat(),
            'path': []
        }
        location_data['data'].append(location_record)
    
    # Add to path for tracking
    if 'path' not in location_record:
        location_record['path'] = []
    location_record['path'].append({
        'lat': latitude,
        'lon': longitude,
        'timestamp': datetime.now().isoformat()
    })
    
    _save_json(LOCATION_FILE, location_data)
    
    # Broadcast to room
    room = f'emergency_{alert_id}'
    emit('location_update', {
        'alert_id': alert_id,
        'latitude': latitude,
        'longitude': longitude,
        'accuracy': accuracy,
        'timestamp': datetime.now().isoformat()
    }, room=room)
    
    print(f'[LOCATION] Alert {alert_id}: ({latitude:.6f}, {longitude:.6f})')

@socketio.on('add_timeline_event')
def handle_add_timeline_event(data):
    """Add event to emergency timeline"""
    alert_id = data.get('alert_id')
    event_type = data.get('event_type')
    description = data.get('description', '')
    
    if not all([alert_id, event_type]):
        return
    
    _add_timeline_event(alert_id, event_type, description)
    
    # Broadcast to room
    room = f'emergency_{alert_id}'
    emit('timeline_updated', {
        'alert_id': alert_id,
        'event_type': event_type,
        'description': description,
        'timestamp': datetime.now().isoformat()
    }, room=room)

def _add_timeline_event(alert_id, event_type, description=''):
    """Add event to timeline"""
    timeline_data = _load_json(TIMELINE_FILE)
    event = {
        'id': len(timeline_data['data']) + 1,
        'alert_id': alert_id,
        'event_type': event_type,
        'description': description,
        'timestamp': datetime.now().isoformat()
    }
    timeline_data['data'].append(event)
    _save_json(TIMELINE_FILE, timeline_data)
    print(f'[TIMELINE] Alert {alert_id}: {event_type}')

# ===== HTTP ENDPOINTS =====

@app.route('/chat-history/<int:alert_id>')
def get_chat_history(alert_id):
    """Get chat history for emergency"""
    chat_data = _load_json(CHAT_FILE)
    messages = [msg for msg in chat_data['data'] if msg['alert_id'] == alert_id]
    return {'success': True, 'messages': messages}

@app.route('/timeline/<int:alert_id>')
def get_timeline(alert_id):
    """Get timeline for emergency"""
    timeline_data = _load_json(TIMELINE_FILE)
    events = [evt for evt in timeline_data['data'] if evt['alert_id'] == alert_id]
    return {'success': True, 'events': events}

@app.route('/live-location/<int:alert_id>')
def get_live_location(alert_id):
    """Get current live location"""
    location_data = _load_json(LOCATION_FILE)
    for loc in location_data['data']:
        if loc['alert_id'] == alert_id:
            return {'success': True, 'location': loc}
    return {'success': False, 'error': 'Location not found'}

if __name__ == '__main__':
    print('\n' + '='*60)
    print('HEALTH AI - WEBSOCKET SERVER STARTING')
    print('='*60)
    print('Real-time features:')
    print('  ✓ Doctor-Patient Chat')
    print('  ✓ Live Location Tracking')
    print('  ✓ Emergency Timeline')
    print('='*60 + '\n')
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)
