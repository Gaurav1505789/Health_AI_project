// Get DOM elements with null checks (some may not exist on all pages)
const form = document.getElementById("symptom-form");
const symptomTextInput = document.getElementById("symptom-text");
const analyzeSymptomsButton = document.getElementById("analyze-symptoms");
const nlpStatus = document.getElementById("nlp-status");
const searchInput = document.getElementById("symptom-search");
const suggestionsList = document.getElementById("symptom-suggestions");
const selectedTags = document.getElementById("selected-symptoms");
const results = document.getElementById("results");
const emergencyBox = document.getElementById("emergency-box");
const settingsBtn = document.getElementById("settings-btn");
const settingsSidebar = document.getElementById("settings-sidebar");
const settingsOverlay = document.getElementById("settings-overlay");
const settingsClose = document.getElementById("settings-close");
const darkModeToggle = document.getElementById("dark-mode-toggle");
const colorBlindToggle = document.getElementById("color-blind-toggle");
const tabSymptom = document.getElementById("tab-symptom");
const tabChat = document.getElementById("tab-chat");
const symptomView = document.getElementById("symptom-view");
const chatView = document.getElementById("chat-view");
const chatFab = document.getElementById("chat-fab");
const chatFloat = document.getElementById("chat-float");
const chatHistory = document.getElementById("chat-history");
const chatHistoryFloat = document.getElementById("chat-history-float");
const chatInput = document.getElementById("chat-input");
const chatInputFloat = document.getElementById("chat-input-float");
const chatSend = document.getElementById("chat-send");
const chatSendFloat = document.getElementById("chat-send-float");

const API_URL = "http://localhost:5000/predict";
const SYMPTOMS_URL = "http://localhost:5000/symptoms";
const EXTRACT_URL = "http://localhost:5000/extract-symptoms";
const CHAT_URL = "http://localhost:5000/chat";
const CHAT_STATUS_URL = "http://localhost:5000/chat-status";
const STORAGE_DARK_MODE = "health_ai_dark_mode";
const STORAGE_COLOR_BLIND = "health_ai_color_blind_mode";

let allSymptoms = [];
const chosenSymptoms = new Set();
let highlightedSuggestionIndex = -1;
const chatMessages = [
    {
        role: "bot",
        text: "Hello, I am your AI Health Assistant. Ask me general health, diet, lifestyle, or preventive care questions.",
    },
];


function applyThemePreferences() {
    const darkModeEnabled = localStorage.getItem(STORAGE_DARK_MODE) === "true";
    const colorBlindEnabled = localStorage.getItem(STORAGE_COLOR_BLIND) === "true";

    document.body.classList.toggle("dark-mode", darkModeEnabled);
    document.body.classList.toggle("color-blind-mode", colorBlindEnabled);

    darkModeToggle.checked = darkModeEnabled;
    colorBlindToggle.checked = colorBlindEnabled;
}

function openSettings() {
    settingsSidebar.classList.add("open");
    settingsOverlay.classList.add("active");
}

function closeSettings() {
    settingsSidebar.classList.remove("open");
    settingsOverlay.classList.remove("active");
}

async function checkChatStatus() {
    const statusElement = document.getElementById("chat-status");
    const statusText = statusElement.querySelector(".status-text");
    
    try {
        const response = await fetch(CHAT_STATUS_URL);
        const data = await response.json();
        
        if (data.connected) {
            statusElement.classList.add("connected");
            statusElement.classList.remove("fallback");
            statusText.textContent = "chat bot Connected";
        } else {
            statusElement.classList.add("fallback");
            statusElement.classList.remove("connected");
            statusText.textContent = "Fallback Mode";
        }
    } catch (error) {
        statusElement.classList.add("fallback");
        statusElement.classList.remove("connected");
        statusText.textContent = "Offline";
    }
}

function toLabel(text) {
    return String(text)
        .split(" ")
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
}

function renderChosenTags() {
    selectedTags.innerHTML = "";
    Array.from(chosenSymptoms).forEach((symptom) => {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.innerHTML = `${toLabel(symptom)} <button type="button" aria-label="Remove ${symptom}">x</button>`;

        tag.querySelector("button").addEventListener("click", () => {
            chosenSymptoms.delete(symptom);
            renderChosenTags();
            renderSuggestions(searchInput.value);
        });

        selectedTags.appendChild(tag);
    });
}

