from flask import Flask, render_template, jsonify, request
import random
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'sensor_data.db')

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))

# ─── DB ──────────────────────────────────────────────────────────────────────

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor      TEXT    NOT NULL,
                value       REAL    NOT NULL,
                unit        TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'normal',
                recorded_at TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                rating      INTEGER NOT NULL,
                category    TEXT    NOT NULL,
                sensor      TEXT    NOT NULL DEFAULT 'general',
                message     TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_readings_sensor ON sensor_readings(sensor);
            CREATE INDEX IF NOT EXISTS idx_readings_time   ON sensor_readings(recorded_at);
        """)

# ─── Sensor helpers ──────────────────────────────────────────────────────────

SENSOR_CFG = {
    "temperature": {"unit": "°C",   "min": 18,  "max": 35,   "warn": 28,  "crit": 32},
    "humidity":    {"unit": "%",    "min": 30,  "max": 80,   "warn": 65,  "crit": 75},
    "pressure":    {"unit": "hPa",  "min": 980, "max": 1030, "warn": None,"crit": None},
    "light":       {"unit": "lux",  "min": 0,   "max": 1000, "warn": None,"crit": None},
    "air_quality": {"unit": "AQI",  "min": 0,   "max": 500,  "warn": 100, "crit": 200},
    "vibration":   {"unit": "mm/s", "min": 0,   "max": 10,   "warn": 5,   "crit": 8},
}

GENERATORS = {
    "temperature": lambda: round(random.uniform(18, 35), 1),
    "humidity":    lambda: round(random.uniform(30, 80), 1),
    "pressure":    lambda: round(random.uniform(980, 1030), 1),
    "light":       lambda: round(random.uniform(0, 1000), 0),
    "air_quality": lambda: round(random.uniform(0, 500), 0),
    "vibration":   lambda: round(random.uniform(0, 10), 2),
}

def get_status(sensor, value):
    cfg = SENSOR_CFG[sensor]
    if cfg["crit"] and value >= cfg["crit"]: return "critical"
    if cfg["warn"] and value >= cfg["warn"]: return "warning"
    return "normal"

def generate_and_save():
    now = datetime.now()
    result = {"timestamp": now.strftime("%H:%M:%S"), "date": now.strftime("%Y-%m-%d")}
    rows = []
    for sensor, gen in GENERATORS.items():
        value  = gen()
        status = get_status(sensor, value)
        cfg    = SENSOR_CFG[sensor]
        result[sensor] = {"value": value, "unit": cfg["unit"],
                          "min": cfg["min"], "max": cfg["max"], "status": status}
        rows.append((sensor, value, cfg["unit"], status))
    with get_db() as db:
        db.executemany(
            "INSERT INTO sensor_readings (sensor, value, unit, status) VALUES (?,?,?,?)", rows)
        db.execute(
            "DELETE FROM sensor_readings WHERE recorded_at < datetime('now','-7 days','localtime')")
    return result

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/sensors")
def api_sensors():
    return jsonify(generate_and_save())

@app.route("/api/history")
def api_history():
    history = {s: [] for s in SENSOR_CFG}
    with get_db() as db:
        for sensor in SENSOR_CFG:
            rows = db.execute(
                """SELECT value FROM (
                       SELECT value, recorded_at FROM sensor_readings
                       WHERE sensor=? ORDER BY recorded_at DESC LIMIT 50
                   ) ORDER BY recorded_at ASC""", (sensor,)).fetchall()
            history[sensor] = [r["value"] for r in rows]
    return jsonify(history)

@app.route("/api/records")
def api_records():
    page     = max(1, int(request.args.get("page", 1)))
    per_page = int(request.args.get("per_page", 20))
    sensor   = request.args.get("sensor", "all")
    offset   = (page - 1) * per_page
    with get_db() as db:
        if sensor == "all":
            total = db.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
            rows  = db.execute(
                "SELECT * FROM sensor_readings ORDER BY recorded_at DESC LIMIT ? OFFSET ?",
                (per_page, offset)).fetchall()
        else:
            total = db.execute(
                "SELECT COUNT(*) FROM sensor_readings WHERE sensor=?", (sensor,)).fetchone()[0]
            rows  = db.execute(
                "SELECT * FROM sensor_readings WHERE sensor=? ORDER BY recorded_at DESC LIMIT ? OFFSET ?",
                (sensor, per_page, offset)).fetchall()
    return jsonify({"total": total, "page": page, "per_page": per_page,
                    "pages": (total + per_page - 1) // per_page,
                    "rows": [dict(r) for r in rows]})

@app.route("/api/stats")
def api_stats():
    with get_db() as db:
        stats = {}
        for sensor in SENSOR_CFG:
            row = db.execute(
                """SELECT COUNT(*) as cnt, ROUND(AVG(value),2) as avg,
                          ROUND(MIN(value),2) as min, ROUND(MAX(value),2) as max
                   FROM sensor_readings
                   WHERE sensor=? AND recorded_at >= datetime('now','-24 hours','localtime')""",
                (sensor,)).fetchone()
            stats[sensor] = dict(row)
        total_readings = db.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
        total_feedback = db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    return jsonify({"sensors": stats, "total_readings": total_readings,
                    "total_feedback": total_feedback})

@app.route("/api/feedback", methods=["POST"])
def post_feedback():
    body = request.json or {}
    rating, category = body.get("rating"), body.get("category")
    if not rating or not category:
        return jsonify({"success": False, "error": "rating and category required"}), 400
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO feedback (rating, category, sensor, message) VALUES (?,?,?,?)",
            (rating, category, body.get("sensor", "general"), body.get("message", "")))
    return jsonify({"success": True, "id": cur.lastrowid})

@app.route("/api/feedback", methods=["GET"])
def get_feedback():
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC LIMIT 20").fetchall()
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
