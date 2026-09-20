import json
import requests
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template_string
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from geopy.geocoders import Nominatim
import urllib3
import os
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. CONFIGURATION
# ==========================================
from google.generativeai.types import HarmCategory, HarmBlockThreshold

SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}


genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash')
geolocator = Nominatim(user_agent="weather_sih_clean_v4")

app = Flask(__name__)

# ==========================================
# 2. WEATHER & WARNING ENGINE
# ==========================================
def get_coordinates(location_name):
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        res = requests.get(url, params={"name": location_name, "count": 1}, timeout=5)
        data = res.json()
        if "results" in data and data["results"]:
            res_item = data["results"][0]
            return float(res_item["latitude"]), float(res_item["longitude"]), res_item.get("name", location_name)
    except Exception as e:
        print(f"[!] Geocoding error: {e}")
    return None, None, None


def fetch_imd_weather(lat, lon, location_name):
    """
    Attempt to fetch weather from the India Meteorological Department (IMD).
    Fails fast (3s timeout) to ensure the UI doesn't freeze if IMD is unreachable.
    """
    try:
        # Note: Replace this URL with the exact IMD endpoint/auth provided to you during SIH.
        # This is a generic IMD API structure representation.
        imd_url = "https://api.imd.gov.in/api/v1/cityforecast"
        headers = {"User-Agent": "WeatherGPT-SIH-Bot"}

        # We simulate a 3-second timeout. If IMD lags, we abandon it and go to Open-Meteo.
        res = requests.get(imd_url, headers=headers, timeout=3)

        if res.status_code == 200:
            data = res.json()
            # Map IMD's specific JSON keys to our app's standard format
            return {
                "source": "IMD (Govt. of India)",
                "location": location_name,
                "temperature": float(data.get("Today_Max_temp", 25.0)),
                "feels_like": float(data.get("Today_Max_temp", 25.0)),
                "humidity": float(data.get("Relative_Humidity_at_1730", 50)),
                "wind_speed": 5.0,
                "precipitation": float(data.get("Past_24_hrs_Rainfall", 0.0)),
                "weather_condition": data.get("Todays_Forecast", "Fair"),
                "aqi": 50,  # Note: AQI usually comes from CPCB, using placeholder
                "aqi_status": "Fair",
                "warnings": []
            }
    except Exception as e:
        print(f"[!] IMD API unreachable or station missing ({e}). Triggering Open-Meteo fallback...")

    return None  # Returning None triggers the Open-Meteo fallback


def fetch_open_meteo_fallback(lat, lon, location_name):
    """
    The reliable global fallback using Open-Meteo spatial grids.
    """
    try:
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&timezone=auto"
        air_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=european_aqi,pm2_5&timezone=auto"

        w_res = requests.get(weather_url, timeout=5).json()
        a_res = requests.get(air_url, timeout=5).json()

        current_w = w_res.get("current", {})
        current_a = a_res.get("current", {})

        wmo_map = {
            0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
            45: "Foggy", 48: "Rime Fog", 51: "Light Drizzle", 61: "Slight Rain",
            63: "Moderate Rain", 65: "Heavy Rain", 80: "Rain Showers", 95: "Thunderstorm"
        }
        condition = wmo_map.get(current_w.get("weather_code", 0), "Fair")

        aqi_val = current_a.get("european_aqi", 42)
        aqi_status = "Good"
        if aqi_val > 50: aqi_status = "Fair"
        if aqi_val > 100: aqi_status = "Moderate"
        if aqi_val > 150: aqi_status = "Unhealthy"

        temp = current_w.get("temperature_2m", 25.0)
        rain = current_w.get("precipitation", 0.0)
        wind = current_w.get("wind_speed_10m", 5.0)

        warnings = []
        if temp >= 40: warnings.append(f"Extreme Heat Warning: {temp}°C.")
        if rain >= 10: warnings.append(f"Heavy Rainfall Alert: {rain}mm.")
        if wind >= 40: warnings.append(f"High Wind Advisory: {wind} km/h.")
        if aqi_val >= 150: warnings.append(f"Air Quality Alert: AQI {aqi_val}.")

        return {
            "source": "Open-Meteo Fallback Grid",
            "location": location_name,
            "temperature": temp,
            "feels_like": current_w.get("apparent_temperature", temp),
            "humidity": current_w.get("relative_humidity_2m", 50),
            "wind_speed": wind,
            "precipitation": rain,
            "weather_condition": condition,
            "aqi": aqi_val,
            "aqi_status": aqi_status,
            "warnings": warnings
        }
    except Exception as e:
        print(f"[!] Critical Error: Both IMD and Fallback failed: {e}")
        return None


