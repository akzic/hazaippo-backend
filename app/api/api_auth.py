from flask import Blueprint, request, jsonify, current_app
from app import db, bcrypt, csrf
from app.models import User, Material, WantedMaterial
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity, create_refresh_token
)
from app.blueprints.utils import log_user_activity, send_reset_email, send_welcome_email
from twilio.rest import Client
from datetime import datetime, timedelta
import pytz
import os
import re
import hmac
import hashlib
import smtplib
import ssl
from email.message import EmailMessage
from werkzeug.utils import secure_filename
from app.utils.s3_uploader import upload_file_to_s3, build_s3_url


api_auth = Blueprint('api_auth', __name__)
jwt = JWTManager()

# JWTの初期化
def init_jwt(app):
    jwt.init_app(app)

# タイムゾーンの設定
JST = pytz.timezone('Asia/Tokyo')

# プロフィール画像用の許可拡張子
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'heic', 'heif'}


# ============================================================
#  ✅ SMTP（Xserver）送信ユーティリティ
# ============================================================

def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _smtp_config() -> dict:
    """
    .env 例:
      EMAIL_USER=info@zai-ltd.com
      EMAIL_PASS=****
      MAIL_SERVER=sv15110.xserver.jp
      MAIL_PORT=587
      MAIL_USE_TLS=true
      MAIL_USE_SSL=false
    """
    return {
        "user": os.getenv("EMAIL_USER", "").strip(),
        "pass": os.getenv("EMAIL_PASS", "").strip(),
        "server": os.getenv("MAIL_SERVER", "").strip(),
        "port": int(os.getenv("MAIL_PORT", "587").strip() or "587"),
        "use_tls": _env_bool("MAIL_USE_TLS", True),
        "use_ssl": _env_bool("MAIL_USE_SSL", False),
    }


