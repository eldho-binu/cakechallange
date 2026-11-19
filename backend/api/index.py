import os
import sys
import uuid
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, g, send_file
from flask_cors import CORS

# Add parent directory to sys.path so 'services' module is importable
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from services.google_sheets import sheets_service
from services.authentication import (
    authenticate_admin, authenticate_member, require_auth, 
    hash_code_or_password, log_activity, MASTER_ADMIN_EMAIL
)
from services.order_service import (
    create_order, get_order_details, get_active_cakes, find_or_create_customer
)
from services.payment_service import (
    record_payment, update_payment_verification, recalculate_order_payments
)
from services.email_service import send_member_request_notification
from services.excel_service import generate_member_excel, generate_admin_master_workbook

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("api")

app = Flask(__name__)
# Enable CORS for frontend Vercel deployment and local dev
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)


# ---------------------------------------------------------------------------
# Global Error Handlers & Helpers
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "error": "API route not found."}), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({"success": False, "error": "An internal server error occurred."}), 500


# ---------------------------------------------------------------------------
# System Status & Health Check
# ---------------------------------------------------------------------------
@app.route("/api/system/status", methods=["GET"])
def system_status():
    status = sheets_service.is_connected()
    return jsonify({
        "success": True,
        "app_name": "Christmas Cake Challenge Order Management System",
        "organization": "Church Youth Group, Pancode",
        "status": status,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


# ---------------------------------------------------------------------------
# Authentication Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/auth/admin-login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required."}), 400

    ip = request.remote_addr or ""
    auth_res, err = authenticate_admin(email, password, ip)
    if err:
        return jsonify({"success": False, "error": err}), 401

    return jsonify({"success": True, "data": auth_res})


@app.route("/api/auth/member-login", methods=["POST"])
def member_login():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    code = data.get("code", "").strip()

    if not name or not code:
        return jsonify({"success": False, "error": "Member Name and Code are required."}), 400

    ip = request.remote_addr or ""
    auth_res, err = authenticate_member(name, code, ip)
    if err:
        return jsonify({"success": False, "error": err}), 401

    return jsonify({"success": True, "data": auth_res})


@app.route("/api/auth/me", methods=["GET"])
@require_auth()
def auth_me():
    return jsonify({"success": True, "user": g.current_user})


@app.route("/api/auth/logout", methods=["POST"])
@require_auth()
def auth_logout():
    user = g.current_user
    log_activity(user.get("name"), "LOGOUT", f"User {user.get('name')} logged out.")
    return jsonify({"success": True, "message": "Logged out successfully."})


# ---------------------------------------------------------------------------
# Public & Admin Member Requests
# ---------------------------------------------------------------------------
@app.route("/api/member-requests", methods=["POST"])
def submit_member_request():
    """Public form submission for applicant requesting access."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    location = data.get("location", "").strip()
    message = data.get("message", "").strip()

    if not name or not phone:
        return jsonify({"success": False, "error": "Full Name and Phone Number are required."}), 400

    # Check for existing pending request with same phone
    existing = sheets_service.find_records("Member_Requests", lambda r: str(r.get("Phone Number", "")).strip() == phone)
    if existing and any(r.get("Request Status") == "Pending" for r in existing):
        return jsonify({
            "success": False, 
            "error": "A pending request with this phone number already exists. The administrator will contact you soon."
        }), 409

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    req_id = f"REQ-{uuid.uuid4().hex[:8].upper()}"

    req_record = {
        "Request ID": req_id,
        "Applicant Name": name,
        "Phone Number": phone,
        "Location": location,
        "Optional Message": message,
        "Request Date": now_str,
        "Request Status": "Pending",
        "Admin Notes": "",
        "Contacted Date": "",
        "Approval or Rejection Date": ""
    }

    try:
        sheets_service.append_row("Member_Requests", req_record)
    except Exception as e:
        logger.error(f"Error saving member request: {e}")
        return jsonify({"success": False, "error": "Failed to save request. Please try again."}), 500

    # Resend email notification (failure does not block request creation)
    email_sent, email_msg = send_member_request_notification(
        applicant_name=name,
        phone_number=phone,
        location=location,
        message=message,
        request_date=now_str
    )

    log_activity(
        "Public Applicant",
        "MEMBER_REQUEST",
        f"New access request submitted by {name} ({phone}, {location}). Email: {email_msg}",
        record_id=req_id
    )

    return jsonify({
        "success": True,
        "message": "Your request has been submitted successfully! The church coordinator will review your application and send your member code.",
        "request_id": req_id,
        "email_notified": email_sent
    })


@app.route("/api/admin/member-requests", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def list_member_requests():
    status_filter = request.args.get("status", "").strip().lower()
    search = request.args.get("search", "").strip().lower()

    records = sheets_service.get_all_records("Member_Requests")
    filtered = []
    for r in records:
        if status_filter and status_filter != "all" and r.get("Request Status", "").lower() != status_filter:
            continue
        if search:
            name = r.get("Applicant Name", "").lower()
            phone = r.get("Phone Number", "").lower()
            loc = r.get("Location", "").lower()
            if search not in name and search not in phone and search not in loc:
                continue
        filtered.append(r)

    # Sort descending by date
    filtered.sort(key=lambda x: x.get("Request Date", ""), reverse=True)
    return jsonify({"success": True, "data": filtered})


@app.route("/api/admin/member-requests/<req_id>/status", methods=["PUT"])
@require_auth(allowed_roles=["admin"])
def update_request_status(req_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status", "").strip()
    admin_notes = data.get("notes", "").strip()

    valid_statuses = ["Pending", "Contacted", "Approved", "Rejected"]
    if new_status not in valid_statuses:
        return jsonify({"success": False, "error": f"Invalid status. Choose from: {valid_statuses}"}), 400

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_dict = {
        "Request Status": new_status,
        "Admin Notes": admin_notes
    }
    if new_status == "Contacted":
        update_dict["Contacted Date"] = now_str
    elif new_status in ["Approved", "Rejected"]:
        update_dict["Approval or Rejection Date"] = now_str

    success = sheets_service.update_row("Member_Requests", "Request ID", req_id, update_dict)
    if not success:
        return jsonify({"success": False, "error": "Request record not found."}), 404

    log_activity(
        g.current_user.get("name"),
        "REQUEST_STATUS_UPDATE",
        f"Updated Request {req_id} status to {new_status}.",
        record_id=req_id,
        new_val=new_status
    )
    return jsonify({"success": True, "message": f"Request status updated to {new_status}."})


@app.route("/api/admin/member-requests/<req_id>/approve", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def approve_member_request(req_id):
    """
    Approves request, creates active member record with unique code, and updates request status.
    """
    req_record = sheets_service.find_record("Member_Requests", "Request ID", req_id)
    if not req_record:
        return jsonify({"success": False, "error": "Request record not found."}), 404

    data = request.get_json(silent=True) or {}
    member_code = data.get("member_code", "").strip()

    # Generate random unique code if not provided by admin
    if not member_code:
        member_code = f"MC-{uuid.uuid4().hex[:6].upper()}"

    # Check if member with this name or code hash already exists
    applicant_name = req_record.get("Applicant Name", "").strip()
    all_members = sheets_service.get_all_records("Members")
    for m in all_members:
        if m.get("Member Name", "").strip().lower() == applicant_name.lower():
            return jsonify({
                "success": False, 
                "error": f"A member named '{applicant_name}' already exists. Please assign a different unique name."
            }), 409

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    member_id = f"MEM-{uuid.uuid4().hex[:8].upper()}"
    code_hash = hash_code_or_password(member_code)

    member_record = {
        "Member ID": member_id,
        "Member Name": applicant_name,
        "Member Code Hash": code_hash,
        "Phone Number": req_record.get("Phone Number", ""),
        "Email": data.get("email", ""),
        "Location": req_record.get("Location", ""),
        "Account Status": "Active",
        "Date Created": now_str,
        "Last Login": "",
        "Notes": f"Created from Request {req_id}. {data.get('notes', '')}".strip()
    }

    try:
        sheets_service.append_row("Members", member_record)
        sheets_service.update_row("Member_Requests", "Request ID", req_id, {
            "Request Status": "Approved",
            "Approval or Rejection Date": now_str,
            "Admin Notes": f"Approved and assigned Member ID {member_id}"
        })

        log_activity(
            g.current_user.get("name"),
            "MEMBER_APPROVED",
            f"Approved request {req_id} and created member {applicant_name} ({member_id}).",
            record_id=member_id
        )

        return jsonify({
            "success": True,
            "message": f"Member account created for {applicant_name}.",
            "member_id": member_id,
            "member_name": applicant_name,
            "generated_code": member_code  # Displayed once to admin so they can communicate it securely
        })
    except Exception as e:
        logger.error(f"Error approving member request: {e}")
        return jsonify({"success": False, "error": f"Failed to approve member: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Members Management (Admin)
# ---------------------------------------------------------------------------
@app.route("/api/admin/members", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def list_members():
    search = request.args.get("search", "").strip().lower()
    location = request.args.get("location", "").strip().lower()
    status = request.args.get("status", "").strip().lower()

    members = sheets_service.get_all_records("Members")
    orders = sheets_service.get_all_records("Orders")

    # Aggregate performance stats per member
    member_stats = {}
    for o in orders:
        mid = o.get("Member ID")
        if mid not in member_stats:
            member_stats[mid] = {"orders_count": 0, "total_sales": 0.0, "total_collected": 0.0}
        member_stats[mid]["orders_count"] += 1
        member_stats[mid]["total_sales"] += float(o.get("Total Amount", 0) or 0)
        member_stats[mid]["total_collected"] += float(o.get("Total Amount Paid", 0) or 0)

    result = []
    for m in members:
        if status and status != "all" and m.get("Account Status", "").lower() != status:
            continue
        if location and location != "all" and m.get("Location", "").lower() != location:
            continue
        if search:
            name = m.get("Member Name", "").lower()
            mid = m.get("Member ID", "").lower()
            phone = m.get("Phone Number", "").lower()
            if search not in name and search not in mid and search not in phone:
                continue

        mid = m.get("Member ID")
        stats = member_stats.get(mid, {"orders_count": 0, "total_sales": 0.0, "total_collected": 0.0})
        pending = max(0.0, stats["total_sales"] - stats["total_collected"])

        # Never return Member Code Hash in response!
        m_safe = dict(m)
        m_safe.pop("Member Code Hash", None)
        m_safe["orders_count"] = stats["orders_count"]
        m_safe["total_sales"] = round(stats["total_sales"], 2)
        m_safe["total_collected"] = round(stats["total_collected"], 2)
        m_safe["pending_amount"] = round(pending, 2)
        result.append(m_safe)

    return jsonify({"success": True, "data": result})


@app.route("/api/admin/members", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def create_member():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    location = data.get("location", "").strip()
    code = data.get("code", "").strip()
    notes = data.get("notes", "").strip()

    if not name or not phone:
        return jsonify({"success": False, "error": "Member Name and Phone Number are required."}), 400

    if not code:
        code = f"MC-{uuid.uuid4().hex[:6].upper()}"

    # Check for name collision
    existing = sheets_service.find_record("Members", "Member Name", name)
    if existing:
        return jsonify({"success": False, "error": f"Member with name '{name}' already exists."}), 409

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    member_id = f"MEM-{uuid.uuid4().hex[:8].upper()}"
    code_hash = hash_code_or_password(code)

    member_record = {
        "Member ID": member_id,
        "Member Name": name,
        "Member Code Hash": code_hash,
        "Phone Number": phone,
        "Email": email,
        "Location": location,
        "Account Status": "Active",
        "Date Created": now_str,
        "Last Login": "",
        "Notes": notes
    }

    sheets_service.append_row("Members", member_record)
    log_activity(
        g.current_user.get("name"),
        "MEMBER_CREATED",
        f"Admin created member {name} ({member_id}).",
        record_id=member_id
    )

    return jsonify({
        "success": True,
        "message": f"Member {name} created successfully.",
        "member_id": member_id,
        "assigned_code": code
    })


@app.route("/api/admin/members/<mid>", methods=["PUT"])
@require_auth(allowed_roles=["admin"])
def update_member(mid):
    data = request.get_json(silent=True) or {}
    member = sheets_service.find_record("Members", "Member ID", mid)
    if not member:
        return jsonify({"success": False, "error": "Member not found."}), 404

    updates = {}
    if "name" in data and data["name"].strip():
        updates["Member Name"] = data["name"].strip()
    if "phone" in data:
        updates["Phone Number"] = data["phone"].strip()
    if "email" in data:
        updates["Email"] = data["email"].strip()
    if "location" in data:
        updates["Location"] = data["location"].strip()
    if "notes" in data:
        updates["Notes"] = data["notes"].strip()
    if "status" in data and data["status"] in ["Active", "Inactive"]:
        updates["Account Status"] = data["status"]

    sheets_service.update_row("Members", "Member ID", mid, updates)
    log_activity(
        g.current_user.get("name"),
        "MEMBER_UPDATED",
        f"Admin updated member details for {mid}.",
        record_id=mid
    )
    return jsonify({"success": True, "message": "Member details updated."})


@app.route("/api/admin/members/<mid>/reset-code", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def reset_member_code(mid):
    member = sheets_service.find_record("Members", "Member ID", mid)
    if not member:
        return jsonify({"success": False, "error": "Member not found."}), 404

    data = request.get_json(silent=True) or {}
    new_code = data.get("new_code", "").strip()
    if not new_code:
        new_code = f"MC-{uuid.uuid4().hex[:6].upper()}"

    new_hash = hash_code_or_password(new_code)
    sheets_service.update_row("Members", "Member ID", mid, {"Member Code Hash": new_hash})

    log_activity(
        g.current_user.get("name"),
        "MEMBER_CODE_RESET",
        f"Reset login code for member {member.get('Member Name')} ({mid}).",
        record_id=mid
    )

    return jsonify({
        "success": True,
        "message": f"Member code reset for {member.get('Member Name')}.",
        "new_code": new_code
    })


@app.route("/api/admin/members/<mid>/toggle-status", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def toggle_member_status(mid):
    member = sheets_service.find_record("Members", "Member ID", mid)
    if not member:
        return jsonify({"success": False, "error": "Member not found."}), 404

    curr_status = member.get("Account Status", "Active")
    new_status = "Inactive" if curr_status == "Active" else "Active"

    sheets_service.update_row("Members", "Member ID", mid, {"Account Status": new_status})
    log_activity(
        g.current_user.get("name"),
        "MEMBER_STATUS_TOGGLE",
        f"Member {member.get('Member Name')} ({mid}) set to {new_status}.",
        record_id=mid,
        prev_val=curr_status,
        new_val=new_status
    )
    return jsonify({"success": True, "new_status": new_status})


# ---------------------------------------------------------------------------
# Cake Settings (Dynamic Varieties & Prices)
# ---------------------------------------------------------------------------
@app.route("/api/cakes", methods=["GET"])
def list_public_cakes():
    """Returns active cake varieties and pricing for members and order form."""
    active_cakes = get_active_cakes()
    return jsonify({"success": True, "data": active_cakes})


@app.route("/api/admin/cakes", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def list_admin_cakes():
    """Returns all cakes including inactive varieties."""
    cakes = sheets_service.get_all_records("Cake_Settings")
    parsed = []
    for c in cakes:
        weights_raw = c.get("Available Weights", "[]")
        prices_raw = c.get("Price For Each Weight", "{}")
        try:
            weights = json.loads(weights_raw) if weights_raw.startswith("[") else [w.strip() for w in weights_raw.split(",") if w.strip()]
        except Exception:
            weights = [w.strip() for w in weights_raw.split(",") if w.strip()]
        try:
            prices = json.loads(prices_raw) if prices_raw.startswith("{") else {}
        except Exception:
            prices = {}

        parsed.append({
            "cake_id": c.get("Cake ID"),
            "cake_name": c.get("Cake Name"),
            "description": c.get("Description", ""),
            "available_weights": weights,
            "prices": prices,
            "status": c.get("Active Status", "Active"),
            "date_created": c.get("Date Created", ""),
            "last_updated": c.get("Last Updated", "")
        })
    return jsonify({"success": True, "data": parsed})


@app.route("/api/admin/cakes", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def create_cake():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    desc = data.get("description", "").strip()
    weights = data.get("weights", [])
    prices = data.get("prices", {})  # e.g. {"500 g": 250, "1 kg": 500}

    if not name:
        return jsonify({"success": False, "error": "Cake name is required."}), 400
    if not weights or not prices:
        return jsonify({"success": False, "error": "At least one weight and price pair is required."}), 400

    now_str = datetime.now().strftime("%Y-%m-%d")
    cake_id = f"CAKE-{uuid.uuid4().hex[:6].upper()}"

    cake_record = {
        "Cake ID": cake_id,
        "Cake Name": name,
        "Description": desc,
        "Available Weights": json.dumps(weights),
        "Price For Each Weight": json.dumps(prices),
        "Active Status": "Active",
        "Date Created": now_str,
        "Last Updated": now_str
    }

    sheets_service.append_row("Cake_Settings", cake_record)
    log_activity(
        g.current_user.get("name"),
        "CAKE_CREATED",
        f"Added cake variety {name} ({cake_id}).",
        record_id=cake_id
    )

    return jsonify({"success": True, "message": "Cake variety created.", "cake_id": cake_id})


@app.route("/api/admin/cakes/<cid>", methods=["PUT"])
@require_auth(allowed_roles=["admin"])
def update_cake(cid):
    data = request.get_json(silent=True) or {}
    cake = sheets_service.find_record("Cake_Settings", "Cake ID", cid)
    if not cake:
        return jsonify({"success": False, "error": "Cake variety not found."}), 404

    now_str = datetime.now().strftime("%Y-%m-%d")
    updates = {"Last Updated": now_str}
    if "name" in data and data["name"].strip():
        updates["Cake Name"] = data["name"].strip()
    if "description" in data:
        updates["Description"] = data["description"].strip()
    if "weights" in data:
        updates["Available Weights"] = json.dumps(data["weights"])
    if "prices" in data:
        updates["Price For Each Weight"] = json.dumps(data["prices"])
    if "status" in data:
        updates["Active Status"] = data["status"]

    sheets_service.update_row("Cake_Settings", "Cake ID", cid, updates)
    log_activity(
        g.current_user.get("name"),
        "CAKE_UPDATED",
        f"Updated cake settings for {cid}.",
        record_id=cid
    )
    return jsonify({"success": True, "message": "Cake settings updated."})


@app.route("/api/admin/cakes/<cid>/toggle-status", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def toggle_cake_status(cid):
    cake = sheets_service.find_record("Cake_Settings", "Cake ID", cid)
    if not cake:
        return jsonify({"success": False, "error": "Cake not found."}), 404

    curr = cake.get("Active Status", "Active")
    new_status = "Inactive" if curr == "Active" else "Active"
    sheets_service.update_row("Cake_Settings", "Cake ID", cid, {"Active Status": new_status})

    log_activity(
        g.current_user.get("name"),
        "CAKE_STATUS_TOGGLE",
        f"Cake {cake.get('Cake Name')} set to {new_status}.",
        record_id=cid,
        prev_val=curr,
        new_val=new_status
    )
    return jsonify({"success": True, "new_status": new_status})


# ---------------------------------------------------------------------------
# Locations Management
# ---------------------------------------------------------------------------
@app.route("/api/locations", methods=["GET"])
def list_locations():
    """Returns active locations for dropdowns in member forms."""
    locs = sheets_service.get_all_records("Locations")
    active = [l for l in locs if str(l.get("Active Status", "")).lower() == "active"]
    return jsonify({"success": True, "data": active})


@app.route("/api/admin/locations", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def list_admin_locations():
    locs = sheets_service.get_all_records("Locations")
    orders = sheets_service.get_all_records("Orders")
    customers = sheets_service.get_all_records("Customers")

    cust_loc_map = {c.get("Customer ID"): c.get("Location") for c in customers}

    # Aggregate stats per location
    loc_stats = {}
    for o in orders:
        loc = cust_loc_map.get(o.get("Customer ID"), "")
        if loc not in loc_stats:
            loc_stats[loc] = {"orders_count": 0, "total_sales": 0.0, "total_collected": 0.0}
        loc_stats[loc]["orders_count"] += 1
        loc_stats[loc]["total_sales"] += float(o.get("Total Amount", 0) or 0)
        loc_stats[loc]["total_collected"] += float(o.get("Total Amount Paid", 0) or 0)

    for l in locs:
        name = l.get("Location Name", "")
        st = loc_stats.get(name, {"orders_count": 0, "total_sales": 0.0, "total_collected": 0.0})
        l["orders_count"] = st["orders_count"]
        l["total_sales"] = round(st["total_sales"], 2)
        l["total_collected"] = round(st["total_collected"], 2)
        l["pending_amount"] = round(max(0.0, st["total_sales"] - st["total_collected"]), 2)

    return jsonify({"success": True, "data": locs})


@app.route("/api/admin/locations", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def create_location():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    desc = data.get("description", "").strip()

    if not name:
        return jsonify({"success": False, "error": "Location name is required."}), 400

    existing = sheets_service.find_record("Locations", "Location Name", name)
    if existing:
        return jsonify({"success": False, "error": f"Location '{name}' already exists."}), 409

    loc_id = f"LOC-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "Location ID": loc_id,
        "Location Name": name,
        "Description": desc,
        "Active Status": "Active"
    }

    sheets_service.append_row("Locations", record)
    log_activity(
        g.current_user.get("name"),
        "LOCATION_CREATED",
        f"Created location {name} ({loc_id}).",
        record_id=loc_id
    )
    return jsonify({"success": True, "message": "Location created.", "location_id": loc_id})


@app.route("/api/admin/locations/<lid>", methods=["PUT"])
@require_auth(allowed_roles=["admin"])
def update_location(lid):
    data = request.get_json(silent=True) or {}
    loc = sheets_service.find_record("Locations", "Location ID", lid)
    if not loc:
        return jsonify({"success": False, "error": "Location not found."}), 404

    updates = {}
    if "name" in data and data["name"].strip():
        updates["Location Name"] = data["name"].strip()
    if "description" in data:
        updates["Description"] = data["description"].strip()
    if "status" in data:
        updates["Active Status"] = data["status"]

    sheets_service.update_row("Locations", "Location ID", lid, updates)
    log_activity(
        g.current_user.get("name"),
        "LOCATION_UPDATED",
        f"Updated location {lid}.",
        record_id=lid
    )
    return jsonify({"success": True, "message": "Location updated."})


@app.route("/api/admin/locations/<lid>/toggle-status", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def toggle_location_status(lid):
    loc = sheets_service.find_record("Locations", "Location ID", lid)
    if not loc:
        return jsonify({"success": False, "error": "Location not found."}), 404

    curr = loc.get("Active Status", "Active")
    new_status = "Inactive" if curr == "Active" else "Active"
    sheets_service.update_row("Locations", "Location ID", lid, {"Active Status": new_status})

    log_activity(
        g.current_user.get("name"),
        "LOCATION_STATUS_TOGGLE",
        f"Location {loc.get('Location Name')} set to {new_status}.",
        record_id=lid,
        prev_val=curr,
        new_val=new_status
    )
    return jsonify({"success": True, "new_status": new_status})


# ---------------------------------------------------------------------------
# Custom Fields Management (Dynamic Form Fields)
# ---------------------------------------------------------------------------
@app.route("/api/custom-fields", methods=["GET"])
def list_active_custom_fields():
    """Returns active custom fields to display in member add-order form."""
    fields = sheets_service.get_all_records("Custom_Fields")
    active = [f for f in fields if str(f.get("Active Status", "")).lower() == "active"]
    active.sort(key=lambda x: int(x.get("Display Order", 99) or 99))
    return jsonify({"success": True, "data": active})


@app.route("/api/admin/custom-fields", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def list_admin_custom_fields():
    fields = sheets_service.get_all_records("Custom_Fields")
    fields.sort(key=lambda x: int(x.get("Display Order", 99) or 99))
    return jsonify({"success": True, "data": fields})


@app.route("/api/admin/custom-fields", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def create_custom_field():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    ftype = data.get("type", "Short Text").strip()
    required = "Yes" if data.get("required") in [True, "Yes", "yes"] else "No"
    options = data.get("options", "").strip()
    order = str(data.get("order", 1))

    if not name:
        return jsonify({"success": False, "error": "Field Name is required."}), 400

    field_id = f"FIELD-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "Field ID": field_id,
        "Field Name": name,
        "Field Type": ftype,
        "Required": required,
        "Dropdown Options": options,
        "Active Status": "Active",
        "Display Order": order
    }

    sheets_service.append_row("Custom_Fields", record)
    log_activity(
        g.current_user.get("name"),
        "CUSTOM_FIELD_CREATED",
        f"Created custom field '{name}' ({field_id}).",
        record_id=field_id
    )
    return jsonify({"success": True, "message": "Custom field created.", "field_id": field_id})


@app.route("/api/admin/custom-fields/<fid>", methods=["PUT"])
@require_auth(allowed_roles=["admin"])
def update_custom_field(fid):
    data = request.get_json(silent=True) or {}
    field = sheets_service.find_record("Custom_Fields", "Field ID", fid)
    if not field:
        return jsonify({"success": False, "error": "Custom field not found."}), 404

    updates = {}
    if "name" in data and data["name"].strip():
        updates["Field Name"] = data["name"].strip()
    if "type" in data:
        updates["Field Type"] = data["type"].strip()
    if "required" in data:
        updates["Required"] = "Yes" if data["required"] in [True, "Yes", "yes"] else "No"
    if "options" in data:
        updates["Dropdown Options"] = data["options"].strip()
    if "order" in data:
        updates["Display Order"] = str(data["order"])
    if "status" in data:
        updates["Active Status"] = data["status"]

    sheets_service.update_row("Custom_Fields", "Field ID", fid, updates)
    log_activity(
        g.current_user.get("name"),
        "CUSTOM_FIELD_UPDATED",
        f"Updated custom field {fid}.",
        record_id=fid
    )
    return jsonify({"success": True, "message": "Custom field updated."})


@app.route("/api/admin/custom-fields/<fid>/toggle-status", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def toggle_custom_field_status(fid):
    field = sheets_service.find_record("Custom_Fields", "Field ID", fid)
    if not field:
        return jsonify({"success": False, "error": "Field not found."}), 404

    curr = field.get("Active Status", "Active")
    new_status = "Inactive" if curr == "Active" else "Active"
    sheets_service.update_row("Custom_Fields", "Field ID", fid, {"Active Status": new_status})

    log_activity(
        g.current_user.get("name"),
        "CUSTOM_FIELD_STATUS_TOGGLE",
        f"Field {field.get('Field Name')} set to {new_status}.",
        record_id=fid,
        prev_val=curr,
        new_val=new_status
    )
    return jsonify({"success": True, "new_status": new_status})


# ---------------------------------------------------------------------------
# Customers Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/customers/search", methods=["GET"])
@require_auth()
def search_customers():
    """Autocomplete search by phone or name for reuse in order form."""
    q = request.args.get("q", "").strip().lower()
    if not q or len(q) < 3:
        return jsonify({"success": True, "data": []})

    customers = sheets_service.get_all_records("Customers")
    matched = []
    for c in customers:
        if c.get("Archived Status") == "Archived":
            continue
        phone = str(c.get("Phone Number", "")).strip().lower()
        name = str(c.get("Customer Name", "")).strip().lower()
        if q in phone or q in name:
            matched.append(c)
            if len(matched) >= 10:
                break

    return jsonify({"success": True, "data": matched})


@app.route("/api/admin/customers", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def list_customers():
    search = request.args.get("search", "").strip().lower()
    location = request.args.get("location", "").strip().lower()
    archived = request.args.get("archived", "false").lower() == "true"

    customers = sheets_service.get_all_records("Customers")
    orders = sheets_service.get_all_records("Orders")

    # Order count per customer
    cust_orders = {}
    for o in orders:
        cid = o.get("Customer ID")
        cust_orders[cid] = cust_orders.get(cid, 0) + 1

    filtered = []
    for c in customers:
        is_archived = (c.get("Archived Status") == "Archived")
        if is_archived != archived:
            continue
        if location and location != "all" and c.get("Location", "").lower() != location:
            continue
        if search:
            name = c.get("Customer Name", "").lower()
            phone = c.get("Phone Number", "").lower()
            alt_phone = c.get("Alternate Phone Number", "").lower()
            if search not in name and search not in phone and search not in alt_phone:
                continue

        cid = c.get("Customer ID")
        c_copy = dict(c)
        c_copy["total_orders"] = cust_orders.get(cid, 0)
        filtered.append(c_copy)

    return jsonify({"success": True, "data": filtered})


@app.route("/api/admin/customers/<cid>", methods=["PUT"])
@require_auth(allowed_roles=["admin"])
def update_customer(cid):
    data = request.get_json(silent=True) or {}
    cust = sheets_service.find_record("Customers", "Customer ID", cid)
    if not cust:
        return jsonify({"success": False, "error": "Customer not found."}), 404

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updates = {"Updated Date": now_str}
    if "name" in data and data["name"].strip():
        updates["Customer Name"] = data["name"].strip()
    if "phone" in data and data["phone"].strip():
        updates["Phone Number"] = data["phone"].strip()
    if "alt_phone" in data:
        updates["Alternate Phone Number"] = data["alt_phone"].strip()
    if "address" in data:
        updates["Address"] = data["address"].strip()
    if "location" in data:
        updates["Location"] = data["location"].strip()
    if "landmark" in data:
        updates["Landmark"] = data["landmark"].strip()
    if "notes" in data:
        updates["Notes"] = data["notes"].strip()

    sheets_service.update_row("Customers", "Customer ID", cid, updates)
    log_activity(
        g.current_user.get("name"),
        "CUSTOMER_UPDATED",
        f"Updated customer {cid} ({updates.get('Customer Name', cust.get('Customer Name'))}).",
        record_id=cid
    )
    return jsonify({"success": True, "message": "Customer updated successfully."})


@app.route("/api/admin/customers/<cid>/archive", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def archive_customer(cid):
    cust = sheets_service.find_record("Customers", "Customer ID", cid)
    if not cust:
        return jsonify({"success": False, "error": "Customer not found."}), 404

    curr = cust.get("Archived Status", "Active")
    new_status = "Archived" if curr != "Archived" else "Active"
    sheets_service.update_row("Customers", "Customer ID", cid, {"Archived Status": new_status})

    log_activity(
        g.current_user.get("name"),
        "CUSTOMER_ARCHIVED" if new_status == "Archived" else "CUSTOMER_RESTORED",
        f"Customer {cid} set to {new_status}.",
        record_id=cid
    )
    return jsonify({"success": True, "new_status": new_status})


# ---------------------------------------------------------------------------
# Orders Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/orders", methods=["POST"])
@require_auth(allowed_roles=["member", "admin"])
def submit_order():
    """Creates a new customer order with cake items, customer handling, payment, custom fields."""
    user = g.current_user
    data = request.get_json(silent=True) or {}

    customer_data = data.get("customer", {})
    items_data = data.get("items", [])
    payment_data = data.get("payment", {})
    custom_fields = data.get("custom_fields", {})
    delivery_notes = data.get("delivery_notes", "")
    special_instructions = data.get("special_instructions", "")

    # For admin creating order, allow specifying member; otherwise member is current user
    if user.get("role") == "admin" and data.get("member_id"):
        member_id = data.get("member_id")
        member_rec = sheets_service.find_record("Members", "Member ID", member_id)
        member_name = member_rec.get("Member Name", "Assigned Member") if member_rec else "Admin"
    else:
        member_id = user.get("sub")
        member_name = user.get("name")

    res, err = create_order(
        member_id=member_id,
        member_name=member_name,
        customer_data=customer_data,
        items_data=items_data,
        payment_data=payment_data,
        custom_fields_data=custom_fields,
        delivery_notes=delivery_notes,
        special_instructions=special_instructions
    )

    if err:
        return jsonify({"success": False, "error": err}), 400

    return jsonify({"success": True, "message": "Order created successfully!", "data": res})


@app.route("/api/orders/my-orders", methods=["GET"])
@require_auth(allowed_roles=["member"])
def get_my_orders():
    """Returns orders created by the logged-in member with search and status filters."""
    member_id = g.current_user.get("sub")
    search = request.args.get("search", "").strip().lower()
    pay_status = request.args.get("payment_status", "").strip().lower()
    ver_status = request.args.get("verification_status", "").strip().lower()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    all_orders = sheets_service.get_all_records("Orders")
    all_customers = sheets_service.get_all_records("Customers")
    all_items = sheets_service.get_all_records("Order_Items")

    cust_map = {c.get("Customer ID"): c for c in all_customers}

    # Aggregate item summary per order
    item_summary = {}
    for it in all_items:
        oid = it.get("Order ID")
        if oid not in item_summary:
            item_summary[oid] = []
        item_summary[oid].append(f"{it.get('Quantity')}x {it.get('Cake Name')} ({it.get('Weight')})")

    my_orders = []
    for o in all_orders:
        if str(o.get("Member ID", "")).strip() != str(member_id).strip():
            continue
        if o.get("Archived Status") == "Archived":
            continue

        if pay_status and pay_status != "all" and o.get("Payment Status", "").lower() != pay_status:
            continue
        if ver_status and ver_status != "all" and o.get("Verification Status", "").lower() != ver_status:
            continue

        ord_date = o.get("Order Date", "")
        if date_from and ord_date < date_from:
            continue
        if date_to and ord_date > date_to:
            continue

        cid = o.get("Customer ID")
        cust = cust_map.get(cid, {})

        if search:
            oid = o.get("Order ID", "").lower()
            cname = cust.get("Customer Name", "").lower()
            cphone = cust.get("Phone Number", "").lower()
            if search not in oid and search not in cname and search not in cphone:
                continue

        o_copy = dict(o)
        o_copy["customer_name"] = cust.get("Customer Name", "Unknown")
        o_copy["customer_phone"] = cust.get("Phone Number", "")
        o_copy["customer_location"] = cust.get("Location", "")
        o_copy["items_summary"] = ", ".join(item_summary.get(o.get("Order ID"), []))
        my_orders.append(o_copy)

    my_orders.sort(key=lambda x: x.get("Created Date", ""), reverse=True)
    return jsonify({"success": True, "data": my_orders})


@app.route("/api/admin/orders", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def list_admin_orders():
    """
    Master Order Search: Multi-field filters across customer, member, location, cake, weight, dates.
    """
    search = request.args.get("search", "").strip().lower()
    member_filter = request.args.get("member_id", "").strip().lower()
    location_filter = request.args.get("location", "").strip().lower()
    cake_filter = request.args.get("cake_id", "").strip().lower()
    weight_filter = request.args.get("weight", "").strip().lower()
    pay_status = request.args.get("payment_status", "").strip().lower()
    ver_status = request.args.get("verification_status", "").strip().lower()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    archived = request.args.get("archived", "false").lower() == "true"

    all_orders = sheets_service.get_all_records("Orders")
    all_customers = sheets_service.get_all_records("Customers")
    all_members = sheets_service.get_all_records("Members")
    all_items = sheets_service.get_all_records("Order_Items")

    cust_map = {c.get("Customer ID"): c for c in all_customers}
    member_map = {m.get("Member ID"): m for m in all_members}

    # Map items to orders
    order_items_map = {}
    for it in all_items:
        oid = it.get("Order ID")
        if oid not in order_items_map:
            order_items_map[oid] = []
        order_items_map[oid].append(it)

    results = []
    for o in all_orders:
        is_archived = (o.get("Archived Status") == "Archived")
        if is_archived != archived:
            continue

        oid = o.get("Order ID")
        cid = o.get("Customer ID")
        mid = o.get("Member ID")
        cust = cust_map.get(cid, {})
        mem = member_map.get(mid, {})
        items = order_items_map.get(oid, [])

        if member_filter and member_filter != "all" and str(mid).lower() != member_filter:
            continue

        loc = cust.get("Location") or mem.get("Location", "")
        if location_filter and location_filter != "all" and loc.lower() != location_filter:
            continue

        if cake_filter and cake_filter != "all":
            if not any(it.get("Cake ID", "").lower() == cake_filter for it in items):
                continue

        if weight_filter and weight_filter != "all":
            if not any(it.get("Weight", "").lower() == weight_filter for it in items):
                continue

        if pay_status and pay_status != "all" and o.get("Payment Status", "").lower() != pay_status:
            continue

        if ver_status and ver_status != "all" and o.get("Verification Status", "").lower() != ver_status:
            continue

        ord_date = o.get("Order Date", "")
        if date_from and ord_date < date_from:
            continue
        if date_to and ord_date > date_to:
            continue

        if search:
            cname = cust.get("Customer Name", "").lower()
            cphone = cust.get("Phone Number", "").lower()
            calt = cust.get("Alternate Phone Number", "").lower()
            mname = mem.get("Member Name", "").lower()
            c_oid = oid.lower()
            if search not in cname and search not in cphone and search not in calt and search not in mname and search not in c_oid:
                continue

        o_copy = dict(o)
        o_copy["customer_name"] = cust.get("Customer Name", "Unknown")
        o_copy["customer_phone"] = cust.get("Phone Number", "")
        o_copy["customer_location"] = loc
        o_copy["member_name"] = mem.get("Member Name", "Unknown")
        o_copy["items_summary"] = ", ".join([f"{it.get('Quantity')}x {it.get('Cake Name')} ({it.get('Weight')})" for it in items])
        results.append(o_copy)

    results.sort(key=lambda x: x.get("Created Date", ""), reverse=True)
    return jsonify({"success": True, "data": results})


@app.route("/api/orders/<oid>", methods=["GET"])
@require_auth()
def get_single_order(oid):
    user = g.current_user
    res, err = get_order_details(oid, user_role=user.get("role"), user_id=user.get("sub"))
    if err:
        return jsonify({"success": False, "error": err}), 404 if "not found" in err.lower() else 403

    return jsonify({"success": True, "data": res})


@app.route("/api/orders/<oid>", methods=["PUT"])
@require_auth(allowed_roles=["admin", "member"])
def update_order(oid):
    """
    Updates permitted order details.
    If member: locked if order is Verified!
    If admin: unrestricted edit of customer details, notes, delivery, member reassign.
    """
    user = g.current_user
    order = sheets_service.find_record("Orders", "Order ID", oid)
    if not order:
        return jsonify({"success": False, "error": "Order not found."}), 404

    is_admin = (user.get("role") == "admin")
    if not is_admin:
        if str(order.get("Member ID", "")).strip() != str(user.get("sub")).strip():
            return jsonify({"success": False, "error": "Access denied."}), 403
        if order.get("Verification Status") == "Verified":
            return jsonify({
                "success": False, 
                "error": "This order is verified and locked against member edits. Please request a correction from the administrator."
            }), 403

    data = request.get_json(silent=True) or {}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updates = {"Updated Date": now_str}

    if "delivery_notes" in data:
        updates["Delivery or Collection Details"] = data["delivery_notes"].strip()
    if "special_instructions" in data:
        updates["Special Instructions"] = data["special_instructions"].strip()

    if is_admin:
        if "member_id" in data and data["member_id"].strip():
            updates["Member ID"] = data["member_id"].strip()
        if "order_status" in data:
            updates["Order Status"] = data["order_status"]
        if "verification_status" in data:
            updates["Verification Status"] = data["verification_status"]

    sheets_service.update_row("Orders", "Order ID", oid, updates)

    # If customer info provided, update customer record
    if "customer" in data and isinstance(data["customer"], dict):
        cid = order.get("Customer ID")
        cust_updates = {"Updated Date": now_str}
        cdata = data["customer"]
        if "name" in cdata: cust_updates["Customer Name"] = cdata["name"].strip()
        if "phone" in cdata: cust_updates["Phone Number"] = cdata["phone"].strip()
        if "alt_phone" in cdata: cust_updates["Alternate Phone Number"] = cdata["alt_phone"].strip()
        if "address" in cdata: cust_updates["Address"] = cdata["address"].strip()
        if "location" in cdata: cust_updates["Location"] = cdata["location"].strip()
        if "landmark" in cdata: cust_updates["Landmark"] = cdata["landmark"].strip()
        sheets_service.update_row("Customers", "Customer ID", cid, cust_updates)

    log_activity(
        user.get("name"),
        "ORDER_UPDATED",
        f"Order {oid} updated by {user.get('name')}.",
        record_id=oid
    )
    return jsonify({"success": True, "message": "Order updated successfully."})


@app.route("/api/orders/<oid>/reopen", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def reopen_order(oid):
    order = sheets_service.find_record("Orders", "Order ID", oid)
    if not order:
        return jsonify({"success": False, "error": "Order not found."}), 404

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheets_service.update_row("Orders", "Order ID", oid, {
        "Verification Status": "Pending Verification",
        "Updated Date": now_str
    })

    log_activity(
        g.current_user.get("name"),
        "ORDER_REOPENED",
        f"Administrator reopened order {oid} for editing.",
        record_id=oid
    )
    return jsonify({"success": True, "message": "Order reopened. Verification status set to Pending Verification."})


@app.route("/api/orders/<oid>/archive", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def archive_order(oid):
    order = sheets_service.find_record("Orders", "Order ID", oid)
    if not order:
        return jsonify({"success": False, "error": "Order not found."}), 404

    sheets_service.update_row("Orders", "Order ID", oid, {"Archived Status": "Archived"})
    log_activity(
        g.current_user.get("name"),
        "ORDER_ARCHIVED",
        f"Administrator archived order {oid}.",
        record_id=oid
    )
    return jsonify({"success": True, "message": "Order archived."})


@app.route("/api/orders/<oid>/restore", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def restore_order(oid):
    order = sheets_service.find_record("Orders", "Order ID", oid)
    if not order:
        return jsonify({"success": False, "error": "Order not found."}), 404

    sheets_service.update_row("Orders", "Order ID", oid, {"Archived Status": "Active"})
    log_activity(
        g.current_user.get("name"),
        "ORDER_RESTORED",
        f"Administrator restored order {oid} to active.",
        record_id=oid
    )
    return jsonify({"success": True, "message": "Order restored to active."})


# ---------------------------------------------------------------------------
# Payments Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/orders/<oid>/payments", methods=["POST"])
@require_auth(allowed_roles=["member", "admin"])
def add_order_payment(oid):
    user = g.current_user
    data = request.get_json(silent=True) or {}
    amount = data.get("amount")
    method = data.get("method", "Cash")
    reference = data.get("reference", "")
    notes = data.get("notes", "")

    order = sheets_service.find_record("Orders", "Order ID", oid)
    if not order:
        return jsonify({"success": False, "error": "Order not found."}), 404

    # Enforce member isolation
    if user.get("role") == "member" and str(order.get("Member ID", "")).strip() != str(user.get("sub")).strip():
        return jsonify({"success": False, "error": "Access denied."}), 403

    is_admin = (user.get("role") == "admin")
    verification_status = "Verified" if is_admin else "Pending Verification"

    res, err = record_payment(
        order_id=oid,
        member_id=order.get("Member ID"),
        amount=amount,
        payment_method=method,
        recorded_by=user.get("name"),
        reference=reference,
        notes=notes,
        verification_status=verification_status
    )

    if err:
        return jsonify({"success": False, "error": err}), 400

    return jsonify({"success": True, "message": "Payment recorded successfully.", "data": res})


@app.route("/api/admin/payments", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def list_payments():
    search = request.args.get("search", "").strip().lower()
    method_filter = request.args.get("method", "").strip().lower()
    ver_status = request.args.get("verification_status", "").strip().lower()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    all_payments = sheets_service.get_all_records("Payments")
    all_orders = sheets_service.get_all_records("Orders")
    all_customers = sheets_service.get_all_records("Customers")
    all_members = sheets_service.get_all_records("Members")

    order_map = {o.get("Order ID"): o for o in all_orders}
    cust_map = {c.get("Customer ID"): c for c in all_customers}
    member_map = {m.get("Member ID"): m for m in all_members}

    filtered = []
    for p in all_payments:
        if method_filter and method_filter != "all" and p.get("Payment Method", "").lower() != method_filter:
            continue
        if ver_status and ver_status != "all" and p.get("Verification Status", "").lower() != ver_status:
            continue

        p_date = p.get("Payment Date", "")
        if date_from and p_date < date_from:
            continue
        if date_to and p_date > date_to:
            continue

        oid = p.get("Order ID")
        mid = p.get("Member ID")
        order = order_map.get(oid, {})
        cid = order.get("Customer ID")
        cust = cust_map.get(cid, {})
        mem = member_map.get(mid, {})

        if search:
            pid = p.get("Payment ID", "").lower()
            cname = cust.get("Customer Name", "").lower()
            mname = mem.get("Member Name", "").lower()
            pref = p.get("Payment Reference", "").lower()
            p_oid = oid.lower()
            if search not in pid and search not in cname and search not in mname and search not in pref and search not in p_oid:
                continue

        p_copy = dict(p)
        p_copy["customer_name"] = cust.get("Customer Name", "Unknown")
        p_copy["member_name"] = mem.get("Member Name", "Unknown")
        p_copy["order_total"] = order.get("Total Amount", "0.00")
        p_copy["order_remaining"] = order.get("Remaining Amount", "0.00")
        filtered.append(p_copy)

    filtered.sort(key=lambda x: f"{x.get('Payment Date', '')} {x.get('Payment Time', '')}", reverse=True)
    return jsonify({"success": True, "data": filtered})


@app.route("/api/admin/payments/<pid>/verify", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def verify_payment(pid):
    data = request.get_json(silent=True) or {}
    notes = data.get("notes", "")
    res, err = update_payment_verification(pid, "Verified", g.current_user.get("name"), admin_notes=notes)
    if err:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": "Payment verified successfully.", "data": res})


@app.route("/api/admin/payments/<pid>/reject", methods=["POST"])
@require_auth(allowed_roles=["admin"])
def reject_payment(pid):
    data = request.get_json(silent=True) or {}
    notes = data.get("notes", "")
    res, err = update_payment_verification(pid, "Rejected", g.current_user.get("name"), admin_notes=notes)
    if err:
        return jsonify({"success": False, "error": err}), 400
    return jsonify({"success": True, "message": "Payment rejected.", "data": res})


# ---------------------------------------------------------------------------
# Reports & Excel Downloads
# ---------------------------------------------------------------------------
@app.route("/api/reports/member-summary", methods=["GET"])
@require_auth(allowed_roles=["member"])
def member_summary():
    member_id = g.current_user.get("sub")
    all_orders = sheets_service.get_all_records("Orders")
    all_items = sheets_service.get_all_records("Order_Items")

    my_orders = [o for o in all_orders if str(o.get("Member ID", "")).strip() == str(member_id).strip() and o.get("Archived Status") != "Archived"]
    my_order_ids = {o.get("Order ID") for o in my_orders}
    my_items = [it for it in all_items if it.get("Order ID") in my_order_ids]

    total_orders = len(my_orders)
    total_cakes = sum(int(it.get("Quantity", 1) or 1) for it in my_items)
    total_sales = sum(float(o.get("Total Amount", 0) or 0) for o in my_orders)
    total_collected = sum(float(o.get("Total Amount Paid", 0) or 0) for o in my_orders)
    total_pending = round(max(0.0, total_sales - total_collected), 2)

    paid_orders = sum(1 for o in my_orders if o.get("Payment Status") == "Paid")
    partially_paid = sum(1 for o in my_orders if o.get("Payment Status") == "Partially Paid")
    unpaid_orders = sum(1 for o in my_orders if o.get("Payment Status") == "Not Paid")
    awaiting_verification = sum(1 for o in my_orders if o.get("Verification Status") == "Pending Verification")

    return jsonify({
        "success": True,
        "data": {
            "total_orders": total_orders,
            "total_cakes": total_cakes,
            "total_sales": round(total_sales, 2),
            "total_collected": round(total_collected, 2),
            "total_pending": total_pending,
            "paid_orders": paid_orders,
            "partially_paid": partially_paid,
            "unpaid_orders": unpaid_orders,
            "awaiting_verification": awaiting_verification
        }
    })


@app.route("/api/reports/member-excel", methods=["GET"])
@require_auth(allowed_roles=["member"])
def export_member_excel():
    user = g.current_user
    excel_stream = generate_member_excel(user.get("sub"), user.get("name"))
    filename = f"My_Orders_{user.get('name').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(
        excel_stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@app.route("/api/reports/admin-summary", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def admin_summary():
    """Calculates all key performance indicators and analytics for Admin Dashboard."""
    all_orders = sheets_service.get_all_records("Orders")
    all_members = sheets_service.get_all_records("Members")
    all_items = sheets_service.get_all_records("Order_Items")
    all_payments = sheets_service.get_all_records("Payments")
    all_requests = sheets_service.get_all_records("Member_Requests")
    all_customers = sheets_service.get_all_records("Customers")

    active_orders = [o for o in all_orders if o.get("Archived Status") != "Archived"]
    valid_payments = [p for p in all_payments if str(p.get("Verification Status")).lower() != "rejected"]

    total_sales = sum(float(o.get("Total Amount", 0) or 0) for o in active_orders)
    total_collected = sum(float(p.get("Payment Amount", 0) or 0) for p in valid_payments)
    total_pending = round(max(0.0, total_sales - total_collected), 2)
    total_cakes = sum(int(it.get("Quantity", 1) or 1) for it in all_items)

    total_members = len(all_members)
    active_members = sum(1 for m in all_members if str(m.get("Account Status")).lower() == "active")
    pending_requests = sum(1 for r in all_requests if r.get("Request Status") == "Pending")

    fully_paid = sum(1 for o in active_orders if o.get("Payment Status") == "Paid")
    partially_paid = sum(1 for o in active_orders if o.get("Payment Status") == "Partially Paid")
    unpaid = sum(1 for o in active_orders if o.get("Payment Status") == "Not Paid")
    awaiting_ver = sum(1 for o in active_orders if o.get("Verification Status") == "Pending Verification")

    # Cake-wise sales
    cake_distribution = {}
    for it in all_items:
        cname = it.get("Cake Name", "Unknown")
        cake_distribution[cname] = cake_distribution.get(cname, 0) + int(it.get("Quantity", 1) or 1)

    # Location-wise sales
    cust_loc_map = {c.get("Customer ID"): c.get("Location") for c in all_customers}
    mem_loc_map = {m.get("Member ID"): m.get("Location") for m in all_members}
    location_sales = {}
    for o in active_orders:
        loc = cust_loc_map.get(o.get("Customer ID")) or mem_loc_map.get(o.get("Member ID")) or "Unknown"
        location_sales[loc] = round(location_sales.get(loc, 0.0) + float(o.get("Total Amount", 0) or 0), 2)

    # Member performance
    member_map = {m.get("Member ID"): m.get("Member Name") for m in all_members}
    member_sales = {}
    for o in active_orders:
        mname = member_map.get(o.get("Member ID"), "Unknown")
        member_sales[mname] = round(member_sales.get(mname, 0.0) + float(o.get("Total Amount", 0) or 0), 2)

    # Recent 6 orders
    active_orders_sorted = sorted(active_orders, key=lambda x: x.get("Created Date", ""), reverse=True)
    recent_orders = active_orders_sorted[:6]
    cust_map = {c.get("Customer ID"): c.get("Customer Name") for c in all_customers}
    for r in recent_orders:
        r["customer_name"] = cust_map.get(r.get("Customer ID"), "Unknown")
        r["member_name"] = member_map.get(r.get("Member ID"), "Unknown")

    return jsonify({
        "success": True,
        "data": {
            "total_members": total_members,
            "active_members": active_members,
            "total_orders": len(active_orders),
            "total_cakes_sold": total_cakes,
            "total_sales": round(total_sales, 2),
            "total_collected": round(total_collected, 2),
            "total_pending": total_pending,
            "fully_paid_orders": fully_paid,
            "partially_paid_orders": partially_paid,
            "unpaid_orders": unpaid,
            "awaiting_verification": awaiting_ver,
            "pending_requests": pending_requests,
            "cake_distribution": cake_distribution,
            "location_sales": location_sales,
            "member_sales": member_sales,
            "recent_orders": recent_orders
        }
    })


@app.route("/api/reports/admin-excel", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def export_admin_excel():
    admin_name = g.current_user.get("name")
    excel_stream = generate_admin_master_workbook(admin_name)
    filename = f"Christmas_Cake_Challenge_Master_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        excel_stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


# ---------------------------------------------------------------------------
# Activity Logs Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/admin/activity-logs", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def list_activity_logs():
    search = request.args.get("search", "").strip().lower()
    action_type = request.args.get("action_type", "").strip().lower()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    logs = sheets_service.get_all_records("Activity_Logs")
    filtered = []
    for l in logs:
        if action_type and action_type != "all" and l.get("Action Type", "").lower() != action_type:
            continue
        ldate = l.get("Date", "")
        if date_from and ldate < date_from:
            continue
        if date_to and ldate > date_to:
            continue
        if search:
            user = l.get("Admin ID or Username", "").lower()
            desc = l.get("Action Description", "").lower()
            rec = l.get("Related Record ID", "").lower()
            if search not in user and search not in desc and search not in rec:
                continue
        filtered.append(l)

    filtered.sort(key=lambda x: f"{x.get('Date', '')} {x.get('Time', '')}", reverse=True)
    return jsonify({"success": True, "data": filtered})


# ---------------------------------------------------------------------------
# Settings Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/admin/settings", methods=["GET"])
@require_auth(allowed_roles=["admin"])
def get_settings():
    settings = sheets_service.get_all_records("Settings")
    safe_settings = []
    for s in settings:
        if s.get("Setting Name") == "admin_password_hash":
            continue
        safe_settings.append(s)
    return jsonify({"success": True, "data": safe_settings})


@app.route("/api/admin/settings/password", methods=["PUT"])
@require_auth(allowed_roles=["admin"])
def update_admin_password():
    data = request.get_json(silent=True) or {}
    new_password = data.get("new_password", "").strip()
    if not new_password or len(new_password) < 8:
        return jsonify({"success": False, "error": "New password must be at least 8 characters long."}), 400

    hashed = hash_code_or_password(new_password)
    existing = sheets_service.find_record("Settings", "Setting Name", "admin_password_hash")
    now_str = datetime.now().strftime("%Y-%m-%d")

    if existing:
        sheets_service.update_row("Settings", "Setting Name", "admin_password_hash", {
            "Setting Value": hashed,
            "Updated Date": now_str
        })
    else:
        sheets_service.append_row("Settings", {
            "Setting ID": f"SET-{uuid.uuid4().hex[:6].upper()}",
            "Setting Name": "admin_password_hash",
            "Setting Value": hashed,
            "Description": "Secure hash of administrator password",
            "Updated Date": now_str
        })

    log_activity(
        g.current_user.get("name"),
        "ADMIN_PASSWORD_CHANGED",
        "Administrator changed the master password."
    )
    return jsonify({"success": True, "message": "Administrator password updated successfully."})


# ---------------------------------------------------------------------------
# Vercel entrypoint / local development runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
