# test deploy: fix route not found


# app.py
import os
from datetime import datetime, timezone
from flask import Flask, Blueprint, jsonify, request, redirect
from flask_cors import CORS

from dotenv import load_dotenv
load_dotenv()


# -------- 基本設定 --------
app = Flask(__name__)
# 先開放 /api/* 的跨網域；上線後把 origins 換成你的前端網域
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    allow_headers=["Authorization", "Content-Type"],
    methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
)


VERSION = os.getenv("APP_VERSION", "v4.0-alpha.2")

api_bp = Blueprint("api", __name__)

def now_iso_z():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# -------- 首頁 & 健康檢查 --------
@app.get("/")
def index():
    # 簡單 dashboard（可改成模板或前端靜態頁）
    return (
        f"<h1>FinBoard API</h1>"
        f"<p>version: {VERSION}</p>"
        f"<ul>"
        f"<li>GET /health</li>"
        f"<li>GET /api/price?symbol=USD/TWD</li>"
        f"<li>GET /api/price?symbol=2330.TW</li>"
        f"</ul>"
    ), 200

@app.get("/health")
def health():
    return jsonify(status="ok", version=VERSION, ts=now_iso_z()), 200

# -------- 新路由：/api/price --------
@api_bp.get("/price")
def get_price():
    # 相容 sym → symbol（前端應統一傳 symbol）
    symbol = request.args.get("symbol") or request.args.get("sym")
    if not symbol:
        return jsonify(error="missing 'symbol'"), 400

    # 這裡先回 mock；之後可接 twbank / yfinance / cache
    if "/" in symbol:
        price = 32.45   # 外匯 mock
        source = "mock:fx"
    else:
        price = 905.0   # 股票 mock
        source = "mock:stock"

    return jsonify(
        symbol=symbol,
        price=price,
        ts=now_iso_z(),
        source=source,
        version=VERSION,
    ), 200

# -------- 舊路由：/price_api（相容期導轉到新路徑）--------
@app.get("/price_api")
def legacy_price_api():
    symbol = request.args.get("symbol") or request.args.get("sym")
    # 永久導轉（觀察期可改 302）；也能在這裡直接 return get_price()
    target = f"/api/price?symbol={symbol}" if symbol else "/api/price"
    app.logger.info(f"[legacy] /price_api hit → redirect to {target}")
    return redirect(target, code=301)

# -------- Bearer Token 驗證（正式版）--------
REQUIRE_TOKEN = os.getenv("REQUIRE_TOKEN", "0").lower() in ("1", "true", "yes")
API_TOKEN     = os.getenv("API_TOKEN", "")

def require_auth(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not REQUIRE_TOKEN:
            return fn(*args, **kwargs)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify(error="missing bearer token"), 401
        token = auth.split(" ", 1)[1].strip()
        if token != API_TOKEN:
            return jsonify(error="invalid token"), 403
        return fn(*args, **kwargs)
    return wrapper


@api_bp.get("/auth/echo")
def auth_echo():
    # 判斷是否帶對的 Bearer Token；同時考慮是否有開啟強制驗證
    auth = request.headers.get("Authorization", "")
    token = ""
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1].strip()

    authorized = (not REQUIRE_TOKEN) or (token == API_TOKEN)

    return jsonify(
        authorized=authorized,
        ts=now_iso_z(),
        version=VERSION,
    ), 200



@api_bp.patch("/alerts/<int:alert_id>")
@require_auth
def update_alert(alert_id):
    payload = request.get_json(silent=True) or {}
    return jsonify(
        ok=True, alert_id=alert_id, updated=payload, ts=now_iso_z(), version=VERSION
    ), 200

# ---- 驗證回聲（前端 Save 後用來顯示 Auth: ok/error）----
@api_bp.get("/auth/echo")
def auth_echo():
    auth = request.headers.get("Authorization", "")
    token = ""
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1].strip()

    # REQUIRE_TOKEN=0 時即使沒帶 token 也視為 authorized
    authorized = (not REQUIRE_TOKEN) or (token == API_TOKEN)

    return jsonify(
        authorized=authorized,
        ts=now_iso_z(),
        version=VERSION,
    ), 200


# ---- Watchlist（暫時 mock，之後可接資料庫）----
@api_bp.get("/watchlist")
def get_watchlist():
    return jsonify([
        {"id": 1, "symbol": "USD/TWD"},
        {"id": 2, "symbol": "2330.TW"},
    ]), 200


# ---- Alerts 列表（暫時 mock）----
@api_bp.get("/alerts")
def get_alerts():
    return jsonify([
        {"id": 1, "symbol": "USD/TWD", "cond": ">", "name": "FX Alert", "enabled": True},
        {"id": 2, "symbol": "2330.TW", "cond": "<", "name": "Stock Alert", "enabled": False},
    ]), 200


@api_bp.get("/watchlist")
def get_watchlist():
    return jsonify([
        {"id": 1, "symbol": "USD/TWD"},
        {"id": 2, "symbol": "2330.TW"},
    ]), 200

@api_bp.get("/alerts")
def get_alerts():
    return jsonify([
        {"id": 1, "symbol": "USD/TWD", "cond": ">", "name": "FX Alert",   "enabled": True},
        {"id": 2, "symbol": "2330.TW",  "cond": "<", "name": "Stock Alert","enabled": False},
    ]), 200



# -------- Blueprint 註冊 --------
app.register_blueprint(api_bp, url_prefix="/api")

# -------- 本地執行 --------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("DEBUG", "0") == "1")


    # updated to fix 404 issue