def _send_email_smtp(to_email: str, subject: str, body: str) -> bool:
    """
    Xserver SMTPで確実に送る（STARTTLS対応）
    """
    try:
        cfg = _smtp_config()
        if not cfg["user"] or not cfg["pass"] or not cfg["server"] or not to_email:
            current_app.logger.error("[SMTP] missing env or to_email")
            return False

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg["user"]
        msg["To"] = to_email
        msg.set_content(body)

        timeout_sec = 15

        if cfg["use_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["server"], cfg["port"], timeout=timeout_sec, context=context) as smtp:
                smtp.login(cfg["user"], cfg["pass"])
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(cfg["server"], cfg["port"], timeout=timeout_sec) as smtp:
                smtp.ehlo()
                if cfg["use_tls"]:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                smtp.login(cfg["user"], cfg["pass"])
                smtp.send_message(msg)

        return True

    except Exception as e:
        current_app.logger.error(f"[SMTP] send failed: {e}", exc_info=True)
        return False


# ============================================================
#  ✅ 確認コード（6桁）生成＆検証（DB保存なしで安定）
# ============================================================

def _get_secret_key_bytes() -> bytes:
    # FlaskのSECRET_KEYを使う（ない場合も事故らないように）
    sk = current_app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY") or "fallback-secret"
    if isinstance(sk, bytes):
        return sk
    return str(sk).encode("utf-8")


def _email_code_time_window(now: datetime, minutes: int = 10) -> int:
    """
    10分単位の窓：この数値が同じ間は同じコードになる
    """
    ts = int(now.timestamp())
    return ts // (minutes * 60)


def _generate_email_verification_code(email: str, window: int) -> str:
    """
    stateless: SECRET_KEY + email + window でHMACして6桁化
    """
    key = _get_secret_key_bytes()
    msg = f"{email.strip().lower()}|{window}".encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    num = int.from_bytes(digest[:4], "big") % 1000000
    return f"{num:06d}"


def _verify_email_verification_code(email: str, code: str) -> bool:
    """
    現在窓 + 1つ前窓（時計ズレ対策）を許可
    """
    if not email or not code:
        return False
    c = str(code).strip()
    if not re.fullmatch(r"\d{6}", c):
        return False

    now = datetime.now(JST)
    w_now = _email_code_time_window(now, minutes=10)
    w_prev = w_now - 1

    good_now = _generate_email_verification_code(email, w_now)
    good_prev = _generate_email_verification_code(email, w_prev)
    return (c == good_now) or (c == good_prev)


def _send_verification_code_email(email: str) -> bool:
    now = datetime.now(JST)
    w = _email_code_time_window(now, minutes=10)
    code = _generate_email_verification_code(email, w)

    subject = "【はざいっぽ】確認コードのお知らせ"
    body = (
        "はざいっぽをご利用いただきありがとうございます。\n\n"
        "以下の確認コードを入力してください。\n\n"
        f"確認コード：{code}\n\n"
        "※このコードは一定時間で無効になります。\n"
        "※心当たりがない場合は、このメールを破棄してください。\n"
    )
    return _send_email_smtp(email, subject, body)


def _send_welcome_email_safe(email: str) -> bool:
    """
    既存 send_welcome_email が失敗してもSMTPで送る
    """
    try:
        ok = send_welcome_email(email)
        if ok:
            return True
    except Exception as e:
        current_app.logger.warning(f"[welcome_email] legacy send failed: {e}")

    subject = "【はざいっぽ】ご登録ありがとうございます"
    body = (
        "はざいっぽへのご登録ありがとうございます。\n\n"
        "ご利用を開始できます。\n"
        "今後ともよろしくお願いいたします。\n"
    )
    return _send_email_smtp(email, subject, body)


def _send_reset_email_safe(user: User, for_mobile: bool = False) -> bool:
    """
    既存 send_reset_email が失敗してもSMTPで送る
    """
    try:
        ok = send_reset_email(user, for_mobile=for_mobile)
        if ok:
            return True
    except Exception as e:
        current_app.logger.warning(f"[reset_email] legacy send failed: {e}")

    # フォールバック（SMTP）
    token = user.get_reset_token()
    base = request.host_url.rstrip("/")
    reset_url = f"{base}/api/auth/reset_password/{token}"
    subject = "【はざいっぽ】パスワード再設定のご案内"
    body = (
        f"{user.contact_name} 様\n\n"
        "パスワード再設定のリクエストを受け付けました。\n"
        "以下のリンクから再設定を行ってください。\n\n"
        f"{reset_url}\n\n"
        "※心当たりがない場合は、このメールを破棄してください。\n"
    )
    return _send_email_smtp(user.email, subject, body)


# ============================================================
#  ✅ バリデーション
# ============================================================

def _is_valid_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    e = email.strip()
    return ("@" in e) and ("." in e.split("@")[-1])


def _password_policy_ok(pw: str) -> bool:
    return isinstance(pw, str) and len(pw) >= 6


def _validate_company_code(v: str) -> bool:
    """
    半角英数字 6〜24（法人のみ想定）
    """
    if v is None:
        return False
    s = str(v).strip()
    return bool(re.fullmatch(r"[A-Za-z0-9]{6,24}", s))


# ============================================================
#  ✅ API
# ============================================================

@csrf.exempt
@api_auth.route("/login", methods=['POST'])
def api_login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"msg": "メールアドレスとパスワードが必要です。"}), 400

    email = data['email']
    password = data['password']

    user = User.query.filter_by(email=email).first()
    if user and bcrypt.check_password_hash(user.password, password):
        access_token = create_access_token(identity=user.id, expires_delta=timedelta(hours=24))
        refresh_token = create_refresh_token(identity=user.id, expires_delta=timedelta(days=30))

        try:
            log_user_activity(
                user.id,
                'ログイン',
                'ユーザーがAPI経由でログインしました。',
                request.remote_addr,
                request.user_agent.string,
                'N/A'
            )
        except Exception:
            pass

        return jsonify({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "msg": "ログイン成功しました。",
            "user": user.to_dict()
        }), 200
    else:
        return jsonify({"msg": "ログインに失敗しました。メールアドレスかパスワードが違います。"}), 401


# ------------------------------------------------------------
# ✅ 確認コード送信（単体で叩ける）
# POST /api/auth/register/send_code
# Body: { "email": "..."}
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route("/register/send_code", methods=["POST"])
def api_send_register_code():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()

    if not _is_valid_email(email):
        return jsonify({"msg": "有効なメールアドレスを入力してください。"}), 400

    # 既に登録済みなら不要
    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({"msg": "このメールアドレスは既に使用されています。"}), 400

    ok = _send_verification_code_email(email)
    if not ok:
        return jsonify({"msg": "確認コードメールの送信に失敗しました。"}), 500

    return jsonify({
        "msg": "確認コードを送信しました。",
        "needs_verification": True
    }), 200


