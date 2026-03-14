/**
 * Yoga & Wellness Module
 * Handles yoga poses, exercise timer, progress tracking, and video demos
 */

// Yoga poses database with details
const yogaPoses = [
    {
        id: 1,
        name: 'Tadasana',
        englishName: 'Mountain Pose',
        duration: 60,
        difficulty: 'Beginner',
        benefits: ['Improves posture', 'Strengthens legs', 'Improves balance', 'Increases awareness'],
        videoId: 'KN_RXucmlkY',
        image: '🧍'
    },
    {
        id: 2,
        name: 'Bhujangasana',
        englishName: 'Cobra Pose',
        duration: 30,
        difficulty: 'Beginner',
        benefits: ['Strengthens spine', 'Opens chest', 'Reduces stress', 'Improves flexibility'],
        videoId: 'JUP_YdYyfQw',
        image: '🐍'
    },
    {
        id: 3,
        name: 'Vrikshasana',
        englishName: 'Tree Pose',
        duration: 60,
        difficulty: 'Intermediate',
        benefits: ['Improves balance', 'Strengthens legs', 'Increases focus', 'Calms mind'],
        videoId: 'VmfT4hZcZz4',
        image: '🌳'
    },
    {
        id: 4,
        name: 'Adho Mukha Svanasana',
        englishName: 'Downward Dog',
        duration: 60,
        difficulty: 'Beginner',
        benefits: ['Stretches hamstrings', 'Strengthens arms', 'Energizes body', 'Relieves back pain'],
        videoId: '7Hlc-QKUVwQ',
        image: '🐕'
    },
    {
        id: 5,
        name: 'Balasana',
        englishName: 'Child Pose',
        duration: 120,
        difficulty: 'Beginner',
        benefits: ['Relaxes body', 'Reduces stress', 'Stretches back', 'Calms nervous system'],
        videoId: 'E6CU80PqyFw',
        image: '🧘'
    },
    {
        id: 6,
        name: 'Surya Namaskar',
        englishName: 'Sun Salutation',
        duration: 600,
        difficulty: 'Intermediate',
        benefits: ['Full body workout', 'Improves flexibility', 'Boosts metabolism', 'Increases energy'],
        videoId: 'qTu6i1YFvJM',
        image: '☀️'
    }
];

// Timer variables
let timerInterval = null;
let timerSeconds = 60;
let timerRunning = false;
let currentPoseId = null;

// Progress tracking
let completedExercises = [];
let totalMinutes = 0;
let currentExerciseId = null; // Track current exercise session
let exerciseStartTime = null;

/**
 * Initialize yoga page
 */
document.addEventListener('DOMContentLoaded', () => {
    loadYogaPoses();
    loadProgress();
    updateProgressDisplay();
    loadExerciseData(); // Load exercise tracking data
});

/**
 * Load and display yoga poses
 */
function loadYogaPoses() {
    const grid = document.getElementById('poses-grid');
    
    grid.innerHTML = yogaPoses.map(pose => `
        <div class="pose-card ${isCompleted(pose.id) ? 'completed' : ''}" data-pose-id="${pose.id}">
            <div class="pose-icon">${pose.image}</div>
            <h3>${pose.name}</h3>
            <p class="pose-english">${pose.englishName}</p>
            <div class="pose-meta">
                <span class="difficulty ${pose.difficulty.toLowerCase()}">${pose.difficulty}</span>
                <span class="duration">⏱️ ${formatDuration(pose.duration)}</span>
            </div>
            <div class="pose-benefits">
                <strong>Benefits:</strong>
                <ul>
                    ${pose.benefits.map(b => `<li>${b}</li>`).join('')}
                </ul>
            </div>
            <div class="pose-actions">
                <button class="btn-primary" onclick="openTimer(${pose.id})">
                    ${isCompleted(pose.id) ? '✓ Practice Again' : 'Start Exercise'}
                </button>
                <button class="btn-secondary" onclick="openVideo(${pose.id})">Watch Demo</button>
            </div>
            ${isCompleted(pose.id) ? '<div class="completed-badge">✓ Completed</div>' : ''}
        </div>
    `).join('');
}