def fetch_comprehensive_weather(location_name):
    """
    Main Orchestrator: Attempts IMD first, falls back to Open-Meteo if IMD fails.
    """
    lat, lon, resolved_name = get_coordinates(location_name)
    if not lat or not lon:
        return None

    # Step 1: Attempt India Meteorological Department (Primary)
    weather_data = fetch_imd_weather(lat, lon, resolved_name)

    # Step 2: If IMD returns None (down, timed out, or no data), use Open-Meteo (Secondary)
    if not weather_data:
        weather_data = fetch_open_meteo_fallback(lat, lon, resolved_name)

    return weather_data


# ==========================================
# 3. CONTEXTUAL AI LOGIC
# ==========================================
def process_query_with_ai(user_prompt, current_location, context_history):
    prompt = f"""
    You are WeatherGPT, a helpful and polished weather assistant.
    Conversation History: {json.dumps(context_history[-4:])}
    Current Pinned Location: {current_location}
    New User Query: '{user_prompt}'

    Instructions:
    1. Look at the New User Query. Did the user mention or imply a *different* city, town, or location than the current pinned location? 
    2. If yes, extract that exact new location name into "detected_location". If no new location is mentioned, leave "detected_location" as an empty string "".
    3. Output ONLY a valid JSON string with NO markdown formatting, containing these exact keys:
    "detected_location": string,
    "persona": string (e.g. farmer, commuter, traveler, general),
    "activity": string (e.g. crop spraying, driving, tour)
    """
    try:
        raw_res = model.generate_content(prompt, safety_settings=SAFETY_SETTINGS).text.strip()
        raw_res = raw_res.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw_res)
    except Exception as e:
        print(f"[!] Parsing error: {e}")
        parsed = {"detected_location": "", "persona": "general", "activity": "general"}

    # Check if a new location was explicitly requested
    new_loc = parsed.get("detected_location", "").strip()
    target_location = new_loc if new_loc else current_location
    if not target_location:
        target_location = "New Delhi"

    weather_data = fetch_comprehensive_weather(target_location)
    if not weather_data:
        return {"error": f"Could not retrieve telemetry for '{target_location}'."}

    adv_prompt = f"""
    User Query: "{user_prompt}"
    Target Location: {weather_data['location']}
    Persona Profile: {parsed.get('persona')}
    Live Spatial Telemetry: {json.dumps(weather_data)}

    Provide a friendly, conversational, yet expert weather advisory based strictly on these exact metrics for {weather_data['location']}. Do not mention New Delhi unless New Delhi is the target location.
    """
    try:
        advisory = model.generate_content(adv_prompt, safety_settings=SAFETY_SETTINGS).text.strip()
    except Exception as e:
        advisory = f"Service Error: {str(e)}"

    return {
        "active_location": weather_data['location'],
        "intent": parsed,
        "weather": weather_data,
        "advisory": advisory
    }