# ------------------------------------------------------------
# ✅ 確認コード検証（単体で叩ける）
# POST /api/auth/register/verify_code
# Body: { "email": "...", "code": "123456"}
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route("/register/verify_code", methods=["POST"])
def api_verify_register_code():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()
    code = (data.get("code") or "").strip()

    if not _is_valid_email(email):
        return jsonify({"msg": "有効なメールアドレスを入力してください。"}), 400

    if not _verify_email_verification_code(email, code):
        return jsonify({"msg": "確認コードが正しくありません。"}), 400

    return jsonify({"msg": "確認コードを確認しました。"}), 200


# ------------------------------------------------------------
# ✅ 登録API（フロントの “続く” で確実に動く）
# POST /api/auth/register
#
# 仕様:
#  - verification_code が無い → 「確認コード送信だけ」して 200 を返す（登録しない）
#  - verification_code がある → コード検証→登録確定→201
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route("/register", methods=['POST'])
def api_register():
    data = request.get_json() or {}

    email = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()

    if not email or not password:
        return jsonify({"msg": "メールアドレスとパスワードが必要です。"}), 400

    if not _is_valid_email(email):
        return jsonify({"msg": "有効なメールアドレスを入力してください。"}), 400

    if not _password_policy_ok(password):
        return jsonify({"msg": "パスワードは6文字以上で入力してください。"}), 400

    # 既存ユーザーがいる場合はこの時点で弾く
    existing_user_by_email = User.query.filter_by(email=email).first()
    if existing_user_by_email:
        return jsonify({"msg": "このメールアドレスは既に使用されています。別のメールアドレスを使用してください。"}), 400

    # ✅ まだ verification_code が無いなら「確認コード送信だけ」
    verification_code = (data.get("verification_code") or "").strip()
    if not verification_code:
        ok = _send_verification_code_email(email)
        if not ok:
            return jsonify({"msg": "確認コードメールの送信に失敗しました。"}), 500

        return jsonify({
            "msg": "確認コードを送信しました。メールをご確認ください。",
            "needs_verification": True
        }), 200

    # ✅ verification_code があるなら検証して登録確定
    if not _verify_email_verification_code(email, verification_code):
        return jsonify({"msg": "確認コードが正しくありません。"}), 400

    # ここから先は「登録確定」なので必須項目チェック
    required_fields = [
        'company_name', 'prefecture', 'city', 'address',
        'company_phone', 'industry', 'job_title', 'contact_name', 'contact_phone',
        'business_structure'
    ]
    missing_fields = [f for f in required_fields if f not in data]
    if missing_fields:
        return jsonify({"msg": f"以下のフィールドが不足しています: {', '.join(missing_fields)}"}), 400

    company_name = (data.get('company_name') or '').strip()
    prefecture = (data.get('prefecture') or '').strip()
    city = (data.get('city') or '').strip()
    address = (data.get('address') or '').strip()
    company_phone = (data.get('company_phone') or '').strip()
    industry = (data.get('industry') or '').strip()
    job_title = (data.get('job_title') or '').strip()
    contact_name = (data.get('contact_name') or '').strip()
    contact_phone = (data.get('contact_phone') or '').strip()

    # business_structure
    try:
        business_structure = int(data.get('business_structure'))
    except (ValueError, TypeError):
        return jsonify({"msg": "有効な登録形態を選択してください。"}), 400

    if business_structure not in [0, 1, 2]:
        return jsonify({"msg": "有効な登録形態を選択してください。"}), 400

    # 電話番号重複チェック
    existing_user_by_contact_phone = User.query.filter_by(contact_phone=contact_phone).first()
    if existing_user_by_contact_phone:
        return jsonify({"msg": "この電話番号は既に使用されています。別の電話番号を使用してください。"}), 400

    # ✅ 法人コード（business_structure == 0 の場合のみ必須）
    company_code = (data.get("company_code") or "").strip()
    if business_structure == 0:
        if not company_code:
            return jsonify({"msg": "法人コードが必要です。"}), 400
        if not _validate_company_code(company_code):
            return jsonify({"msg": "法人コードは半角英数字6〜24桁で入力してください。"}), 400

    # business_structure に応じて値調整
    if business_structure in [0, 1]:
        industry_value = industry
        job_title_value = job_title
    else:
        industry_value = '業種なし'
        job_title_value = '職種なし'

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    # image（任意）: Flutterが一旦パスを載せてくる想定でも、DBへ入れるだけならクラッシュしない
    image_value = (data.get("image") or "").strip() or None

    try:
        if business_structure in [0, 1]:
            user = User(
                email=email,
                password=hashed_password,
                company_code=company_code if business_structure == 0 else None,
                company_name=company_name,
                prefecture=prefecture,
                city=city,
                address=address,
                company_phone=company_phone,
                industry=industry_value,
                job_title=job_title_value,
                without_approval=bool(data.get('without_approval', False)),
                contact_name=contact_name,
                contact_phone=contact_phone,
                business_structure=business_structure,
                image=image_value
            )
        else:
            # 一般ユーザー
            user = User(
                email=email,
                password=hashed_password,
                company_code=None,
                company_name=company_name,
                prefecture=prefecture,
                city=city,
                address=address,
                company_phone=contact_phone,  # 既存の方針維持
                industry=industry_value,
                job_title=job_title_value,
                without_approval=bool(data.get('without_approval', False)),
                contact_name=contact_name,
                contact_phone=contact_phone,
                business_structure=business_structure,
                image=image_value
            )

        db.session.add(user)
        db.session.commit()

        try:
            log_user_activity(
                user.id,
                'ユーザー登録',
                'ユーザーがAPI経由で新規登録しました。（確認コード検証済み）',
                request.remote_addr,
                request.user_agent.string,
                'N/A'
            )
        except Exception:
            pass

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[register] db error: {e}", exc_info=True)
        return jsonify({"msg": "ユーザー登録中にエラーが発生しました。もう一度やり直してください。"}), 500

    # ✅ ウェルカムメール（失敗しても登録は成功扱い）
    try:
        _send_welcome_email_safe(user.email)
    except Exception as e:
        current_app.logger.warning(f"[register] welcome mail failed: {e}")

    return jsonify({
        "msg": "ユーザー登録が完了しました！",
        "user": user.to_dict()
    }), 201