function addSymptom(symptom) {
    if (!symptom || chosenSymptoms.has(symptom)) {
        return;
    }
    chosenSymptoms.add(symptom);
    searchInput.value = "";
    renderChosenTags();
    renderSuggestions("");
}

function renderSuggestions(query) {
    const normalized = query.trim().toLowerCase();
    suggestionsList.innerHTML = "";
    highlightedSuggestionIndex = -1;
    searchInput.setAttribute("aria-expanded", "false");

    if (normalized.length < 1) {
        return;
    }

    const matches = allSymptoms
        .filter((symptom) => !chosenSymptoms.has(symptom))
        .filter((symptom) => symptom.includes(normalized))
        .slice(0, 8);

    matches.forEach((symptom) => {
        const item = document.createElement("li");
        item.className = "suggestion-item";
        item.setAttribute("role", "option");
        item.setAttribute("tabindex", "0");
        item.textContent = toLabel(symptom);
        item.addEventListener("click", () => addSymptom(symptom));
        item.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                addSymptom(symptom);
            }
        });
        suggestionsList.appendChild(item);
    });

    searchInput.setAttribute("aria-expanded", String(matches.length > 0));
}


function riskLabel(level) {
    if (level === "Low") {
        return "Low ✔";
    }
    if (level === "Medium") {
        return "Medium ⚠";
    }
    if (level === "High") {
        return "High 🚨";
    }
    return level || "Not available";
}

function renderEmergency(message) {
    if (!message) {
        emergencyBox.classList.add("hidden");
        emergencyBox.textContent = "";
        return;
    }

    emergencyBox.textContent = message;
    emergencyBox.classList.remove("hidden");
}

function renderResults(data) {
    const bestDisease = data.dataset_name || data.disease || "Not available";
    const confidence = data.confidence || "Not available";
    const severity = riskLabel(data.severity || "Not available");
    const medicine = data.medicine_advice || data.medicine || "Not available";
    const remedy = data.ayurvedic_remedy || data.remedy || "Not available";
    const diet = data.diet_advice || data.diet || "Not available";
    const herbs = data.herbs || "Not available";
    const precautions = data.precautions || "Not available";
    const riskLevel = data.risk_level || data.severity || "Not available";
    
    const predictions = Array.isArray(data.predictions) ? data.predictions : [];
    const top3Predictions = Array.isArray(data.top_3_predictions) ? data.top_3_predictions : [];

    // Extract MedlinePlus information
    const medlineplasInfo = data.medlineplus || {};
    const medlinePlusTitle = medlineplasInfo.title || bestDisease;
    const medlinePlusSummary = medlineplasInfo.summary || "No summary available from MedlinePlus.";
    const medlinePlusUrl = medlineplasInfo.url || "https://medlineplus.gov/";
    const relatedTopics = Array.isArray(medlineplasInfo.related_topics) ? medlineplasInfo.related_topics : [];

    // Build top predictions list from either top_3_predictions or predictions array
    const topList = top3Predictions.length
        ? `<ol class="predictions-list">${top3Predictions
            .map((item) => `<li>${item.disease_name || item.dataset_name || item.disease_prediction} (${item.confidence})</li>`)
            .join("")}</ol>`
        : predictions.length
        ? `<ol class="predictions-list">${predictions
            .map((item) => `<li>${item.dataset_name || item.disease_prediction} (${item.confidence})</li>`)
            .join("")}</ol>`
        : "<p>Not available</p>";

    // Build MedlinePlus section
    const medlinePlusSection = `
        <article class="result-box medlineplus-section">
            <h3>📚 MedlinePlus - ${medlinePlusTitle}</h3>
            <p>${medlinePlusSummary}</p>
            ${relatedTopics.length > 0 ? `
                <div class="related-topics">
                    <p><strong>Related Topics:</strong> ${relatedTopics.join(", ")}</p>
                </div>
            ` : ""}
        </article>
    `;

    results.innerHTML = `
        <article class="result-box">
            <h3>🦠 Possible Disease</h3>
            <p>${bestDisease} (${confidence})</p>
        </article>
        <article class="result-box">
            <h3>📊 Top 3 Predictions</h3>
            ${topList}
        </article>
        <article class="result-box">
            <h3>📊 Risk Level</h3>
            <p>${riskLevel}</p>
        </article>
        ${medlinePlusSection}
        <article class="result-box">
            <h3>💊 Medicine Advice</h3>
            <p>${medicine}</p>
        </article>
        <article class="result-box">
            <h3>🌿 Ayurvedic Remedy</h3>
            <p>${remedy}</p>
        </article>
        <article class="result-box">
            <h3>🥗 Diet Advice</h3>
            <p>${diet}</p>
        </article>
        <article class="result-box">
            <h3>🌿 Herbs</h3>
            <p>${herbs}</p>
        </article>
        <article class="result-box">
            <h3>⚠ Precautions</h3>
            <p>${precautions}</p>
        </article>
    `;

    renderEmergency(data.emergency_warning || "");
}

