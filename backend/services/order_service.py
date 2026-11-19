import json
import uuid
import logging
from datetime import datetime
from .google_sheets import sheets_service
from .authentication import log_activity

logger = logging.getLogger(__name__)


def get_active_cakes():
    """Returns active cake varieties and pricing structure."""
    all_cakes = sheets_service.get_all_records("Cake_Settings")
    active_cakes = []
    for c in all_cakes:
        status = str(c.get("Active Status", "")).strip().lower()
        if status in ["active", "true", "yes"]:
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

            active_cakes.append({
                "cake_id": c.get("Cake ID"),
                "cake_name": c.get("Cake Name"),
                "description": c.get("Description", ""),
                "available_weights": weights,
                "prices": prices,
                "status": c.get("Active Status")
            })
    return active_cakes


def find_or_create_customer(name, phone, alt_phone="", address="", location="", landmark="", notes=""):
    """
    Looks up an existing customer by phone number, updates missing fields or creates a new customer.
    Prevents duplicate customer records.
    """
    phone_clean = str(phone).strip()
    customers = sheets_service.get_all_records("Customers")
    matched = None
    for cust in customers:
        if str(cust.get("Phone Number", "")).strip() == phone_clean:
            matched = cust
            break

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if matched:
        cust_id = matched.get("Customer ID")
        # Update any blank or updated details
        updates = {"Updated Date": now_str}
        if name and name.strip() != matched.get("Customer Name"):
            updates["Customer Name"] = name.strip()
        if alt_phone and alt_phone.strip() != matched.get("Alternate Phone Number"):
            updates["Alternate Phone Number"] = alt_phone.strip()
        if address and address.strip() != matched.get("Address"):
            updates["Address"] = address.strip()
        if location and location.strip() != matched.get("Location"):
            updates["Location"] = location.strip()
        if landmark and landmark.strip() != matched.get("Landmark"):
            updates["Landmark"] = landmark.strip()
        if notes and notes.strip() != matched.get("Notes"):
            updates["Notes"] = notes.strip()

        sheets_service.update_row("Customers", "Customer ID", cust_id, updates)
        return cust_id, False
    else:
        cust_id = f"CUST-{uuid.uuid4().hex[:8].upper()}"
        new_cust = {
            "Customer ID": cust_id,
            "Customer Name": name.strip(),
            "Phone Number": phone_clean,
            "Alternate Phone Number": alt_phone.strip() if alt_phone else "",
            "Address": address.strip() if address else "",
            "Location": location.strip() if location else "",
            "Landmark": landmark.strip() if landmark else "",
            "Notes": notes.strip() if notes else "",
            "Created Date": now_str,
            "Updated Date": now_str,
            "Archived Status": "Active"
        }
        sheets_service.append_row("Customers", new_cust)
        return cust_id, True


def validate_and_calculate_items(items_data):
    """
    Validates submitted cake items against official Cake_Settings.
    Calculates subtotal and preserves historical pricing.
    """
    active_cakes = get_active_cakes()
    cake_lookup = {c["cake_id"]: c for c in active_cakes}

    validated_items = []
    order_total = 0.0

    if not items_data or not isinstance(items_data, list):
        return None, 0.0, "At least one cake item is required."

    for item in items_data:
        cake_id = str(item.get("cake_id", "")).strip()
        weight = str(item.get("weight", "")).strip()
        try:
            qty = int(item.get("quantity", 0))
            if qty <= 0:
                return None, 0.0, f"Quantity for cake must be at least 1."
        except (ValueError, TypeError):
            return None, 0.0, "Invalid quantity."

        cake = cake_lookup.get(cake_id)
        if not cake:
            return None, 0.0, f"Cake variety '{cake_id}' is not currently available."

        if weight not in cake["available_weights"]:
            return None, 0.0, f"Weight '{weight}' is not available for cake '{cake['cake_name']}'."

        official_price = cake["prices"].get(weight)
        if official_price is None:
            return None, 0.0, f"Official price not found for {cake['cake_name']} ({weight})."

        try:
            unit_price = float(official_price)
        except (ValueError, TypeError):
            return None, 0.0, f"Invalid official price configuration for {cake['cake_name']}."

        subtotal = round(qty * unit_price, 2)
        order_total += subtotal

        validated_items.append({
            "cake_id": cake_id,
            "cake_name": cake["cake_name"],
            "weight": weight,
            "quantity": qty,
            "unit_price": unit_price,
            "subtotal": subtotal,
            "historical_price": unit_price
        })

    return validated_items, round(order_total, 2), None