@csrf.exempt
@api_auth.route("/refresh", methods=['POST'])
@jwt_required(refresh=True)
def refresh_token():
    current_user_id = get_jwt_identity()
    access_token = create_access_token(identity=current_user_id, expires_delta=timedelta(hours=24))
    return jsonify({"access_token": access_token}), 200


# ------------------------------------------------------------
# パスワードリセット（メール送信）
# POST /api/auth/reset_password
# Body: { "email": "...", "for_mobile": true/false(任意) }
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route("/reset_password", methods=['POST'])
def api_reset_request():
    data = request.get_json() or {}
    email = (data.get('email') or "").strip()

    if not email:
        return jsonify({"msg": "メールアドレスが必要です。"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"msg": "該当アカウントがありません。"}), 404

    for_mobile = bool(data.get("for_mobile", False))

    if _send_reset_email_safe(user, for_mobile=for_mobile):
        try:
            log_user_activity(
                user.id,
                'API パスワードリセット',
                'モバイルアプリ経由リセットリクエスト',
                request.remote_addr,
                request.user_agent.string,
                'N/A'
            )
        except Exception:
            pass
        return jsonify({"msg": "リセットメールを送信しました。"}), 200

    return jsonify({"msg": "メール送信に失敗しました。"}), 500


# ------------------------------------------------------------
# パスワードリセット（トークン確定）
# POST /api/auth/reset_password/<token>
# Body: { "password": "..." } or { "new_password": "..." }
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route("/reset_password/<token>", methods=['POST'])
def api_reset_token(token):
    data = request.get_json() or {}
    new_password = data.get('password') or data.get('new_password')

    if not new_password:
        return jsonify({"msg": "新しいパスワードが必要です。"}), 400

    if not _password_policy_ok(new_password):
        return jsonify({"msg": "パスワードは6文字以上で入力してください。"}), 400

    user = User.verify_reset_token(token)
    if not user:
        return jsonify({"msg": "トークンが無効です。"}), 400

    try:
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[reset_password_token] error: {e}", exc_info=True)
        return jsonify({"msg": "パスワード更新に失敗しました。"}), 500

    try:
        log_user_activity(
            user.id,
            'パスワードリセット',
            'パスワードがAPI経由でリセットされました。',
            request.remote_addr,
            request.user_agent.string,
            'N/A'
        )
    except Exception:
        pass

    return jsonify({"msg": "パスワードが更新されました！"}), 200


