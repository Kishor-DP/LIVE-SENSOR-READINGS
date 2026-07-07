# SensorGrid — Flask Sensor Dashboard

A real-time sensor monitoring dashboard with user feedback system.

## Features
- 📊 Live sensor cards: Temperature, Humidity, Pressure, Light, Air Quality, Vibration
- 📈 Sparkline history per sensor + trend charts
- 🚨 Status indicators: Normal / Warning / Critical with color coding
- 💬 User feedback form (rating, category, sensor, message)
- 📋 Feedback log with last 10 submissions

## Setup & Run

```bash
# 1. Navigate to project folder
cd ex.sensor_dashboard

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py

# 4. Open in browser
# http://localhost:5000
```

## Sensor Data API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sensors` | GET | Live sensor readings |
| `/api/history` | GET | Last 20 readings per sensor |
| `/api/feedback` | POST | Submit user feedback |
| `/api/feedback` | GET | Get recent feedback |

### Feedback POST body example:
```json
{
  "rating": 4,
  "category": "accuracy",
  "sensor": "temperature",
  "message": "Temperature readings seem slightly high"
}
```

## Connecting Real Sensors
Replace the `generate_sensor_data()` function in `app.py` with actual sensor SDK calls.
Example integrations: Raspberry Pi GPIO, Arduino Serial, MQTT broker, REST sensor APIs.

## Customization
- Adjust sensor thresholds in the `get_status()` function
- Add new sensors by extending `SENSORS` dict
- Persist feedback by replacing `feedback_store` list with SQLite/PostgreSQL
