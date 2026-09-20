
# WeatherGPT 🌦️

A conversational AI-powered weather assistant that provides weather information, forecasts, and weather-related guidance through a user-friendly interface.

## Features

- Conversational weather assistance powered by Google Gemini.
- Location-based weather information.
- Current weather data using Open-Meteo.
- Fallback-based weather retrieval.
- Weather summaries and advisory responses.
- Interactive web dashboard.

> Note: IMD weather data integration is included as an experimental
> component, but the currently working weather retrieval uses Open-Meteo.

## Tech Stack

- **Backend:** Python, Flask
- **AI:** Google Gemini API
- **Weather Data:** Open-Meteo
- **Experimental Integration:** India Meteorological Department (IMD)
- **Geocoding:** GeoPy / Nominatim
- **Frontend:** HTML, CSS, JavaScript
- **HTTP Requests:** Requests
## Project Structure

```text
WeatherGPT/
├── app.py
├── requirements.txt
├── .gitignore
└── README.md
```

## Setup and Installation

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd WeatherGPT
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_api_key_here
```

Never publish your actual API key.

### 5. Run the application

```bash
python app.py
```

Open the local URL displayed in the terminal.

## Important Notes

- Weather information depends on external data providers.
- API keys should be stored securely in environment variables.
- This project was developed for the Smart India Hackathon 2026 internal selection.

## License

This project is currently intended for educational and hackathon purposes.