# ------------------------------------------------------------
# パスワード変更（ログイン中）
# POST /api/auth/change_password
# Body: { "old_password": "...", "new_password": "..." }
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route("/change_password", methods=["POST"])
@jwt_required()
def api_change_password():
    data = request.get_json() or {}
    old_password = data.get("old_password") or ""
    new_password = data.get("new_password") or ""

    if not old_password or not new_password:
        return jsonify({"msg": "old_password と new_password が必要です。"}), 400

    if not _password_policy_ok(new_password):
        return jsonify({"msg": "新しいパスワードは6文字以上で入力してください。"}), 400

    if old_password == new_password:
        return jsonify({"msg": "新しいパスワードが現在のパスワードと同じです。"}), 400

    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "ユーザーが見つかりません。"}), 404

    if not bcrypt.check_password_hash(user.password, old_password):
        return jsonify({"msg": "現在のパスワードが違います。"}), 401

    try:
        hashed = bcrypt.generate_password_hash(new_password).decode("utf-8")
        user.password = hashed
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[change_password] error: {e}", exc_info=True)
        return jsonify({"msg": "パスワードの変更に失敗しました。"}), 500

    try:
        log_user_activity(
            user.id,
            "パスワード変更",
            "ユーザーがAPI経由でパスワードを変更しました。",
            request.remote_addr,
            request.user_agent.string,
            "N/A",
        )
    except Exception:
        pass

    return jsonify({"msg": "パスワードを変更しました。"}), 200


# ------------------------------------------------------------
# メールアドレス変更（ログイン中）
# POST /api/auth/change_email
# Body: { "old_email": "...", "new_email": "...", "password": "..." }
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route("/change_email", methods=["POST"])
@jwt_required()
def api_change_email():
    data = request.get_json() or {}
    old_email = (data.get("old_email") or "").strip()
    new_email = (data.get("new_email") or "").strip()
    password = data.get("password") or ""

    if not old_email or not new_email or not password:
        return jsonify({"msg": "old_email, new_email, password が必要です。"}), 400

    if not _is_valid_email(old_email) or not _is_valid_email(new_email):
        return jsonify({"msg": "有効なメールアドレスを入力してください。"}), 400

    if old_email == new_email:
        return jsonify({"msg": "新しいメールアドレスが現在のメールアドレスと同じです。"}), 400

    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "ユーザーが見つかりません。"}), 404

    if (user.email or "").strip() != old_email:
        return jsonify({"msg": "現在のメールアドレスと一致しません。"}), 400

    if not bcrypt.check_password_hash(user.password, password):
        return jsonify({"msg": "パスワードが違います。"}), 401

    existing = User.query.filter_by(email=new_email).first()
    if existing:
        return jsonify({"msg": "このメールアドレスは既に使用されています。別のメールアドレスを使用してください。"}), 400

    try:
        user.email = new_email
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[change_email] error: {e}", exc_info=True)
        return jsonify({"msg": "メールアドレスの変更に失敗しました。"}), 500

    try:
        log_user_activity(
            user.id,
            "メールアドレス変更",
            "ユーザーがAPI経由でメールアドレスを変更しました。",
            request.remote_addr,
            request.user_agent.string,
            "N/A",
        )
    except Exception:
        pass

    return jsonify({
        "msg": "メールアドレスを変更しました。",
        "user": user.to_dict()
    }), 200