/**
 * Format duration in seconds to readable format
 */
function formatDuration(seconds) {
    if (seconds >= 60) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return secs > 0 ? `${mins}m ${secs}s` : `${mins} min`;
    }
    return `${seconds}s`;
}

/**
 * Check if exercise is completed
 */
function isCompleted(poseId) {
    return completedExercises.includes(poseId);
}

/**
 * Open timer modal for pose
 */
function openTimer(poseId) {
    currentPoseId = poseId;
    const pose = yogaPoses.find(p => p.id === poseId);
    
    if (!pose) return;
    
    document.getElementById('timer-pose-name').textContent = `${pose.name} (${pose.englishName})`;
    timerSeconds = pose.duration;
    document.getElementById('timer-value').textContent = timerSeconds;
    document.getElementById('timer-modal').style.display = 'block';
    
    resetTimer();
}

/**
 * Close timer modal
 */
function closeTimer() {
    document.getElementById('timer-modal').style.display = 'none';
    pauseTimer();
    resetTimer();
}

/**
 * Start exercise timer
 */
function startTimer() {
    if (timerRunning) return;
    
    timerRunning = true;
    document.getElementById('start-timer-btn').style.display = 'none';
    document.getElementById('pause-timer-btn').style.display = 'inline-block';
    
    timerInterval = setInterval(() => {
        timerSeconds--;
        document.getElementById('timer-value').textContent = timerSeconds;
        
        if (timerSeconds <= 0) {
            completeExercise();
        }
    }, 1000);
}

/**
 * Pause timer
 */
function pauseTimer() {
    if (!timerRunning) return;
    
    timerRunning = false;
    clearInterval(timerInterval);
    document.getElementById('start-timer-btn').style.display = 'inline-block';
    document.getElementById('pause-timer-btn').style.display = 'none';
}

/**
 * Reset timer
 */
function resetTimer() {
    pauseTimer();
    const pose = yogaPoses.find(p => p.id === currentPoseId);
    if (pose) {
        timerSeconds = pose.duration;
        document.getElementById('timer-value').textContent = timerSeconds;
    }
}

/**
 * Complete exercise and mark as done
 */
function completeExercise() {
    pauseTimer();
    
    if (currentPoseId && !isCompleted(currentPoseId)) {
        completedExercises.push(currentPoseId);
        
        const pose = yogaPoses.find(p => p.id === currentPoseId);
        if (pose) {
            totalMinutes += Math.floor(pose.duration / 60);
        }
        
        saveProgress();
        updateProgressDisplay();
        loadYogaPoses();
    }
    
    alert('🎉 Exercise completed! Great job!');
    closeTimer();
}

/**
 * Open video demonstration
 */
function openVideo(poseId) {
    const pose = yogaPoses.find(p => p.id === poseId);
    
    if (!pose) return;
    
    document.getElementById('video-pose-name').textContent = `${pose.name} - Video Demonstration`;
    
    const videoContainer = document.getElementById('video-container');
    videoContainer.innerHTML = `
        <iframe 
            width="100%" 
            height="400" 
            src="https://www.youtube.com/embed/${pose.videoId}" 
            frameborder="0" 
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
            allowfullscreen>
        </iframe>
    `;
    
    document.getElementById('video-modal').style.display = 'block';
}

/**
 * Close video modal
 */
function closeVideo() {
    document.getElementById('video-modal').style.display = 'none';
    document.getElementById('video-container').innerHTML = '';
}

/**
 * Start routine (morning or evening)
 */
function startRoutine(type) {
    const routines = {
        morning: ['Stretching', 'Surya Namaskar', 'Deep Breathing'],
        evening: ['Walking', 'Light Yoga', 'Meditation']
    };
    
    const routine = routines[type];
    const routineName = type.charAt(0).toUpperCase() + type.slice(1);
    
    alert(`Starting ${routineName} Routine:\n\n${routine.map((ex, i) => `${i + 1}. ${ex}`).join('\n')}\n\nLet's begin!`);
}