def create_order(member_id, member_name, customer_data, items_data, payment_data=None, custom_fields_data=None, delivery_notes="", special_instructions=""):
    """
    Atomic creation of complete customer order across:
    1. Customers
    2. Orders
    3. Order_Items
    4. Payments (if initial payment entered)
    5. Custom_Field_Values
    """
    # 1. Validate customer data
    cust_name = customer_data.get("name", "").strip()
    cust_phone = customer_data.get("phone", "").strip()
    if not cust_name or not cust_phone:
        return None, "Customer Name and Phone Number are required."

    # 2. Validate items and compute totals
    items, order_total, err = validate_and_calculate_items(items_data)
    if err:
        return None, err

    # 3. Find or create customer
    cust_id, is_new = find_or_create_customer(
        name=cust_name,
        phone=cust_phone,
        alt_phone=customer_data.get("alt_phone", ""),
        address=customer_data.get("address", ""),
        location=customer_data.get("location", ""),
        landmark=customer_data.get("landmark", ""),
        notes=customer_data.get("notes", "")
    )

    # 4. Process payment calculation
    init_payment_amt = 0.0
    pay_method = "Cash"
    pay_ref = ""
    pay_notes = ""
    if payment_data and isinstance(payment_data, dict):
        try:
            raw_amt = payment_data.get("amount", 0)
            if raw_amt:
                init_payment_amt = float(raw_amt)
                if init_payment_amt < 0:
                    return None, "Payment amount cannot be negative."
                if init_payment_amt > order_total:
                    return None, f"Initial payment cannot exceed total order amount (₹{order_total:.2f})."
        except (ValueError, TypeError):
            return None, "Invalid initial payment amount."

        pay_method = payment_data.get("method", "Cash")
        pay_ref = payment_data.get("reference", "")
        pay_notes = payment_data.get("notes", "")

    remaining_amount = round(max(0.0, order_total - init_payment_amt), 2)
    if remaining_amount <= 0 and order_total > 0:
        pay_status = "Paid"
    elif init_payment_amt > 0:
        pay_status = "Partially Paid"
    else:
        pay_status = "Not Paid"

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

    # 5. Build order record
    order_record = {
        "Order ID": order_id,
        "Customer ID": cust_id,
        "Member ID": member_id,
        "Order Date": date_str,
        "Order Status": "Confirmed",
        "Total Amount": f"{order_total:.2f}",
        "Total Amount Paid": f"{init_payment_amt:.2f}",
        "Remaining Amount": f"{remaining_amount:.2f}",
        "Payment Status": pay_status,
        "Verification Status": "Pending Verification",
        "Delivery or Collection Details": delivery_notes.strip() if delivery_notes else "",
        "Special Instructions": special_instructions.strip() if special_instructions else "",
        "Created Date": now_str,
        "Updated Date": now_str,
        "Archived Status": "Active"
    }

    # 6. Build order items
    order_item_records = []
    for it in items:
        item_id = f"ITEM-{uuid.uuid4().hex[:8].upper()}"
        order_item_records.append({
            "Order Item ID": item_id,
            "Order ID": order_id,
            "Cake ID": it["cake_id"],
            "Cake Name": it["cake_name"],
            "Weight": it["weight"],
            "Quantity": str(it["quantity"]),
            "Unit Price": f"{it['unit_price']:.2f}",
            "Subtotal": f"{it['subtotal']:.2f}",
            "Historical Price": f"{it['historical_price']:.2f}"
        })

    # 7. Build payment record if entered
    payment_record = None
    if init_payment_amt > 0:
        pay_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
        payment_record = {
            "Payment ID": pay_id,
            "Order ID": order_id,
            "Member ID": member_id,
            "Payment Amount": f"{init_payment_amt:.2f}",
            "Payment Date": date_str,
            "Payment Time": time_str,
            "Payment Method": pay_method,
            "Payment Reference": pay_ref,
            "Recorded By": member_name,
            "Verification Status": "Pending Verification",
            "Verified By": "",
            "Verification Date": "",
            "Notes": pay_notes
        }

    # 8. Build custom fields values if any
    custom_field_records = []
    if custom_fields_data and isinstance(custom_fields_data, dict):
        for field_id, field_val in custom_fields_data.items():
            if str(field_val).strip():
                custom_field_records.append({
                    "Value ID": f"VAL-{uuid.uuid4().hex[:8].upper()}",
                    "Order ID": order_id,
                    "Field ID": field_id,
                    "Field Value": str(field_val).strip(),
                    "Created Date": now_str
                })

    # Execute writes to sheets
    try:
        sheets_service.append_row("Orders", order_record)
        sheets_service.append_rows("Order_Items", order_item_records)
        if payment_record:
            sheets_service.append_row("Payments", payment_record)
        if custom_field_records:
            sheets_service.append_rows("Custom_Field_Values", custom_field_records)

        log_activity(
            member_name,
            "ORDER_CREATED",
            f"Created Order {order_id} for {cust_name} (Total: ₹{order_total:.2f}, Paid: ₹{init_payment_amt:.2f}).",
            record_id=order_id,
            new_val=f"₹{order_total:.2f}"
        )

        return {
            "order_id": order_id,
            "customer_id": cust_id,
            "total_amount": order_total,
            "amount_paid": init_payment_amt,
            "remaining_amount": remaining_amount,
            "payment_status": pay_status,
            "items_count": len(items)
        }, None

    except Exception as e:
        logger.error(f"Error persisting order {order_id}: {e}")
        return None, f"Failed to save order to persistent storage: {str(e)}"