function renderError(message) {
    renderEmergency("");
    results.innerHTML = `
        <article class="result-box">
            <h3>Unable to Predict</h3>
            <p>${message}</p>
        </article>
    `;
}


function setActiveView(viewName) {
    const showChat = viewName === "chat";
    symptomView.classList.toggle("hidden", showChat);
    chatView.classList.toggle("hidden", !showChat);
    tabSymptom.classList.toggle("active", !showChat);
    tabChat.classList.toggle("active", showChat);
}


function renderChatHistory() {
    const html = chatMessages
        .map((item) => `<div class="chat-msg ${item.role}">${item.text}</div>`)
        .join("");

    chatHistory.innerHTML = html;
    chatHistoryFloat.innerHTML = html;

    chatHistory.scrollTop = chatHistory.scrollHeight;
    chatHistoryFloat.scrollTop = chatHistoryFloat.scrollHeight;
}


async function sendChatMessage(messageText) {
    const userMessage = String(messageText || "").trim();
    if (!userMessage) {
        return;
    }

    chatMessages.push({ role: "user", text: userMessage });
    renderChatHistory();

    chatInput.value = "";
    chatInputFloat.value = "";

    try {
        const response = await fetch(CHAT_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ message: userMessage }),
        });

        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Unable to get assistant response.");
        }

        chatMessages.push({ role: "bot", text: payload.reply || "I am here to help with general guidance." });
    } catch (error) {
        console.error("Chat error:", error);
        chatMessages.push({ role: "bot", text: "I'm currently unable to respond. Please try again later." });
    }

    renderChatHistory();
}

function setNlpStatus(message, isError = false) {
    nlpStatus.textContent = message;
    nlpStatus.style.color = isError ? "#b42318" : "";
}

async function loadSymptoms() {
    try {
        const response = await fetch(SYMPTOMS_URL);
        if (!response.ok) {
            throw new Error("Failed to load symptoms from server.");
        }

        const payload = await response.json();
        allSymptoms = Array.isArray(payload.symptoms) ? payload.symptoms : [];

        if (!allSymptoms.length) {
            renderError("No symptoms available from the dataset.");
        }
    } catch (error) {
        console.error("Symptoms load error:", error);
        renderError(error.message || "Unable to load symptom list.");
    }
}

async function analyzeNaturalLanguageSymptoms() {
    const text = symptomTextInput.value.trim();
    if (!text) {
        setNlpStatus("Please describe your symptoms before analysis.", true);
        return;
    }

    try {
        analyzeSymptomsButton.disabled = true;
        setNlpStatus("Analyzing your description...");

        const response = await fetch(EXTRACT_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ text }),
        });

        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Failed to analyze symptom text.");
        }

        const detected = Array.isArray(payload.symptoms) ? payload.symptoms : [];
        if (!detected.length) {
            setNlpStatus("No symptoms detected. Please try describing your symptoms more clearly.", true);
            return;
        }

        detected.forEach((symptom) => addSymptom(symptom));
        setNlpStatus(`Detected symptoms: ${detected.map((item) => toLabel(item)).join(", ")}`);
    } catch (error) {
        console.error("NLP extract error:", error);
        setNlpStatus(error.message || "Could not extract symptoms from text.", true);
    } finally {
        analyzeSymptomsButton.disabled = false;
    }
}