/**
 * Start breathing exercise
 */
function startBreathing(type) {
    const exercises = {
        anulom: { name: 'Anulom Vilom', duration: 300 },
        kapalbhati: { name: 'Kapalbhati', duration: 180 },
        bhramari: { name: 'Bhramari', duration: 300 }
    };
    
    const exercise = exercises[type];
    
    if (!exercise) return;
    
    document.getElementById('timer-pose-name').textContent = exercise.name;
    timerSeconds = exercise.duration;
    document.getElementById('timer-value').textContent = timerSeconds;
    document.getElementById('timer-modal').style.display = 'block';
    
    resetTimer();
}

/**
 * Save progress to localStorage
 */
function saveProgress() {
    const progress = {
        completedExercises: completedExercises,
        totalMinutes: totalMinutes,
        lastUpdated: new Date().toISOString()
    };
    
    localStorage.setItem('yoga_progress', JSON.stringify(progress));
}

/**
 * Load progress from localStorage
 */
function loadProgress() {
    const saved = localStorage.getItem('yoga_progress');
    
    if (saved) {
        const progress = JSON.parse(saved);
        completedExercises = progress.completedExercises || [];
        totalMinutes = progress.totalMinutes || 0;
    }
}

/**
 * Update progress display
 */
function updateProgressDisplay() {
    document.getElementById('completed-count').textContent = completedExercises.length;
    document.getElementById('total-time').textContent = totalMinutes;
}

/**
 * Close modal when clicking outside
 */
window.onclick = (event) => {
    const timerModal = document.getElementById('timer-modal');
    const videoModal = document.getElementById('video-modal');
    
    if (event.target === timerModal) {
        closeTimer();
    }
    if (event.target === videoModal) {
        closeVideo();
    }
};


// ===== EXERCISE TRACKING FUNCTIONS =====

/**
 * Load exercise data from backend
 */
async function loadExerciseData() {
    const user = JSON.parse(sessionStorage.getItem('user') || '{}');
    
    if (!user.id) {
        console.log('[EXERCISE] No user logged in');
        return;
    }
    
    try {
        const response = await fetch(`http://localhost:5000/api/exercise/user/${user.id}`);
        const data = await response.json();
        
        if (data.success) {
            displayExerciseStatus(data.todayExercise);
            displayWeeklyProgress(data.weeklyStats, data.weeklyCompletion);
            console.log('[EXERCISE] Data loaded:', data);
        }
    } catch (error) {
        console.error('[EXERCISE] Error loading data:', error);
    }
}

/**
 * Display today's exercise status
 */
function displayExerciseStatus(todayExercise) {
    const statusDiv = document.getElementById('exercise-status');
    
    if (!todayExercise) {
        // No exercise today
        statusDiv.innerHTML = `
            <p class="status-text">Start your morning exercise routine</p>
            <button class="btn-primary btn-large" onclick="startMorningExercise()">Start Morning Exercise</button>
        `;
    } else if (todayExercise.status === 'started') {
        // Exercise in progress
        currentExerciseId = todayExercise.id;
        exerciseStartTime = new Date(todayExercise.start_time);
        
        statusDiv.innerHTML = `
            <div class="exercise-active">
                <p class="status-text">🏃 Exercise in Progress</p>
                <p class="exercise-type">${todayExercise.exercise_type}</p>
                <p class="start-time">Started: ${new Date(todayExercise.start_time).toLocaleTimeString()}</p>
                <button class="btn-primary btn-large" onclick="completeMorningExercise()">Complete Exercise</button>
            </div>
        `;
    } else if (todayExercise.status === 'completed') {
        // Exercise completed
        statusDiv.innerHTML = `
            <div class="exercise-completed">
                <p class="status-text">✅ Today's Exercise Completed!</p>
                <p class="exercise-type">${todayExercise.exercise_type}</p>
                <div class="exercise-details">
                    <span>⏱️ Duration: ${todayExercise.duration}</span>
                    <span>🕐 Time: ${new Date(todayExercise.start_time).toLocaleTimeString()}</span>
                </div>
                <button class="btn-secondary" onclick="startMorningExercise()">Start Another Session</button>
            </div>
        `;
    }
}