def get_order_details(order_id, user_role="admin", user_id=None):
    """
    Retrieves full details of an order including customer info, items, payments, custom fields.
    Enforces authorization: members can only view their own orders!
    """
    order = sheets_service.find_record("Orders", "Order ID", order_id)
    if not order:
        return None, "Order not found."

    if user_role == "member" and str(order.get("Member ID", "")).strip() != str(user_id).strip():
        return None, "Access denied. You can only view your own orders."

    # Customer info
    cust_id = order.get("Customer ID")
    customer = sheets_service.find_record("Customers", "Customer ID", cust_id) or {}

    # Member info
    member_id = order.get("Member ID")
    member = sheets_service.find_record("Members", "Member ID", member_id) or {}

    # Items
    all_items = sheets_service.get_all_records("Order_Items")
    items = [it for it in all_items if str(it.get("Order ID", "")).strip() == str(order_id).strip()]

    # Payments
    all_payments = sheets_service.get_all_records("Payments")
    payments = [p for p in all_payments if str(p.get("Order ID", "")).strip() == str(order_id).strip()]

    # Custom Field Values
    all_cfv = sheets_service.get_all_records("Custom_Field_Values")
    cf_values = [v for v in all_cfv if str(v.get("Order ID", "")).strip() == str(order_id).strip()]
    all_cfs = sheets_service.get_all_records("Custom_Fields")
    cf_map = {f.get("Field ID"): f.get("Field Name") for f in all_cfs}

    custom_fields_formatted = []
    for val in cf_values:
        fid = val.get("Field ID")
        custom_fields_formatted.append({
            "field_id": fid,
            "field_name": cf_map.get(fid, fid),
            "value": val.get("Field Value")
        })

    return {
        "order": order,
        "customer": customer,
        "member": {
            "id": member_id,
            "name": member.get("Member Name", "Unknown Member"),
            "phone": member.get("Phone Number", ""),
            "location": member.get("Location", "")
        },
        "items": items,
        "payments": payments,
        "custom_fields": custom_fields_formatted
    }, None
