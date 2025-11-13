# test deploy: fix route not found


# app.py
import os
from datetime import datetime, timezone, timedelta
from flask import Flask, Blueprint, jsonify, request, redirect, current_app
from flask_cors import CORS

from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity


from dotenv import load_dotenv
load_dotenv()

from functools import wraps

import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash, check_password_hash
import jwt


# -------- 基本設定 --------
app = Flask(__name__)


# JWT 秘鑰（讀環境變數 JWT_SECRET；沒有就報錯）
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("Missing env var JWT_SECRET")
app.config["JWT_SECRET_KEY"] = JWT_SECRET  # Flask-JWT-Extended 讀這個
jwt = JWTManager(app)


# 先開放 /api/* 的跨網域；上線後把 origins 換成你的前端網域
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    allow_headers=["Authorization", "Content-Type"],
    methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
)


DB_PATH = 'finboard.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        plan TEXT DEFAULT 'FREE',
        expire_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()


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
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # 讓 CORS 預檢通過
        if request.method == "OPTIONS":
            return ("", 204)

        if not REQUIRE_TOKEN:
            return fn(*args, **kwargs)
        
        # ✅ 驗證 Bearer Token
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify(error="missing bearer token"), 401
        token = auth.split(" ", 1)[1].strip()
        if token != API_TOKEN:
            return jsonify(error="invalid token"), 403

        return fn(*args, **kwargs)
    return wrapper





@api_bp.patch("/alerts/<int:alert_id>")
@require_auth
def update_alert(alert_id):
    payload = request.get_json(silent=True) or {}
    return jsonify(
        ok=True, alert_id=alert_id, updated=payload, ts=now_iso_z(), version=VERSION
    ), 200



# ---- Auth Echo ----
@api_bp.get("/auth/echo")
def auth_echo():
    auth = request.headers.get("Authorization", "")
    token = auth.split(" ", 1)[1].strip() if auth.startswith("Bearer ") else ""
    authorized = (not REQUIRE_TOKEN) or (token == API_TOKEN)
    return jsonify(authorized=authorized, version=VERSION, ts=now_iso_z()), 200


# ==== Auth: register/login (keep this one) ====
import jwt
from werkzeug.security import generate_password_hash, check_password_hash

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-to-real-secret")


def ensure_user_table():
    conn = get_db()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT,
        password_hash TEXT NOT NULL,
        plan TEXT DEFAULT 'FREE',
        expire_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT
    )
    """)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()

ensure_user_table()


def create_token(user):
    # 你原本 payload 帶 user_id/username/plan 和 12 小時效期
    claims = {
        "username": user["username"],
        "plan": user["plan"],
    }
    # 12 小時效期維持不變
    token = create_access_token(identity=int(user["id"]), additional_claims=claims, expires_delta=timedelta(hours=12))
    return token



def get_user_by_username(username):
    conn = get_db()
    cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    conn.close()
    return user


@api_bp.post("/auth/register")
def api_register():
    data = request.get_json() or {}
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    if get_user_by_username(username):
        return jsonify({"error": "username already exists"}), 400

    password_hash = generate_password_hash(password)

    conn = get_db()
    conn.execute(
        "INSERT INTO users (username, password_hash, plan, email) VALUES (?, ?, ?, ?)",
        (username, password_hash, "FREE", email),
    )
    conn.commit()
    conn.close()

    user = get_user_by_username(username)
    token = create_token(user)
    return jsonify({
        "ok": True,
        "token": token,
        "user": {
            "username": user["username"],
            "plan": user["plan"],
            "expire_at": user["expire_at"]
        }
    }), 201


@api_bp.post("/auth/login")
def api_login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    user = get_user_by_username(username)
    if not user:
        return jsonify({"error": "user not found"}), 404

    if not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "invalid password"}), 401

    token = create_token(user)
    return jsonify({
        "ok": True,
        "token": token,
        "user": {
            "username": user["username"],
            "plan": user["plan"],
            "expire_at": user["expire_at"]
        }
    })


# ==== Auth: status / upgrade / check ====
from flask import g

from flask import request, jsonify
import jwt
from datetime import datetime

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")  # 你原本怎麼寫就用原本的




# 你的 secret，照你原本的來源來：
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")  # 例如這樣，照你實際的為主


def _decode_token_and_get_user():
    """解析 JWT，並從 DB 取得使用者資料"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, (jsonify({"error": "missing token"}), 401)

    token = auth_header.split(" ", 1)[1]

    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None, (jsonify({"error": "token expired"}), 401)
    except Exception:
        return None, (jsonify({"error": "invalid token"}), 401)

    username = data.get("username")
    if not username:
        return None, (jsonify({"error": "invalid token"}), 401)

    # 在 JSON DB 中找使用者
    user = db["users"].get(username)
    if not user:
        return None, (jsonify({"error": "user not found"}), 404)

    return user, None