/**
 * Display weekly progress
 */
function displayWeeklyProgress(weeklyStats, weeklyCompletion) {
    if (!weeklyStats) return;
    
    // Update progress bar
    const progressBar = document.getElementById('weekly-progress-bar');
    const progressText = document.getElementById('progress-text');
    const percentage = (weeklyCompletion.completed / weeklyCompletion.total) * 100;
    
    progressBar.style.width = `${percentage}%`;
    progressText.textContent = `${weeklyCompletion.completed} / ${weeklyCompletion.total} days completed`;
    
    // Update calendar
    const calendar = document.getElementById('weekly-calendar');
    calendar.innerHTML = weeklyStats.map(day => `
        <div class="day-item ${day.completed ? 'completed' : ''}">
            <div class="day-name">${day.day}</div>
            <div class="day-status">${day.completed ? '✔' : '✖'}</div>
        </div>
    `).join('');
}

/**
 * Start morning exercise
 */
async function startMorningExercise() {
    const user = JSON.parse(sessionStorage.getItem('user') || '{}');
    
    if (!user.id) {
        alert('Please login to track your exercise');
        return;
    }
    
    console.log('[EXERCISE] Starting exercise for user:', user.id);
    
    try {
        console.log('[EXERCISE] Sending request to: http://localhost:5000/api/exercise/start');
        
        const response = await fetch('http://localhost:5000/api/exercise/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                userId: user.id,
                exerciseType: 'Morning Yoga'
            })
        });
        
        console.log('[EXERCISE] Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('[EXERCISE] Response data:', data);
        
        if (data.success) {
            currentExerciseId = data.exercise_id;
            exerciseStartTime = new Date();
            
            alert('✅ Morning exercise started! Complete your routine and click "Complete Exercise" when done.');
            loadExerciseData(); // Refresh display
            
            console.log('[EXERCISE] Started successfully:', data);
        } else {
            alert('Error starting exercise: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('[EXERCISE] Error details:', error);
        
        // Provide specific error messages
        if (error.message.includes('Failed to fetch')) {
            alert('❌ Cannot connect to backend server.\n\nPlease ensure:\n1. Backend server is running (python backend/app.py)\n2. Server is running on http://localhost:5000\n3. Check console for details');
        } else if (error.message.includes('NetworkError')) {
            alert('❌ Network error. Please check your internet connection.');
        } else {
            alert('❌ Error: ' + error.message + '\n\nCheck browser console for details.');
        }
    }
}

/**
 * Complete morning exercise
 */
async function completeMorningExercise() {
    const user = JSON.parse(sessionStorage.getItem('user') || '{}');
    
    if (!user.id || !currentExerciseId) {
        alert('No active exercise session');
        return;
    }
    
    if (!confirm('Mark this exercise as completed?')) {
        return;
    }
    
    console.log('[EXERCISE] Completing exercise:', currentExerciseId);
    
    try {
        const response = await fetch('http://localhost:5000/api/exercise/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                userId: user.id,
                exerciseId: currentExerciseId
            })
        });
        
        console.log('[EXERCISE] Complete response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('[EXERCISE] Complete response data:', data);
        
        if (data.success) {
            alert(`🎉 Exercise completed! Duration: ${data.exercise.duration}`);
            currentExerciseId = null;
            exerciseStartTime = null;
            loadExerciseData(); // Refresh display
            
            console.log('[EXERCISE] Completed successfully:', data);
        } else {
            alert('Error completing exercise: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('[EXERCISE] Error details:', error);
        
        if (error.message.includes('Failed to fetch')) {
            alert('❌ Cannot connect to backend server.\n\nPlease ensure backend is running on http://localhost:5000');
        } else {
            alert('❌ Error: ' + error.message);
        }
    }
}