# ==========================================
# 4. FLASK ROUTES & CHATGPT/GEMINI STYLE UI
# ==========================================
@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    data = request.json
    user_prompt = data.get("prompt", "")
    current_location = data.get("location", "New Delhi")
    context_history = data.get("history", [])

    if not user_prompt:
        return jsonify({"error": "Empty payload received."}), 400

    result = process_query_with_ai(user_prompt, current_location, context_history)
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@app.route('/')
def home():
    HTML_PAGE = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>WeatherGPT</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
        <style>
            :root {
                --bg-main: #212121;
                --bg-card: #2f2f2f;
                --bg-input: #2f2f2f;
                --border-color: rgba(255, 255, 255, 0.1);
                --text-main: #ececec;
                --text-muted: #9b9b9b;
                --accent: #10a37f;
                --warning-bg: rgba(239, 68, 68, 0.15);
                --warning-border: rgba(239, 68, 68, 0.4);
                --warning-text: #f87171;
            }

            * { box-sizing: border-box; }
            body, html {
                margin: 0; padding: 0;
                height: 100vh;
                background-color: var(--bg-main);
                color: var(--text-main);
                font-family: 'Inter', sans-serif;
                display: flex; flex-direction: column;
                align-items: center;
            }

            /* Header */
            .header {
                width: 100%; max-width: 900px;
                padding: 16px 24px;
                display: flex; justify-content: space-between; align-items: center;
                font-weight: 600; font-size: 1.1rem; color: #fff;
                border-bottom: 1px solid var(--border-color);
            }
            .location-badge {
                font-size: 0.85rem; font-weight: 400;
                background: rgba(255, 255, 255, 0.08);
                padding: 5px 12px; border-radius: 20px;
                color: var(--text-muted);
            }

            /* Main Container Layout */
            .main-container {
                flex-grow: 1; width: 100%; max-width: 900px;
                display: flex; flex-direction: column;
                overflow: hidden; position: relative;
            }

            /* Warning Banner Area */
            #warning-container {
                padding: 0 24px;
                margin-top: 16px;
                display: none;
            }
            .warning-banner {
                background-color: var(--warning-bg);
                border: 1px solid var(--warning-border);
                color: var(--warning-text);
                padding: 12px 18px; border-radius: 12px;
                font-size: 0.9rem; display: flex; align-items: center; gap: 10px;
            }

            /* Weather Summary Cards Strip */
            .weather-strip {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
                gap: 12px; padding: 16px 24px;
            }
            .mini-card {
                background: var(--bg-card);
                border: 1px solid var(--border-color);
                border-radius: 12px;
                padding: 14px 16px;
                display: flex; flex-direction: column; gap: 4px;
            }
            .mini-label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 500; }
            .mini-value { font-size: 1.35rem; font-weight: 600; color: #fff; }
            .mini-sub { font-size: 0.75rem; color: var(--text-muted); }

            /* Chat Stream Area */
            .chat-history {
                flex-grow: 1; overflow-y: auto;
                padding: 20px 24px 100px 24px;
                display: flex; flex-direction: column; gap: 20px;
                scroll-behavior: smooth;
            }

            .msg {
                max-width: 85%; padding: 14px 18px; border-radius: 16px;
                line-height: 1.6; font-size: 0.95rem;
            }
            .msg.user {
                background: var(--bg-card); color: #fff;
                align-self: flex-end; border-bottom-right-radius: 4px;
            }
            .msg.ai {
                background: transparent; color: var(--text-main);
                align-self: flex-start; padding-left: 0;
            }

            /* Input Area */
            .input-area {
                position: absolute; bottom: 0; left: 0; right: 0;
                padding: 20px 24px;
                background: linear-gradient(180deg, rgba(33,33,33,0) 0%, rgba(33,33,33,0.95) 40%);
            }
            .input-box {
                background-color: var(--bg-input);
                border-radius: 24px;
                display: flex; align-items: center;
                padding: 8px 8px 8px 20px;
                border: 1px solid var(--border-color);
                box-shadow: 0 8px 20px rgba(0,0,0,0.3);
            }
            .input-box input {
                flex-grow: 1; background: transparent; border: none;
                color: white; font-size: 1rem; font-family: inherit; outline: none;
            }
            .send-btn {
                background-color: #fff; color: #000;
                border: none; border-radius: 50%;
                width: 36px; height: 36px;
                display: flex; align-items: center; justify-content: center;
                cursor: pointer; transition: opacity 0.2s;
            }
            .send-btn:hover { opacity: 0.85; }
            .send-btn svg { width: 16px; height: 16px; fill: currentColor; }

            /* Typing Dots */
            .typing-dots { display: flex; gap: 4px; padding: 10px 0; }
            .dot { width: 7px; height: 7px; background: var(--text-muted); border-radius: 50%; animation: pulse 1.4s infinite ease-in-out both; }
            .dot:nth-child(2) { animation-delay: 0.2s; }
            .dot:nth-child(3) { animation-delay: 0.4s; }
            @keyframes pulse { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
        </style>
    </head>
    <body>

        <div class="header">
            <span>WeatherGPT</span>
            <span class="location-badge" id="header-loc">New Delhi</span>
        </div>

        <div class="main-container">
            <!-- Dynamic Warning Banner -->
            <div id="warning-container">
                <div class="warning-banner" id="warning-text">⚠️ Warning message goes here.</div>
            </div>

            <!-- Weather Cards Strip (Default: New Delhi) -->
            <div class="weather-strip">
                <div class="mini-card">
                    <span class="mini-label">Temperature</span>
                    <span class="mini-value" id="card-temp">--°C</span>
                    <span class="mini-sub" id="card-feels">Feels like --°C</span>
                </div>
                <div class="mini-card">
                    <span class="mini-label">Condition</span>
                    <span class="mini-value" id="card-cond" style="font-size: 1.1rem; margin-top: 4px;">--</span>
                    <span class="mini-sub" id="card-source">Live Grid</span>
                </div>
                <div class="mini-card">
                    <span class="mini-label">Wind Speed</span>
                    <span class="mini-value" id="card-wind">-- km/h</span>
                    <span class="mini-sub">Surface vector</span>
                </div>
                <div class="mini-card">
                    <span class="mini-label">Air Quality (AQI)</span>
                    <span class="mini-value" id="card-aqi">--</span>
                    <span class="mini-sub" id="card-aqi-status">Calibrating</span>
                </div>
                <div class="mini-card">
                    <span class="mini-label">Precipitation</span>
                    <span class="mini-value" id="card-rain">-- mm</span>
                    <span class="mini-sub">Accumulation</span>
                </div>
            </div>

            <!-- Chat Stream -->
            <div class="chat-history" id="chatbox">
                <div class="msg ai">
                    Hello! I'm WeatherGPT. Current conditions for New Delhi are loaded above. Ask me anything or mention any town or city globally to switch locations instantly.
                </div>
            </div>

            <!-- Input Bar -->
            <div class="input-area">
                <div class="input-box">
                    <input type="text" id="user-input" placeholder="Ask a weather question or type a location..." onkeypress="if(event.key==='Enter') submitQuery()">
                    <button class="send-btn" onclick="submitQuery()">
                        <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                    </button>
                </div>
            </div>
        </div>

        <script>
            let currentActiveLocation = "New Delhi";
            let conversationHistory = [];

            // Fetch New Delhi weather automatically upon loading page
            window.addEventListener('DOMContentLoaded', () => {
                fetchInitialWeather();
            });

            async function fetchInitialWeather() {
                try {
                    const res = await fetch('/api/chat', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            prompt: "Provide status summary for New Delhi",
                            location: "New Delhi",
                            history: []
                        })
                    });
                    const data = await res.json();
                    if(!data.error) {
                        updateWeatherCards(data.weather);
                    }
                } catch(e) {
                    console.error("Initial load error", e);
                }
            }

            function updateWeatherCards(w) {
                currentActiveLocation = w.location;
                document.getElementById('header-loc').innerText = w.location;
                document.getElementById('card-temp').innerText = w.temperature + '°C';
                document.getElementById('card-feels').innerText = 'Feels like ' + w.feels_like + '°C';
                document.getElementById('card-cond').innerText = w.weather_condition;
                document.getElementById('card-source').innerText = w.source;
                document.getElementById('card-wind').innerText = w.wind_speed + ' km/h';
                document.getElementById('card-aqi').innerText = w.aqi;
                document.getElementById('card-aqi-status').innerText = 'Status: ' + w.aqi_status;
                document.getElementById('card-rain').innerText = w.precipitation + ' mm';

                // Handle warning banner display
                const warningContainer = document.getElementById('warning-container');
                const warningText = document.getElementById('warning-text');
                if (w.warnings && w.warnings.length > 0) {
                    warningText.innerHTML = `⚠️ ${w.warnings.join(' | ')}`;
                    warningContainer.style.display = 'block';
                } else {
                    warningContainer.style.display = 'none';
                }
            }

            function appendMessage(text, sender) {
        const chatbox = document.getElementById('chatbox');
        const div = document.createElement('div');
        div.className = `msg ${sender}`;
        
        // Use marked.js for AI responses to render bold/bullets correctly
        if (sender === 'ai') {
            div.innerHTML = marked.parse(text);
        } else {
            // Keep user messages as standard text (Note the DOUBLE backslash here for Python strings!)
            div.innerHTML = text.replace(/\\n/g, '<br>');
        }
        
        chatbox.appendChild(div);
        chatbox.scrollTop = chatbox.scrollHeight;
        conversationHistory.push({role: sender, content: text});
    }

            function showTyping() {
                const chatbox = document.getElementById('chatbox');
                const div = document.createElement('div');
                div.id = 'typing';
                div.className = 'msg ai';
                div.innerHTML = `<div class="typing-dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>`;
                chatbox.appendChild(div);
                chatbox.scrollTop = chatbox.scrollHeight;
            }

            function removeTyping() {
                const el = document.getElementById('typing');
                if(el) el.remove();
            }

            async function submitQuery() {
    const input = document.getElementById('user-input');
    const prompt = input.value.trim();
    if(!prompt) return;

    appendMessage(prompt, 'user');
    input.value = '';
    input.disabled = true;

    showTyping();

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                prompt: prompt,
                location: currentActiveLocation, // Send current state; backend AI will override if a new city is detected
                history: conversationHistory
            })
        });
        
        removeTyping();
        const data = await res.json();
        
        if(data.error) {
            appendMessage(data.error, 'ai');
        } else {
            // Update active location state globally on the frontend
            currentActiveLocation = data.active_location;
            updateWeatherCards(data.weather);
            appendMessage(data.advisory, 'ai');
        }
    } catch(e) {
        removeTyping();
        appendMessage("Network connection error. Please try again.", 'ai');
    }

    input.disabled = false;
    input.focus();
}
        </script>
    </body>
    </html>
    """
    return render_template_string(HTML_PAGE)


if __name__ == '__main__':
    app.run(debug=True, port=5000)