if (searchInput) {
    searchInput.addEventListener("input", () => {
        renderSuggestions(searchInput.value);
    });

    searchInput.addEventListener("keydown", (event) => {
        const items = suggestionsList ? Array.from(suggestionsList.querySelectorAll(".suggestion-item")) : [];

        if (event.key === "ArrowDown" && items.length) {
            event.preventDefault();
            highlightedSuggestionIndex = Math.min(highlightedSuggestionIndex + 1, items.length - 1);
            items[highlightedSuggestionIndex].focus();
            return;
        }

    if (event.key === "ArrowUp" && items.length) {
        event.preventDefault();
        highlightedSuggestionIndex = Math.max(highlightedSuggestionIndex - 1, 0);
        items[highlightedSuggestionIndex].focus();
        return;
    }

    if (event.key !== "Enter") {
        return;
    }

    const firstItem = suggestionsList.querySelector(".suggestion-item");
    if (!firstItem) {
        return;
    }

    event.preventDefault();
    const selected = firstItem.textContent.toLowerCase();
    addSymptom(selected);
    });
}

document.addEventListener("click", (event) => {
    if (!event.target.closest(".search-select")) {
        suggestionsList?.innerHTML && (suggestionsList.innerHTML = "");
        searchInput?.setAttribute("aria-expanded", "false");
    }
});

settingsBtn?.addEventListener("click", openSettings);

settingsClose?.addEventListener("click", closeSettings);

settingsOverlay?.addEventListener("click", closeSettings);

darkModeToggle?.addEventListener("change", () => {
    const enabled = darkModeToggle.checked;
    document.body.classList.toggle("dark-mode", enabled);
    localStorage.setItem(STORAGE_DARK_MODE, String(enabled));
});

colorBlindToggle?.addEventListener("change", () => {
    const enabled = colorBlindToggle.checked;
    document.body.classList.toggle("color-blind-mode", enabled);
    localStorage.setItem(STORAGE_COLOR_BLIND, String(enabled));
});

tabSymptom?.addEventListener("click", () => {
    setActiveView("symptom");
});

tabChat?.addEventListener("click", () => {
    setActiveView("chat");
    if (chatFloat) chatFloat.classList.add("hidden");
    if (chatFab) chatFab.setAttribute("aria-expanded", "false");
});

chatFab?.addEventListener("click", () => {
    if (!chatFloat) return;
    const open = chatFloat.classList.contains("hidden");
    chatFloat.classList.toggle("hidden", !open);
    if (chatFab) chatFab.setAttribute("aria-expanded", String(open));
});

chatSend?.addEventListener("click", async () => {
    if (chatInput) await sendChatMessage(chatInput.value);
});

chatSendFloat?.addEventListener("click", async () => {
    if (chatInputFloat) await sendChatMessage(chatInputFloat.value);
});

chatInput?.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        if (chatInput) await sendChatMessage(chatInput.value);
    }
});

chatInputFloat?.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        if (chatInputFloat) await sendChatMessage(chatInputFloat.value);
    }
});

if (analyzeSymptomsButton) {
    analyzeSymptomsButton.addEventListener("click", async () => {
        await analyzeNaturalLanguageSymptoms();
    });
}

if (symptomTextInput) {
    symptomTextInput.addEventListener("keydown", async (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            await analyzeNaturalLanguageSymptoms();
        }
    });
}

if (form) {
    form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const symptoms = Array.from(chosenSymptoms);
    if (!symptoms.length) {
        renderError("Please select at least one symptom.");
        return;
    }

    try {
        console.log("[PREDICT] Sending symptoms to API:", symptoms);
        
        const response = await fetch(API_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ symptoms }),
        });

        let data;
        try {
            data = await response.json();
        } catch (parseError) {
            throw new Error("Server returned an invalid response.");
        }

        if (!response.ok) {
            throw new Error(data.error || "Prediction request failed.");
        }

        console.log("[PREDICT] API Response received:", data);
        console.log("[PREDICT] MedlinePlus data:", data.medlineplus);
        console.log("[PREDICT] Top 3 Predictions:", data.top_3_predictions);

        renderResults(data);
    } catch (error) {
        console.error("Prediction error:", error);
        renderError(error.message || "Unexpected error occurred.");
    }
});

// ======================== LOGOUT HANDLER ========================
// Handle logout from index.html navigation
const logoutBtnNav = document.getElementById('logout-btn-nav');
if (logoutBtnNav) {
    logoutBtnNav.addEventListener('click', () => {
        sessionStorage.clear();
        localStorage.removeItem('remember_email');
        window.location.href = 'login.html';
    });
}

loadSymptoms();
applyThemePreferences();
renderChatHistory();
checkChatStatus();}