@csrf.exempt
@api_auth.route("/logout", methods=['POST'])
@jwt_required()
def api_logout():
    current_user_id = get_jwt_identity()

    try:
        log_user_activity(
            current_user_id,
            'ログアウト',
            'ユーザーがAPI経由でログアウトしました。',
            request.remote_addr,
            request.user_agent.string,
            'N/A'
        )
    except Exception:
        pass

    return jsonify({"msg": "ログアウトしました。"}), 200


def send_reset_sms(user):
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    client = Client(account_sid, auth_token)

    token = user.get_reset_token()
    base = request.host_url.rstrip("/")
    reset_url = f"{base}/api/auth/reset_password/{token}"

    message_body = (
        f"こんにちは、{user.contact_name}様。パスワードリセットのリクエストがありました。\n"
        f"以下のリンクをクリックしてパスワードをリセットしてください: {reset_url}"
    )

    try:
        client.messages.create(
            body=message_body,
            from_=os.getenv('TWILIO_PHONE_NUMBER'),
            to=user.contact_phone
        )
        return True
    except Exception as e:
        current_app.logger.error(f"SMS送信に失敗しました: {e}")
        return False


# ------------------------------------------------------------
# デバイストークン登録
# POST /api/auth/device_token/register
# Expect: { "device_token": "<FCM トークン文字列>" }
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route('/device_token/register', methods=['POST'])
@jwt_required()
def register_device_token():
    data = request.get_json() or {}
    fcm_token = data.get('device_token')
    current_app.logger.info(f"★Device token received: {fcm_token}")

    if not fcm_token:
        return jsonify({'msg': 'FCMトークンが必要です。'}), 400

    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'msg': 'ユーザーが見つかりません。'}), 404

    if user.device_tokens is None:
        user.device_tokens = []

    if fcm_token not in user.device_tokens:
        user.device_tokens.append(fcm_token)
        db.session.commit()

    return jsonify({'msg': 'FCMトークンを登録しました。'}), 200


@csrf.exempt
@api_auth.route("/my_match_count", methods=['GET'])
@jwt_required()
def my_match_count():
    current_user_id = get_jwt_identity()
    user = User.query.get_or_404(current_user_id)

    matched_materials_count = Material.query.filter_by(
        user_id=user.id, matched=True
    ).count()

    matched_wanted_materials_count = WantedMaterial.query.filter_by(
        user_id=user.id, matched=True
    ).count()

    total_matched_count = matched_materials_count + matched_wanted_materials_count

    return jsonify({
        'status': 'success',
        'total_matched_count': total_matched_count
    }), 200


@csrf.exempt
@api_auth.route("/delete_account", methods=['DELETE'])
@jwt_required()
def api_delete_account():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    if not user:
        return jsonify({"msg": "アカウントが見つかりません。"}), 404

    try:
        db.session.delete(user)
        db.session.commit()
        current_app.logger.info(f"User {user.email} (ID: {user.id}) was deleted via API.")
        return jsonify({"msg": "アカウントを削除しました。"}), 200
    except Exception as e:
        current_app.logger.error(f"アカウント削除エラー: {str(e)}")
        db.session.rollback()
        return jsonify({"msg": "アカウントの削除に失敗しました。"}), 500


