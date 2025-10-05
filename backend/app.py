# -*- coding: utf-8 -*-
import os, re, math, sqlite3
from contextlib import contextmanager
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "finboard.db")
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dashboard")
API_TOKEN = os.getenv("API_TOKEN", "DEMO-TOKEN")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="/dashboard")
CORS(app, resources={r"/api/*": {"origins": "*"}})

@contextmanager
def db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

SCHEMA_ALERTS = '''
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 0,
    symbol TEXT NOT NULL,
    symbol_norm TEXT NOT NULL,
    cond TEXT,
    name TEXT,
    enabled INTEGER DEFAULT 1,
    last_triggered_ts INTEGER,
    created_ts INTEGER,
    updated_ts INTEGER
);
'''
SCHEMA_WATCHLIST = '''
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 0,
    symbol TEXT NOT NULL,
    symbol_norm TEXT NOT NULL,
    label TEXT,
    created_ts INTEGER,
    updated_ts INTEGER
);
'''

def init_db():
    with db_conn() as conn:
        c = conn.cursor()
        c.execute(SCHEMA_ALERTS)
        c.execute(SCHEMA_WATCHLIST)
        conn.commit()

_alias_map = {"BTC":"BTC-USD","BTCUSD":"BTC-USD","ETH":"ETH-USD","ETHUSD":"ETH-USD","TSMC":"2330.TW"}
_fx_pat = re.compile(r"^([A-Z]{3})/([A-Z]{3})$")
def normalize_symbol(raw: str) -> str:
    s = raw.strip().upper()
    m = _fx_pat.match(s)
    if m: return f"{m.group(1)}{m.group(2)}=X"
    return _alias_map.get(s, s)

def price_of(symbol_or_pair: str):
    ticker = normalize_symbol(symbol_or_pair)
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        p = float(info.last_price) if hasattr(info, "last_price") and info.last_price is not None else None
        if p is None:
            hist = t.history(period="1d")
            if not hist.empty: p = float(hist["Close"].iloc[-1])
        if p is None or math.isnan(p): return None
        return round(p, 6)
    except Exception:
        return None

def require_token():
    auth = request.headers.get("Authorization", "")
    return auth.startswith("Bearer ") and auth.split(" ",1)[1].strip() == API_TOKEN

@app.route("/api/auth/echo")
def auth_echo():
    return jsonify({"authorized": require_token()})

@app.route("/api/watchlist", methods=["GET","POST"])
def watchlist():
    init_db()
    if request.method == "GET":
        with db_conn() as conn:
            rows = conn.execute("SELECT id,symbol,symbol_norm,COALESCE(label,'') AS label FROM watchlist WHERE user_id=0 ORDER BY id DESC").fetchall()
        return jsonify([dict(r) for r in rows])
    if not require_token(): return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    sym = (data.get("symbol") or "").strip()
    label = (data.get("label") or "").strip()
    if not sym: return jsonify({"error":"symbol required"}), 400
    norm = normalize_symbol(sym); now_ts = int(datetime.utcnow().timestamp())
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO watchlist(user_id,symbol,symbol_norm,label,created_ts,updated_ts) VALUES(0,?,?,?, ?,?)",(sym,norm,label,now_ts,now_ts))
        conn.commit()
        row = conn.execute("SELECT id,symbol,symbol_norm,COALESCE(label,'') AS label FROM watchlist WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201

@app.route("/api/watchlist/<int:iid>", methods=["DELETE"])
def watchlist_del(iid:int):
    init_db()
    if not require_token(): return jsonify({"error":"unauthorized"}), 401
    with db_conn() as conn:
        conn.execute("DELETE FROM watchlist WHERE id=? AND user_id=0", (iid,)); conn.commit()
    return jsonify({"ok": True})

@app.route("/api/alerts")
def alerts_list():
    init_db()
    with db_conn() as conn:
        rows = conn.execute("SELECT id,symbol,symbol_norm,COALESCE(name,'') AS name,COALESCE(cond,'') AS cond,enabled,COALESCE(last_triggered_ts,0) AS last_triggered_ts FROM alerts WHERE user_id=0 ORDER BY id DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/alerts/<int:aid>", methods=["PATCH"])
def alerts_patch(aid:int):
    init_db()
    if not require_token(): return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    fields=[]; params=[]
    if "enabled" in data: fields.append("enabled=?"); params.append(1 if data.get("enabled") else 0)
    if "name" in data: fields.append("name=?"); params.append(str(data.get("name") or ""))
    if "cond" in data: fields.append("cond=?"); params.append(str(data.get("cond") or ""))
    if not fields: return jsonify({"error":"no fields"}), 400
    fields.append("updated_ts=?"); params.append(int(datetime.utcnow().timestamp()))
    params.extend([aid,0])
    with db_conn() as conn:
        conn.execute(f"UPDATE alerts SET {', '.join(fields)} WHERE id=? AND user_id=?", params); conn.commit()
        row = conn.execute("SELECT id,symbol,symbol_norm,COALESCE(name,'') AS name,COALESCE(cond,'') AS cond,enabled,COALESCE(last_triggered_ts,0) AS last_triggered_ts FROM alerts WHERE id=?", (aid,)).fetchone()
    return jsonify(dict(row) if row else {"ok": True})

@app.route("/api/price")
def price_api():
    sym = (request.args.get("symbol") or "").strip()
    if not sym: return jsonify({"error":"symbol required"}), 400
    p = price_of(sym)
    return jsonify({"symbol": sym, "price": p, "ok": p is not None})

@app.route("/dashboard")
def dashboard():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/")
def root():
    return jsonify({"name":"FinBoard v4.0-alpha.1","dashboard":"/dashboard","auth":"set API_TOKEN env; send Bearer token for write ops"})

if __name__ == "__main__":
    init_db()
    with db_conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 0:
            now_ts = int(datetime.utcnow().timestamp())
            demo = [("2330.TW","2330.TW","TSMC"),("USD/TWD","USDTWD=X","USD/TWD"),("BTC-USD","BTC-USD","Bitcoin"),("AAPL","AAPL","Apple")]
            for s,n,lbl in demo:
                conn.execute("INSERT INTO watchlist(user_id,symbol,symbol_norm,label,created_ts,updated_ts) VALUES(0,?,?,?, ?,?)",(s,n,lbl,now_ts,now_ts))
        if conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0:
            now_ts = int(datetime.utcnow().timestamp())
            demo_a = [("USD/TWD","USDTWD=X","美元破位買進","price >= 33.0",1),("2330.TW","2330.TW","TSMC 買點","price <= 800",0)]
            for s,norm,name,cond,en in demo_a:
                conn.execute("INSERT INTO alerts(user_id,symbol,symbol_norm,name,cond,enabled,created_ts,updated_ts) VALUES(0,?,?,?,?,?, ?,?)",(s,norm,name,cond,en,now_ts,now_ts))
        conn.commit()
    app.run(host="0.0.0.0", port=5000, debug=True)