@api_bp.get("/auth/status")
def auth_status():
    """查目前方案與剩餘天數"""
    user, err = _decode_token_and_get_user()
    if err:
        return err

    expire_at = user["expire_at"]
    remaining_days = None
    is_active = False
    if expire_at:
        try:
            dt = datetime.fromisoformat(expire_at)
            delta = dt - datetime.utcnow()
            remaining_days = max(0, delta.days)
            is_active = delta.total_seconds() > 0 and user["plan"] != "FREE"
        except Exception:
            pass

    return jsonify({
        "ok": True,
        "user": {
            "username": user["username"],
            "plan": user["plan"],
            "expire_at": expire_at,
            "remaining_days": remaining_days,
            "is_active": is_active
        }
    }), 200


@api_bp.post("/auth/upgrade")
def auth_upgrade():
    """
    模擬升級成付費方案：
    body: { "plan": "PRO" | "PREMIUM", "days": 30 }
    """
    user, err = _decode_token_and_get_user()
    if err:
        return err

    data = request.get_json() or {}
    plan = (data.get("plan") or "PRO").upper()
    days = int(data.get("days") or 30)
    if plan not in ("PRO", "PREMIUM"):
        return jsonify({"error": "invalid plan"}), 400
    if days <= 0:
        return jsonify({"error": "invalid days"}), 400

    new_expire = (datetime.utcnow() + timedelta(days=days)).isoformat(timespec="seconds")

    conn = get_db()
    conn.execute(
        "UPDATE users SET plan = ?, expire_at = ?, updated_at = ? WHERE id = ?",
        (plan, new_expire, datetime.utcnow().isoformat(timespec="seconds"), user["id"])
    )
    conn.commit()
    conn.close()

    # 重新取使用者並簽新 token（把 plan 帶在 payload）
    conn = get_db()
    cur = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
    updated = cur.fetchone()
    conn.close()

    new_token = create_token(updated)

    return jsonify({
        "ok": True,
        "message": f"upgraded to {plan} for {days} days",
        "token": new_token,
        "user": {
            "username": updated["username"],
            "plan": updated["plan"],
            "expire_at": updated["expire_at"]
        }
    }), 200


@api_bp.get("/auth/check")
def auth_check():
    """最輕量檢查：token 是否有效、是否需要續期"""
    user, err = _decode_token_and_get_user()
    if err:
        # err 是 (response, status) 形式
        resp, status = err
        # 403（需續費）時順便回 need_renew=true
        payload = resp.get_json() if hasattr(resp, "get_json") else {}
        return jsonify({
            "ok": False,
            "authorized": False,
            "need_renew": bool(payload.get("need_renew")),
            "error": payload.get("error", "unauthorized")
        }), status

    need_renew = False
    if user["expire_at"]:
        try:
            dt = datetime.fromisoformat(user["expire_at"])
            need_renew = (dt - datetime.utcnow()).days <= 3 and dt > datetime.utcnow()
        except Exception:
            pass

    return jsonify({
        "ok": True,
        "authorized": True,
        "need_renew": need_renew,
        "user": {
            "username": user["username"],
            "plan": user["plan"],
            "expire_at": user["expire_at"]
        }
    }), 200


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


# CORS for all /api/* routes
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    supports_credentials=False,
    allow_headers=["Authorization", "Content-Type"],
    methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
)



# -------- Blueprint 註冊 --------
app.register_blueprint(api_bp, url_prefix="/api")

# -------- 本地執行 --------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("DEBUG", "0") == "1")


    # updated to fix 404 issue

