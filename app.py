#!/usr/bin/env python3
"""手机活动上报服务：收 iOS 快捷指令的 POST，存 SQLite 小本本。"""

import os
import sqlite3
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)
CST = timezone(timedelta(hours=8))  # 北京时间
EXPECTED_TOKEN = os.environ.get("REPORT_TOKEN", "")  # 部署时设一个随机串当密码
DB_PATH = os.environ.get("DATA_DIR", "/tmp") + "/activity.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT NOT NULL,
            opened_at TEXT NOT NULL
        )
    """)
    return conn


def require_token():
    """没设密码就不查；设了就必须带对的 Bearer。"""
    if not EXPECTED_TOKEN:
        return None
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if token != EXPECTED_TOKEN:
        return jsonify({"error": "unauthorized"}), 401
    return None


@app.route("/report", methods=["POST"])
def report():
    err = require_token()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    app_name = data.get("app_name") or data.get("app") or "unknown"
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    conn.execute(
        "INSERT INTO phone_activity (app_name, opened_at) VALUES (?, ?)",
        (app_name, now),
    )
    # 小本本只留最近 100 条，旧的自动删掉
    conn.execute("""
        DELETE FROM phone_activity
        WHERE id NOT IN (
            SELECT id FROM phone_activity ORDER BY opened_at DESC LIMIT 100
        )
    """)
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@app.route("/activity", methods=["GET"])
def activity():
    err = require_token()
    if err:
        return err
    conn = get_db()
    rows = conn.execute(
        "SELECT app_name, opened_at FROM phone_activity ORDER BY opened_at DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify([{"app": r["app_name"], "time": r["opened_at"]} for r in rows])


@app.route("/activity/summary", methods=["GET"])
def activity_summary():
    """聚合一下：最后活跃时间 + 最近用过的 App。"""
    err = require_token()
    if err:
        return err
    conn = get_db()
    rows = conn.execute(
        "SELECT app_name, opened_at FROM phone_activity ORDER BY opened_at DESC LIMIT 100"
    ).fetchall()
    conn.close()
    if not rows:
        return jsonify({"last_active": None, "recent_apps": [], "count": 0})
    last_active = rows[0]["opened_at"]
    recent_apps = list(dict.fromkeys(r["app_name"] for r in rows[:10]))
    return jsonify({
        "last_active": last_active,
        "recent_apps": recent_apps,
        "count": len(rows),
    })


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
