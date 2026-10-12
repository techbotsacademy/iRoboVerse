from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime, timedelta
from pathlib import Path
import json
import threading
import time

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "tasks.json"

DEFAULT_TASKS = [
    {
        "id": 1,
        "name": "Morning exercise",
        "time": "08:00",
        "status": "pending",
        "misses": 0,
        "enabled": True
    },
    {
        "id": 2,
        "name": "Drink water",
        "time": "10:00",
        "status": "pending",
        "misses": 0,
        "enabled": True
    },
    {
        "id": 3,
        "name": "Take a break",
        "time": "14:00",
        "status": "pending",
        "misses": 0,
        "enabled": True
    }
]

lock = threading.Lock()


def load_tasks():
    if not DATA_FILE.exists():
        save_tasks(DEFAULT_TASKS)
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_tasks(tasks):
    DATA_FILE.write_text(
        json.dumps(tasks, indent=2),
        encoding="utf-8"
    )


@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/api/tasks")
def get_tasks():
    with lock:
        return jsonify(load_tasks())


@app.post("/api/tasks/<int:task_id>/complete")
def complete_task(task_id):
    with lock:
        tasks = load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                task["status"] = "completed"
                task["misses"] = 0
                save_tasks(tasks)
                return jsonify({
                    "message": "Task marked completed",
                    "task": task
                })
    return jsonify({"error": "Task not found"}), 404


@app.post("/api/tasks/<int:task_id>/missed")
def miss_task(task_id):
    with lock:
        tasks = load_tasks()
        for task in tasks:
            if task["id"] == task_id:
                task["status"] = "missed"
                task["misses"] += 1

                if task["misses"] >= 3:
                    task["alert"] = (
                        "Caretaker alert required: "
                        "three consecutive misses."
                    )
                else:
                    task["alert"] = None

                # Demo policy: retry in 15 minutes.
                next_time = datetime.now() + timedelta(minutes=15)
                task["time"] = next_time.strftime("%H:%M")
                task["status"] = "pending"

                save_tasks(tasks)
                return jsonify({
                    "message": "Task rescheduled for 15 minutes later",
                    "task": task,
                    "caretaker_alert": task.get("alert")
                })
    return jsonify({"error": "Task not found"}), 404


@app.get("/api/due")
def due_tasks():
    now = datetime.now().strftime("%H:%M")
    with lock:
        tasks = load_tasks()
        due = [
            task for task in tasks
            if task["enabled"]
            and task["time"] == now
            and task["status"] == "pending"
        ]
    return jsonify(due)


if __name__ == "__main__":
    load_tasks()
    app.run(host="127.0.0.1", port=8001, debug=False)