@csrf.exempt
@api_auth.route("/upload_profile_image", methods=['POST'])
@jwt_required()
def upload_profile_image():
    """
    モバイルアプリから送られてきたプロフィール画像を S3 にアップロードし、
    users テーブルの image カラムを更新する API
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({
                'status': 'error',
                'message': 'ユーザーが見つかりません。'
            }), 404

        if 'image' not in request.files:
            return jsonify({
                'status': 'error',
                'message': 'image ファイルが送信されていません。'
            }), 400

        file = request.files['image']
        if not file or file.filename == '':
            return jsonify({
                'status': 'error',
                'message': 'ファイル名が空です。'
            }), 400

        filename = secure_filename(file.filename or "")
        if '.' not in filename:
            return jsonify({
                'status': 'error',
                'message': 'ファイル拡張子が不正です。'
            }), 400

        ext = filename.rsplit('.', 1)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return jsonify({
                'status': 'error',
                'message': '許可されていないファイル形式です。'
            }), 400

        current_app.logger.debug(
            f"[upload_profile_image] upload start: filename={filename}, user_id={user.id}"
        )

        image_key = upload_file_to_s3(file, folder="users")
        if not image_key:
            return jsonify({
                'status': 'error',
                'message': '画像のアップロードに失敗しました。'
            }), 500

        image_url = build_s3_url(image_key)

        user.image = image_key
        db.session.commit()

        current_app.logger.info(
            f"[upload_profile_image] user_id={user.id}, image_key={image_key}"
        )

        try:
            log_user_activity(
                user.id,
                'プロフィール画像更新',
                'ユーザーがAPI経由でプロフィール画像を更新しました。',
                request.remote_addr,
                request.user_agent.string,
                'N/A'
            )
        except Exception as log_e:
            current_app.logger.warning(
                f"[upload_profile_image] log_user_activity error: {log_e}"
            )

        return jsonify({
            'status': 'success',
            'message': 'プロフィール画像を更新しました。',
            'image_key': image_key,
            'image_url': image_url,
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"[upload_profile_image] error: {e}", exc_info=True
        )
        return jsonify({
            'status': 'error',
            'message': 'プロフィール画像の更新中にエラーが発生しました。'
        }), 500


# ------------------------------------------------------------
# ✅ 法人コードから会社情報取得（自動入力用）
# GET /api/auth/company/by-code?code=XXXXXX
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route("/company/by-code", methods=["GET"])
def api_company_by_code():
    code = (request.args.get("code") or "").strip()

    # 法人コード形式チェック
    if not _validate_company_code(code):
        return jsonify({"msg": "法人コードが不正です。"}), 400

    # 会社情報は「法人ユーザー」の先頭から拾う（同法人の1人目想定）
    company_user = (
        User.query
        .filter_by(company_code=code, business_structure=0)
        .order_by(User.id.asc())
        .first()
    )

    if not company_user:
        return jsonify({"msg": "該当する法人情報が見つかりません。"}), 404

    # ✅ 自動入力してよい項目だけ返す（担当者情報は返さない）
    return jsonify({
        "company_code": code,
        "company_name": (company_user.company_name or ""),
        "company_phone": (company_user.company_phone or ""),
        "prefecture": (company_user.prefecture or ""),
        "city": (company_user.city or ""),
        "address": (company_user.address or ""),
        "industry": (company_user.industry or ""),
        "job_title": (company_user.job_title or ""),
    }), 200

# ------------------------------------------------------------
# ✅ メールアドレス存在チェック（送信はしない）
# POST /api/auth/register/check_email
# Body: { "email": "..." }
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route("/register/check_email", methods=["POST"])
def api_check_email_exists():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()

    if not _is_valid_email(email):
        return jsonify({"msg": "有効なメールアドレスを入力してください。"}), 400

    exists = User.query.filter_by(email=email).first() is not None

    return jsonify({
        "email": email,
        "exists": exists
    }), 200

# ------------------------------------------------------------
# ✅ ログイン中ユーザー情報取得
# GET /api/auth/me
# Header: Authorization: Bearer <access_token>
# ------------------------------------------------------------
@csrf.exempt
@api_auth.route("/me", methods=["GET"])
@jwt_required()
def api_me():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "ユーザーが見つかりません。"}), 404

    # ✅ to_dict に含まれない可能性がある値を「必ず載せる」
    user_dict = {}
    try:
        user_dict = user.to_dict() if hasattr(user, "to_dict") else {}
    except Exception:
        user_dict = {}

    # ✅ 必須フィールドを上書き保証（ここが重要）
    user_dict.update({
        "id": user.id,
        "email": user.email,
        "company_code": (user.company_code or ""),
        "business_structure": user.business_structure,
        "company_name": (user.company_name or ""),
        "prefecture": (user.prefecture or ""),
        "city": (user.city or ""),
        "address": (user.address or ""),
        "company_phone": (user.company_phone or ""),
        "industry": (user.industry or ""),
        "job_title": (user.job_title or ""),
        "contact_name": (user.contact_name or ""),
        "contact_phone": (user.contact_phone or ""),
        "without_approval": bool(user.without_approval) if hasattr(user, "without_approval") else False,
        "image": (user.image or ""),
    })

    return jsonify({
        "msg": "ユーザー情報を取得しました。",
        "user": user_dict
    }), 200
