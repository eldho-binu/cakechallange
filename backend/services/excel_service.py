import io
import logging
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .google_sheets import sheets_service
from .authentication import log_activity

logger = logging.getLogger(__name__)

# Christmas Theme Color Palette for Excel
DARK_GREEN = "14452F"
MINT_ACCENT = "E2EBD8"
GOLD_ACCENT = "D4AF37"
WHITE = "FFFFFF"
LIGHT_GRAY = "F7F9F6"
BORDER_GRAY = "D1D5DB"


def apply_header_styles(ws, row_idx=1):
    """Applies deep Christmas green header with white bold text and centered alignment."""
    header_font = Font(name="Calibri", size=11, bold=True, color=WHITE)
    header_fill = PatternFill(start_color=DARK_GREEN, end_color=DARK_GREEN, fill_type="solid")
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    border = Border(
        left=Side(style="thin", color=BORDER_GRAY),
        right=Side(style="thin", color=BORDER_GRAY),
        top=Side(style="thin", color=BORDER_GRAY),
        bottom=Side(style="medium", color=GOLD_ACCENT)
    )

    ws.row_dimensions[row_idx].height = 28
    for cell in ws[row_idx]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = align
        cell.border = border


def apply_data_row_styles(ws, start_row, end_row, num_cols):
    """Applies clean borders, font, and subtle zebra stripes to data rows."""
    font = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style="thin", color=BORDER_GRAY),
        right=Side(style="thin", color=BORDER_GRAY),
        top=Side(style="thin", color=BORDER_GRAY),
        bottom=Side(style="thin", color=BORDER_GRAY)
    )
    zebra_fill = PatternFill(start_color=LIGHT_GRAY, end_color=LIGHT_GRAY, fill_type="solid")

    for r in range(start_row, end_row + 1):
        ws.row_dimensions[r].height = 20
        is_even = (r % 2 == 0)
        for c in range(1, num_cols + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = font
            cell.border = thin_border
            if is_even:
                cell.fill = zebra_fill


def auto_fit_columns(ws, max_width=45):
    """Sets column widths dynamically to prevent text truncation."""
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val = str(cell.value or "")
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[col_letter].width = min(max_len + 4, max_width)


def generate_member_excel(member_id, member_name):
    """
    Generates a private Excel workbook for an individual member containing only their orders.
    Guarantees no access to other members' data or sensitive codes.
    """
    all_orders = sheets_service.get_all_records("Orders")
    all_items = sheets_service.get_all_records("Order_Items")
    all_customers = sheets_service.get_all_records("Customers")
    all_payments = sheets_service.get_all_records("Payments")

    cust_map = {c.get("Customer ID"): c for c in all_customers}

    # Filter member's orders
    member_orders = [o for o in all_orders if str(o.get("Member ID", "")).strip() == str(member_id).strip()]
    member_order_ids = {o.get("Order ID") for o in member_orders}
    member_items = [it for it in all_items if it.get("Order ID") in member_order_ids]
    member_payments = [p for p in all_payments if p.get("Order ID") in member_order_ids]

    wb = openpyxl.Workbook()
    # Sheet 1: Orders
    ws_orders = wb.active
    ws_orders.title = "My Orders"
    headers_orders = [
        "Order ID", "Customer Name", "Customer Phone", "Location", "Order Date",
        "Total Amount (₹)", "Amount Paid (₹)", "Remaining (₹)", "Payment Status", "Verification Status"
    ]
    ws_orders.append(headers_orders)

    total_sales = 0.0
    total_paid = 0.0
    total_remaining = 0.0

    for o in member_orders:
        c = cust_map.get(o.get("Customer ID"), {})
        tot = float(o.get("Total Amount", 0) or 0)
        pd = float(o.get("Total Amount Paid", 0) or 0)
        rem = float(o.get("Remaining Amount", 0) or 0)
        total_sales += tot
        total_paid += pd
        total_remaining += rem

        ws_orders.append([
            o.get("Order ID"),
            c.get("Customer Name", "Unknown"),
            c.get("Phone Number", ""),
            c.get("Location", ""),
            o.get("Order Date"),
            tot,
            pd,
            rem,
            o.get("Payment Status"),
            o.get("Verification Status")
        ])

    # Summary row
    sum_row = len(member_orders) + 2
    ws_orders.append(["TOTAL", "", "", "", "", total_sales, total_paid, total_remaining, "", ""])
    ws_orders.cell(row=sum_row, column=1).font = Font(bold=True)
    ws_orders.cell(row=sum_row, column=6).font = Font(bold=True)
    ws_orders.cell(row=sum_row, column=7).font = Font(bold=True)
    ws_orders.cell(row=sum_row, column=8).font = Font(bold=True)

    apply_header_styles(ws_orders)
    if member_orders:
        apply_data_row_styles(ws_orders, 2, len(member_orders) + 1, len(headers_orders))
    auto_fit_columns(ws_orders)

    # Sheet 2: Cake Items Breakdown
    ws_items = wb.create_sheet(title="Cakes Ordered")
    headers_items = ["Order ID", "Cake Variety", "Weight", "Quantity", "Unit Price (₹)", "Subtotal (₹)"]
    ws_items.append(headers_items)
    for it in member_items:
        ws_items.append([
            it.get("Order ID"),
            it.get("Cake Name"),
            it.get("Weight"),
            int(it.get("Quantity", 1) or 1),
            float(it.get("Unit Price", 0) or 0),
            float(it.get("Subtotal", 0) or 0)
        ])
    apply_header_styles(ws_items)
    if member_items:
        apply_data_row_styles(ws_items, 2, len(member_items) + 1, len(headers_items))
    auto_fit_columns(ws_items)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


def generate_admin_master_workbook(admin_username="Master Administrator"):
    """
    Generates the comprehensive 9-worksheet Excel workbook requested by specifications:
    1. All Orders
    2. Order Items
    3. Members (excludes code hashes)
    4. Customer Details
    5. Payment History
    6. Member Summary
    7. Location Summary
    8. Cake Summary
    9. Financial Summary
    """
    all_orders = sheets_service.get_all_records("Orders")
    all_items = sheets_service.get_all_records("Order_Items")
    all_members = sheets_service.get_all_records("Members")
    all_customers = sheets_service.get_all_records("Customers")
    all_payments = sheets_service.get_all_records("Payments")
    all_locations = sheets_service.get_all_records("Locations")
    all_cakes = sheets_service.get_all_records("Cake_Settings")

    cust_map = {c.get("Customer ID"): c for c in all_customers}
    member_map = {m.get("Member ID"): m for m in all_members}

    wb = openpyxl.Workbook()

    # --- Sheet 1: All Orders ---
    ws1 = wb.active
    ws1.title = "All Orders"
    h1 = [
        "Order ID", "Customer Name", "Customer Phone", "Member Name", "Location",
        "Order Date", "Total Amount (₹)", "Amount Paid (₹)", "Remaining (₹)", 
        "Payment Status", "Verification Status", "Special Instructions", "Created Date"
    ]
    ws1.append(h1)
    for o in all_orders:
        c = cust_map.get(o.get("Customer ID"), {})
        m = member_map.get(o.get("Member ID"), {})
        ws1.append([
            o.get("Order ID"),
            c.get("Customer Name", "Unknown"),
            c.get("Phone Number", ""),
            m.get("Member Name", "Unknown"),
            c.get("Location", m.get("Location", "")),
            o.get("Order Date"),
            float(o.get("Total Amount", 0) or 0),
            float(o.get("Total Amount Paid", 0) or 0),
            float(o.get("Remaining Amount", 0) or 0),
            o.get("Payment Status"),
            o.get("Verification Status"),
            o.get("Special Instructions", ""),
            o.get("Created Date")
        ])
    apply_header_styles(ws1)
    if all_orders:
        apply_data_row_styles(ws1, 2, len(all_orders) + 1, len(h1))
    auto_fit_columns(ws1)

    # --- Sheet 2: Order Items ---
    ws2 = wb.create_sheet(title="Order Items")
    h2 = ["Order Item ID", "Order ID", "Cake Variety", "Weight", "Quantity", "Unit Price (₹)", "Subtotal (₹)", "Historical Price (₹)"]
    ws2.append(h2)
    for it in all_items:
        ws2.append([
            it.get("Order Item ID"),
            it.get("Order ID"),
            it.get("Cake Name"),
            it.get("Weight"),
            int(it.get("Quantity", 1) or 1),
            float(it.get("Unit Price", 0) or 0),
            float(it.get("Subtotal", 0) or 0),
            float(it.get("Historical Price", 0) or 0)
        ])
    apply_header_styles(ws2)
    if all_items:
        apply_data_row_styles(ws2, 2, len(all_items) + 1, len(h2))
    auto_fit_columns(ws2)

    # --- Sheet 3: Members (NEVER include hashes or passwords) ---
    ws3 = wb.create_sheet(title="Members")
    h3 = ["Member ID", "Member Name", "Phone Number", "Email", "Location", "Account Status", "Date Created", "Last Login", "Notes"]
    ws3.append(h3)
    for m in all_members:
        ws3.append([
            m.get("Member ID"),
            m.get("Member Name"),
            m.get("Phone Number"),
            m.get("Email", ""),
            m.get("Location", ""),
            m.get("Account Status"),
            m.get("Date Created"),
            m.get("Last Login", ""),
            m.get("Notes", "")
        ])
    apply_header_styles(ws3)
    if all_members:
        apply_data_row_styles(ws3, 2, len(all_members) + 1, len(h3))
    auto_fit_columns(ws3)

    # --- Sheet 4: Customer Details ---
    ws4 = wb.create_sheet(title="Customer Details")
    h4 = ["Customer ID", "Customer Name", "Phone Number", "Alternate Phone", "Address", "Location", "Landmark", "Notes", "Created Date"]
    ws4.append(h4)
    for c in all_customers:
        ws4.append([
            c.get("Customer ID"),
            c.get("Customer Name"),
            c.get("Phone Number"),
            c.get("Alternate Phone Number", ""),
            c.get("Address", ""),
            c.get("Location", ""),
            c.get("Landmark", ""),
            c.get("Notes", ""),
            c.get("Created Date")
        ])
    apply_header_styles(ws4)
    if all_customers:
        apply_data_row_styles(ws4, 2, len(all_customers) + 1, len(h4))
    auto_fit_columns(ws4)

    # --- Sheet 5: Payment History ---
    ws5 = wb.create_sheet(title="Payment History")
    h5 = ["Payment ID", "Order ID", "Member ID", "Amount (₹)", "Date", "Time", "Payment Method", "Reference", "Recorded By", "Verification Status", "Verified By", "Notes"]
    ws5.append(h5)
    for p in all_payments:
        ws5.append([
            p.get("Payment ID"),
            p.get("Order ID"),
            p.get("Member ID"),
            float(p.get("Payment Amount", 0) or 0),
            p.get("Payment Date"),
            p.get("Payment Time"),
            p.get("Payment Method"),
            p.get("Payment Reference", ""),
            p.get("Recorded By"),
            p.get("Verification Status"),
            p.get("Verified By", ""),
            p.get("Notes", "")
        ])
    apply_header_styles(ws5)
    if all_payments:
        apply_data_row_styles(ws5, 2, len(all_payments) + 1, len(h5))
    auto_fit_columns(ws5)

    # --- Sheet 6: Member Summary ---
    ws6 = wb.create_sheet(title="Member Summary")
    h6 = ["Member ID", "Member Name", "Location", "Total Orders", "Total Cakes Sold", "Total Sales (₹)", "Amount Collected (₹)", "Pending Amount (₹)"]
    ws6.append(h6)
    
    # Calculate member stats
    member_stats = {}
    for m in all_members:
        mid = m.get("Member ID")
        member_stats[mid] = {
            "name": m.get("Member Name"),
            "loc": m.get("Location", ""),
            "orders": 0,
            "cakes": 0,
            "sales": 0.0,
            "collected": 0.0,
            "pending": 0.0
        }

    for o in all_orders:
        mid = o.get("Member ID")
        if mid in member_stats:
            member_stats[mid]["orders"] += 1
            tot = float(o.get("Total Amount", 0) or 0)
            pd = float(o.get("Total Amount Paid", 0) or 0)
            rem = float(o.get("Remaining Amount", 0) or 0)
            member_stats[mid]["sales"] += tot
            member_stats[mid]["collected"] += pd
            member_stats[mid]["pending"] += rem

    for it in all_items:
        oid = it.get("Order ID")
        ord_rec = next((o for o in all_orders if o.get("Order ID") == oid), None)
        if ord_rec:
            mid = ord_rec.get("Member ID")
            if mid in member_stats:
                member_stats[mid]["cakes"] += int(it.get("Quantity", 1) or 1)

    for mid, st in member_stats.items():
        ws6.append([
            mid, st["name"], st["loc"], st["orders"], st["cakes"],
            round(st["sales"], 2), round(st["collected"], 2), round(st["pending"], 2)
        ])
    apply_header_styles(ws6)
    if member_stats:
        apply_data_row_styles(ws6, 2, len(member_stats) + 1, len(h6))
    auto_fit_columns(ws6)

    # --- Sheet 7: Location Summary ---
    ws7 = wb.create_sheet(title="Location Summary")
    h7 = ["Location Name", "Total Orders", "Total Sales (₹)", "Amount Collected (₹)", "Pending Amount (₹)"]
    ws7.append(h7)

    loc_stats = {}
    for o in all_orders:
        c = cust_map.get(o.get("Customer ID"), {})
        m = member_map.get(o.get("Member ID"), {})
        loc = c.get("Location") or m.get("Location") or "Unspecified"
        if loc not in loc_stats:
            loc_stats[loc] = {"orders": 0, "sales": 0.0, "collected": 0.0, "pending": 0.0}
        loc_stats[loc]["orders"] += 1
        loc_stats[loc]["sales"] += float(o.get("Total Amount", 0) or 0)
        loc_stats[loc]["collected"] += float(o.get("Total Amount Paid", 0) or 0)
        loc_stats[loc]["pending"] += float(o.get("Remaining Amount", 0) or 0)

    for loc_name, st in loc_stats.items():
        ws7.append([
            loc_name, st["orders"], round(st["sales"], 2), round(st["collected"], 2), round(st["pending"], 2)
        ])
    apply_header_styles(ws7)
    if loc_stats:
        apply_data_row_styles(ws7, 2, len(loc_stats) + 1, len(h7))
    auto_fit_columns(ws7)

    # --- Sheet 8: Cake Summary ---
    ws8 = wb.create_sheet(title="Cake Summary")
    h8 = ["Cake Variety", "Weight", "Quantity Sold", "Total Revenue (₹)"]
    ws8.append(h8)
    cake_summary = {}
    for it in all_items:
        key = (it.get("Cake Name", "Unknown"), it.get("Weight", ""))
        if key not in cake_summary:
            cake_summary[key] = {"qty": 0, "rev": 0.0}
        cake_summary[key]["qty"] += int(it.get("Quantity", 1) or 1)
        cake_summary[key]["rev"] += float(it.get("Subtotal", 0) or 0)

    for (cname, wgt), st in cake_summary.items():
        ws8.append([cname, wgt, st["qty"], round(st["rev"], 2)])
    apply_header_styles(ws8)
    if cake_summary:
        apply_data_row_styles(ws8, 2, len(cake_summary) + 1, len(h8))
    auto_fit_columns(ws8)

    # --- Sheet 9: Financial Summary ---
    ws9 = wb.create_sheet(title="Financial Summary")
    h9 = ["Metric", "Value", "Description"]
    ws9.append(h9)

    grand_sales = sum(float(o.get("Total Amount", 0) or 0) for o in all_orders)
    grand_collected = sum(float(p.get("Payment Amount", 0) or 0) for p in all_payments if str(p.get("Verification Status")).lower() != "rejected")
    grand_pending = max(0.0, grand_sales - grand_collected)
    verified_payments = sum(float(p.get("Payment Amount", 0) or 0) for p in all_payments if str(p.get("Verification Status")).lower() == "verified")
    unverified_payments = sum(float(p.get("Payment Amount", 0) or 0) for p in all_payments if str(p.get("Verification Status")).lower() == "pending verification")

    fin_rows = [
        ["Total Orders Recorded", len(all_orders), "Sum of all confirmed customer orders"],
        ["Total Cakes Sold", sum(int(it.get("Quantity", 1) or 1) for it in all_items), "Total units of cake varieties ordered"],
        ["Gross Sales", f"₹ {grand_sales:,.2f}", "Total monetary value of all cake orders"],
        ["Total Amount Collected", f"₹ {grand_collected:,.2f}", "Total valid recorded payments"],
        ["Total Outstanding / Pending", f"₹ {grand_pending:,.2f}", "Gross Sales minus Total Amount Collected"],
        ["Verified Payments Total", f"₹ {verified_payments:,.2f}", "Payments officially verified by administrator"],
        ["Awaiting Verification Total", f"₹ {unverified_payments:,.2f}", "Payments awaiting admin review"],
        ["Active Members Count", sum(1 for m in all_members if str(m.get("Account Status")).lower() == "active"), "Active youth group members"],
        ["Total Customers Registered", len(all_customers), "Unique customer contacts registered"]
    ]
    for r in fin_rows:
        ws9.append(r)
    apply_header_styles(ws9)
    apply_data_row_styles(ws9, 2, len(fin_rows) + 1, len(h9))
    auto_fit_columns(ws9)

    # Log Excel download audit event
    log_activity(
        admin_username,
        "EXCEL_EXPORT",
        f"Administrator {admin_username} downloaded Complete Master Excel Workbook (9 sheets)."
    )

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream
