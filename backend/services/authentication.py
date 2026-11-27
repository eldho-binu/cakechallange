import os
import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from functools import wraps
import jwt
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from .google_sheets import sheets_service

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "christmas-cake-challenge-super-secret-key-2026-pancode")
MASTER_ADMIN_EMAIL = os.getenv("MASTER_ADMIN_EMAIL", "margregoriousyouthpancode123@gmail.com")
# Default admin password can be configured via environment variable
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@Christmas2026!")

# Simple in-memory rate limiter for login attempts
# Format: { "ip_or_identifier": [timestamp1, timestamp2, ...] }
RATE_LIMIT_STORE = {}
RATE_LIMIT_WINDOW = 900  # 15 minutes
MAX_ATTEMPTS = 6


def is_rate_limited(identifier):
    """Checks if an IP or username has exceeded the allowed login attempts."""
    now = time.time()
    attempts = RATE_LIMIT_STORE.get(identifier, [])
    # Filter attempts within the window
    recent = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
    RATE_LIMIT_STORE[identifier] = recent
    return len(recent) >= MAX_ATTEMPTS


def record_failed_attempt(identifier):
    """Records a failed login attempt for rate-limiting."""
    now = time.time()
    if identifier not in RATE_LIMIT_STORE:
        RATE_LIMIT_STORE[identifier] = []
    RATE_LIMIT_STORE[identifier].append(now)


def clear_failed_attempts(identifier):
    """Clears failed attempts on successful login."""
    RATE_LIMIT_STORE.pop(identifier, None)


def hash_code_or_password(plain_text):
    """Hashes member code or admin password using secure pbkdf2."""
    return generate_password_hash(plain_text.strip(), method="pbkdf2:sha256:100000")


def verify_code_or_password(stored_hash, plain_text):
    """Verifies plain text against stored pbkdf2 hash."""
    if not stored_hash or not plain_text:
        return False
    try:
        return check_password_hash(stored_hash.strip(), plain_text.strip())
    except Exception as e:
        logger.error(f"Error checking password hash: {e}")
        return False


def create_token(user_id, name, role, email=None, location=None, admin_type=None, expires_in_hours=48):
    """Generates a secure signed JWT token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "name": str(name),
        "role": str(role),
        "admin_type": str(admin_type or ""),
        "email": str(email or ""),
        "location": str(location or ""),
        "iat": now,
        "exp": now + timedelta(hours=expires_in_hours)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token):
    """Decodes and validates a JWT token."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user_from_request():
    """Extracts bearer token from headers and returns decoded payload."""
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    elif request.args.get("token"):
        token = request.args.get("token").strip()

    if not token:
        return None

    return decode_token(token)


def require_auth(allowed_roles=None):
    """Decorator to enforce authentication and role-based permissions."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user_from_request()
            if not user:
                return jsonify({"success": False, "error": "Authentication required. Please log in."}), 401

            if allowed_roles and user.get("role") not in allowed_roles:
                return jsonify({"success": False, "error": "Access forbidden: insufficient permissions."}), 403

            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_master_admin():
    """Decorator to enforce Master Admin only permissions."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user_from_request()
            if not user:
                return jsonify({"success": False, "error": "Authentication required. Please log in."}), 401

            if user.get("role") != "admin" or user.get("admin_type") != "master":
                return jsonify({"success": False, "error": "Access forbidden: Only Master Administrator can perform this action."}), 403

            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def log_activity(admin_id_or_user, action_type, description, record_id="", prev_val="", new_val=""):
    """Helper to append an audit log entry to the Activity_Logs sheet."""
    try:
        now = datetime.now()
        log_entry = {
            "Log ID": f"LOG-{uuid.uuid4().hex[:8].upper()}",
            "Admin ID or Username": admin_id_or_user,
            "Action Type": action_type,
            "Action Description": description,
            "Related Record ID": record_id,
            "Previous Value": prev_val,
            "New Value": new_val,
            "Date": now.strftime("%Y-%m-%d"),
            "Time": now.strftime("%H:%M:%S")
        }
        sheets_service.append_row("Activity_Logs", log_entry)
    except Exception as e:
        logger.error(f"Failed to record activity log: {e}")


def authenticate_admin(email, password, ip_address=""):
    """Authenticates the administrator (Master Admin or 1 of 4 Subadmins)."""
    rate_key = f"admin_{email.lower().strip()}_{ip_address}"
    if is_rate_limited(rate_key):
        return None, "Too many failed attempts. Account temporarily locked for 15 minutes."

    clean_input = email.lower().strip()
    target_master_email = MASTER_ADMIN_EMAIL.lower().strip()

    # 1. Master Administrator Check
    if clean_input == target_master_email or clean_input == "admin":
        admin_hash_setting = sheets_service.find_record("Settings", "Setting Name", "admin_password_hash")
        stored_hash = None
        if admin_hash_setting and admin_hash_setting.get("Setting Value"):
            stored_hash = admin_hash_setting["Setting Value"]

        valid = False
        if stored_hash:
            valid = verify_code_or_password(stored_hash, password)
        else:
            if password.strip() == DEFAULT_ADMIN_PASSWORD:
                valid = True
                hashed = hash_code_or_password(DEFAULT_ADMIN_PASSWORD)
                sheets_service.append_row("Settings", {
                    "Setting ID": f"SET-{uuid.uuid4().hex[:6].upper()}",
                    "Setting Name": "admin_password_hash",
                    "Setting Value": hashed,
                    "Description": "Secure hash of administrator password",
                    "Updated Date": datetime.now().strftime("%Y-%m-%d")
                })

        if not valid:
            record_failed_attempt(rate_key)
            return None, "Invalid administrator email or password."

        clear_failed_attempts(rate_key)
        token = create_token(
            user_id="ADMIN-MASTER",
            name="Master Administrator",
            role="admin",
            admin_type="master",
            email=MASTER_ADMIN_EMAIL
        )
        log_activity("Master Administrator", "LOGIN", "Master Administrator logged in successfully.")
        return {
            "token": token,
            "user": {
                "id": "ADMIN-MASTER",
                "name": "Master Administrator",
                "role": "admin",
                "admin_type": "master",
                "email": MASTER_ADMIN_EMAIL
            }
        }, None

    # 2. Subadmin Check (up to 4 Subadmins in Google Sheets)
    subadmins = sheets_service.get_all_records("Subadmins")
    matched_sub = None
    for sub in subadmins:
        sub_email = str(sub.get("Email", "")).lower().strip()
        sub_id = str(sub.get("Subadmin ID", "")).lower().strip()
        sub_name = str(sub.get("Name", "")).lower().strip()
        if clean_input in (sub_email, sub_id, sub_name):
            matched_sub = sub
            break

    if matched_sub:
        status = str(matched_sub.get("Account Status", "")).strip().lower()
        if status != "active":
            return None, "This subadmin account is currently deactivated. Please contact the Master Administrator."

        stored_hash = matched_sub.get("Password Hash", "")
        if not verify_code_or_password(stored_hash, password):
            record_failed_attempt(rate_key)
            return None, "Invalid subadmin password."

        clear_failed_attempts(rate_key)

        # Update Last Login
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheets_service.update_row(
            "Subadmins",
            "Subadmin ID",
            matched_sub.get("Subadmin ID"),
            {"Last Login": now_str}
        )

        sub_name = matched_sub.get("Name", "Subadmin").strip()
        sub_id = matched_sub.get("Subadmin ID", "").strip()
        display_name = f"Subadmin {sub_name} ({sub_id})"

        token = create_token(
            user_id=sub_id,
            name=display_name,
            role="admin",
            admin_type="subadmin",
            email=matched_sub.get("Email", "")
        )

        log_activity(
            display_name,
            "LOGIN",
            f"Subadmin {sub_name} ({sub_id}) logged in successfully.",
            record_id=sub_id
        )

        return {
            "token": token,
            "user": {
                "id": sub_id,
                "name": sub_name,
                "display_name": display_name,
                "role": "admin",
                "admin_type": "subadmin",
                "email": matched_sub.get("Email", "")
            }
        }, None

    record_failed_attempt(rate_key)
    return None, "Invalid administrator email or password."


def authenticate_member(member_name, member_code, ip_address=""):
    """Authenticates a youth group member using Member Name and Unique Code."""
    name_clean = member_name.strip()
    rate_key = f"member_{name_clean.lower()}_{ip_address}"
    if is_rate_limited(rate_key):
        return None, "Too many failed attempts. Please wait 15 minutes before trying again."

    members = sheets_service.get_all_records("Members")
    matched_member = None

    for m in members:
        if m.get("Member Name", "").strip().lower() == name_clean.lower():
            matched_member = m
            break

    if not matched_member:
        record_failed_attempt(rate_key)
        return None, "Member name or code is incorrect."

    # Verify active account status
    if matched_member.get("Account Status", "").strip().lower() != "active":
        return None, "This member account is currently inactive or deactivated. Please contact the administrator."

    stored_hash = matched_member.get("Member Code Hash", "")
    if not verify_code_or_password(stored_hash, member_code):
        record_failed_attempt(rate_key)
        return None, "Member name or code is incorrect."

    clear_failed_attempts(rate_key)

    # Update last login
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheets_service.update_row(
        "Members", 
        "Member ID", 
        matched_member.get("Member ID"), 
        {"Last Login": now_str}
    )

    token = create_token(
        user_id=matched_member.get("Member ID"),
        name=matched_member.get("Member Name"),
        role="member",
        email=matched_member.get("Email", ""),
        location=matched_member.get("Location", "")
    )

    log_activity(
        matched_member.get("Member Name"), 
        "MEMBER_LOGIN", 
        f"Member {matched_member.get('Member Name')} logged in.", 
        record_id=matched_member.get("Member ID")
    )

    return {
        "token": token,
        "user": {
            "id": matched_member.get("Member ID"),
            "name": matched_member.get("Member Name"),
            "role": "member",
            "email": matched_member.get("Email", ""),
            "location": matched_member.get("Location", "")
        }
    }, None
