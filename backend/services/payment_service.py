import uuid
import logging
from datetime import datetime
from .google_sheets import sheets_service
from .authentication import log_activity

logger = logging.getLogger(__name__)


def recalculate_order_payments(order_id):
    """
    Recalculates an order's total paid, remaining amount, and payment status
    based on all non-rejected payments in the Payments sheet.
    """
    order = sheets_service.find_record("Orders", "Order ID", order_id)
    if not order:
        logger.error(f"Cannot recalculate payments: Order {order_id} not found.")
        return None

    try:
        total_order_amount = float(order.get("Total Amount", 0))
    except (ValueError, TypeError):
        total_order_amount = 0.0

    all_payments = sheets_service.get_all_records("Payments")
    order_payments = [p for p in all_payments if str(p.get("Order ID", "")).strip() == str(order_id).strip()]

    # Valid payments: not rejected
    total_paid = 0.0
    for p in order_payments:
        status = str(p.get("Verification Status", "")).strip().lower()
        if status != "rejected":
            try:
                amt = float(p.get("Payment Amount", 0))
                total_paid += amt
            except (ValueError, TypeError):
                continue

    total_paid = round(total_paid, 2)
    remaining_amount = round(max(0.0, total_order_amount - total_paid), 2)

    # Determine payment status
    if remaining_amount <= 0 and total_order_amount > 0:
        payment_status = "Paid"
    elif total_paid > 0:
        payment_status = "Partially Paid"
    else:
        payment_status = "Not Paid"

    updated_order_fields = {
        "Total Amount Paid": f"{total_paid:.2f}",
        "Remaining Amount": f"{remaining_amount:.2f}",
        "Payment Status": payment_status,
        "Updated Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    sheets_service.update_row("Orders", "Order ID", order_id, updated_order_fields)
    return {
        "order_id": order_id,
        "total_amount": total_order_amount,
        "total_paid": total_paid,
        "remaining_amount": remaining_amount,
        "payment_status": payment_status
    }


def record_payment(order_id, member_id, amount, payment_method, recorded_by, reference="", notes="", verification_status="Pending Verification", payment_date=None):
    """
    Records a new payment row and updates the order totals.
    Includes duplicate payment prevention.
    """
    order = sheets_service.find_record("Orders", "Order ID", order_id)
    if not order:
        return None, "Order not found."

    try:
        amt_float = float(amount)
        if amt_float <= 0:
            return None, "Payment amount must be greater than zero."
    except (ValueError, TypeError):
        return None, "Invalid payment amount."

    now = datetime.now()
    p_date = payment_date.strip() if (payment_date and str(payment_date).strip()) else now.strftime("%Y-%m-%d")

    # Duplicate prevention: check recent payments for this order
    all_payments = sheets_service.get_all_records("Payments")
    for p in all_payments:
        if (str(p.get("Order ID", "")).strip() == str(order_id).strip() and
            str(p.get("Payment Amount", "")).strip() == f"{amt_float:.2f}" and
            str(p.get("Payment Method", "")).strip().lower() == str(payment_method or "Cash").strip().lower() and
            str(p.get("Payment Date", "")).strip() == p_date and
            str(p.get("Payment Reference", "")).strip() == str(reference or "").strip() and
            p.get("Verification Status") != "Rejected"):
            return None, f"An identical payment of ₹{amt_float:.2f} for this order was already recorded."

    payment_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"

    payment_record = {
        "Payment ID": payment_id,
        "Order ID": order_id,
        "Member ID": member_id,
        "Payment Amount": f"{amt_float:.2f}",
        "Payment Date": p_date,
        "Payment Time": now.strftime("%H:%M:%S"),
        "Payment Method": payment_method or "Cash",
        "Payment Reference": reference or "",
        "Recorded By": recorded_by,
        "Verification Status": verification_status,
        "Verified By": recorded_by if verification_status == "Verified" else "",
        "Verification Date": now.strftime("%Y-%m-%d") if verification_status == "Verified" else "",
        "Notes": notes or ""
    }

    sheets_service.append_row("Payments", payment_record)
    summary = recalculate_order_payments(order_id)

    log_activity(
        recorded_by,
        "PAYMENT_RECORDED",
        f"Recorded payment of ₹{amt_float:.2f} for Order {order_id} via {payment_method}.",
        record_id=payment_id,
        new_val=f"₹{amt_float:.2f}"
    )

    return {
        "payment": payment_record,
        "order_summary": summary
    }, None


def update_payment_details(payment_id, admin_user, amount=None, method=None, payment_date=None, reference=None, notes=None, verification_status=None):
    """
    Allows administrator to correct or update a payment record.
    Recalculates order payment status and logs the changes.
    """
    payment = sheets_service.find_record("Payments", "Payment ID", payment_id)
    if not payment:
        return None, "Payment record not found."

    updates = {}
    prev_val = f"Amt: {payment.get('Payment Amount')}, Method: {payment.get('Payment Method')}, Status: {payment.get('Verification Status')}"

    if amount is not None:
        try:
            amt_float = float(amount)
            if amt_float <= 0:
                return None, "Payment amount must be greater than zero."
            updates["Payment Amount"] = f"{amt_float:.2f}"
        except (ValueError, TypeError):
            return None, "Invalid payment amount."

    if method is not None and method.strip():
        updates["Payment Method"] = method.strip()
    if payment_date is not None and payment_date.strip():
        updates["Payment Date"] = payment_date.strip()
    if reference is not None:
        updates["Payment Reference"] = reference.strip()
    if notes is not None:
        updates["Notes"] = notes.strip()
    if verification_status in ["Verified", "Rejected", "Pending Verification"]:
        updates["Verification Status"] = verification_status
        if verification_status == "Verified":
            updates["Verified By"] = admin_user
            updates["Verification Date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if updates:
        sheets_service.update_row("Payments", "Payment ID", payment_id, updates)
        order_id = payment.get("Order ID")
        summary = recalculate_order_payments(order_id)
        new_val = f"Amt: {updates.get('Payment Amount', payment.get('Payment Amount'))}, Method: {updates.get('Payment Method', payment.get('Payment Method'))}, Status: {updates.get('Verification Status', payment.get('Verification Status'))}"
        log_activity(
            admin_user,
            "PAYMENT_CORRECTED",
            f"Payment {payment_id} corrected by {admin_user}.",
            record_id=payment_id,
            prev_val=prev_val,
            new_val=new_val
        )
        return {"payment_id": payment_id, "order_summary": summary}, None
    return {"payment_id": payment_id}, None


def update_payment_verification(payment_id, new_status, verified_by, admin_notes=""):
    """
    Allows administrator to verify or reject a payment.
    """
    payment = sheets_service.find_record("Payments", "Payment ID", payment_id)
    if not payment:
        return None, "Payment record not found."

    if new_status not in ["Verified", "Rejected", "Pending Verification"]:
        return None, "Invalid verification status."

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_data = {
        "Verification Status": new_status,
        "Verified By": verified_by,
        "Verification Date": now_str
    }
    if admin_notes:
        old_notes = payment.get("Notes", "")
        update_data["Notes"] = f"{old_notes} | Admin Note: {admin_notes}".strip(" |")

    sheets_service.update_row("Payments", "Payment ID", payment_id, update_data)
    order_id = payment.get("Order ID")
    summary = recalculate_order_payments(order_id)

    log_activity(
        verified_by,
        "PAYMENT_VERIFIED" if new_status == "Verified" else "PAYMENT_REJECTED",
        f"Payment {payment_id} changed to {new_status} by {verified_by}.",
        record_id=payment_id,
        prev_val=payment.get("Verification Status", ""),
        new_val=new_status
    )

    return {
        "payment_id": payment_id,
        "new_status": new_status,
        "order_summary": summary
    }, None
