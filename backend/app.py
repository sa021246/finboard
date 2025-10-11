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
CORS(app, resources={r"/api/*": {"origins": "*"}})

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

# --------（預留）權限樣板：Bearer Token 驗證 --------
def require_token():
    """第4階段要用的簡易驗證；現在先不啟用。
    將 REQUIRE_TOKEN 設為 '1' 才會強制檢查。
    """
    if os.getenv("REQUIRE_TOKEN") != "1":
        return None  # 不檢查
    auth = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not auth.startswith(prefix):
        return jsonify(error="missing bearer token"), 401
    token = auth[len(prefix):].strip()
    # TODO: 驗證 token（查 DB / 比對簽章）
    if token != os.getenv("API_TOKEN", "dev-token"):
        return jsonify(error="invalid token"), 403
    return None

@api_bp.patch("/alerts/<int:alert_id>")
def update_alert(alert_id):
    # 範例：啟用時才驗證
    err = require_token()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    # TODO: 真實更新邏輯
    return jsonify(
        ok=True, alert_id=alert_id, updated=payload, ts=now_iso_z(), version=VERSION
    ), 200

# -------- Blueprint 註冊 --------
app.register_blueprint(api_bp, url_prefix="/api")

# -------- 本地執行 --------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("DEBUG", "0") == "1")
