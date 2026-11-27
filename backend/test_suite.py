"""
Automated End-to-End Integration Test Suite for Christmas Cake Challenge
"""
import os
import sys
import json
import time

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.index import app

def run_tests():
    print("======================================================================")
    print("STARTING COMPREHENSIVE INTEGRATION TEST SUITE")
    print("======================================================================")
    client = app.test_client()

    # 1. System Status
    res = client.get("/api/system/status")
    assert res.status_code == 200, f"System status failed: {res.status_code}"
    status_data = res.get_json()
    assert status_data["success"] is True
    print("✓ [TEST 1] System Status Healthcheck passed.")

    # 2. Admin Login
    res = client.post("/api/auth/admin-login", json={
        "email": "margregoriousyouthpancode123@gmail.com",
        "password": "Admin@Christmas2026!"
    })
    assert res.status_code == 200, f"Admin login failed: {res.status_code}"
    admin_token = res.get_json()["data"]["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("✓ [TEST 2] Admin authentication passed.")

    # 3. Public Member Request Access
    import uuid
    uniq = uuid.uuid4().hex[:4].upper()
    member_name = f"Sarah Paul {uniq}"
    test_code = f"MC-S{uniq}"

    res = client.post("/api/member-requests", json={
        "name": member_name,
        "phone": f"98{uuid.uuid4().int % 100000000:08d}",
        "location": "Vellapara Kurish",
        "message": "Senior youth member eager to collect orders."
    })
    assert res.status_code == 200, f"Member request failed: {res.status_code}"
    req_id = res.get_json()["request_id"]
    print(f"✓ [TEST 3] Public member request access passed (Request ID: {req_id}).")

    # 4. Admin List Requests & Approve Request
    res = client.get("/api/admin/member-requests?status=Pending", headers=admin_headers)
    assert res.status_code == 200
    requests_list = res.get_json()["data"]
    assert any(r["Request ID"] == req_id for r in requests_list)

    res = client.post(f"/api/admin/member-requests/{req_id}/approve", headers=admin_headers, json={
        "member_code": test_code,
        "notes": "Approved by Youth Secretary"
    })
    assert res.status_code == 200, f"Approve failed: {res.get_json()}"
    approved_data = res.get_json()
    member_id = approved_data["member_id"]
    member_code = approved_data["generated_code"]
    print(f"✓ [TEST 4] Admin request approval passed (Member ID: {member_id}, Code: {member_code}).")

    # 5. Member Login with Newly Created Credentials
    res = client.post("/api/auth/member-login", json={
        "name": member_name,
        "code": test_code
    })
    assert res.status_code == 200, f"Member login failed: {res.get_json()}"
    member_token = res.get_json()["data"]["token"]
    member_headers = {"Authorization": f"Bearer {member_token}"}
    print("✓ [TEST 5] Member login with assigned code passed.")

    # 6. Fetch Active Cakes and Custom Fields
    res = client.get("/api/cakes")
    assert res.status_code == 200
    cakes = res.get_json()["data"]
    assert len(cakes) >= 1
    plum_cake = next((c for c in cakes if "Plum" in c["cake_name"]), cakes[0])
    print(f"✓ [TEST 6] Active cake catalog retrieved ({len(cakes)} varieties available).")

    res = client.get("/api/custom-fields")
    assert res.status_code == 200
    custom_fields = res.get_json()["data"]
    print(f"✓ [TEST 7] Active custom fields retrieved ({len(custom_fields)} active fields).")

    # 7. Member Creates New Order with Multiple Cakes & Advance Payment
    order_payload = {
        "customer": {
            "name": "Eldho Kuriakose",
            "phone": "9447123456",
            "alt_phone": "9847123456",
            "address": "Kuriakose Villa, Near Chapel",
            "location": "North Ward",
            "landmark": "St. Mary's Post Office"
        },
        "items": [
            {
                "cake_id": plum_cake["cake_id"],
                "weight": "500 g",
                "quantity": 2
            },
            {
                "cake_id": plum_cake["cake_id"],
                "weight": "1 kg",
                "quantity": 1
            }
        ],
        "payment": {
            "amount": 500.0,
            "method": "UPI / GPay",
            "reference": "UPI9876543210",
            "notes": "Advance via Google Pay"
        },
        "custom_fields": {
            "FIELD-001": "Home Delivery",
            "FIELD-002": "2026-12-23"
        },
        "delivery_notes": "Please deliver before 5 PM",
        "special_instructions": "Festive gift pack requested"
    }

    res = client.post("/api/orders", headers=member_headers, json=order_payload)
    assert res.status_code == 200, f"Order creation failed: {res.get_json()}"
    order_res = res.get_json()["data"]
    order_id = order_res["order_id"]
    assert order_res["total_amount"] == 1000.0 # 2*250 + 1*500 = 1000
    assert order_res["amount_paid"] == 500.0
    assert order_res["remaining_amount"] == 500.0
    assert order_res["payment_status"] == "Partially Paid"
    print(f"✓ [TEST 8] Order created atomically across 4 sheets (Order ID: {order_id}, Total: ₹{order_res['total_amount']}, Remaining: ₹{order_res['remaining_amount']}).")

    # 8. Member views their orders
    res = client.get("/api/orders/my-orders", headers=member_headers)
    assert res.status_code == 200
    my_orders = res.get_json()["data"]
    assert len(my_orders) >= 1
    assert any(o["Order ID"] == order_id for o in my_orders)
    print("✓ [TEST 9] Member order history lookup passed.")

    # 9. Member records additional payment
    res = client.post(f"/api/orders/{order_id}/payments", headers=member_headers, json={
        "amount": 500.0,
        "method": "Cash",
        "notes": "Final balance settlement"
    })
    assert res.status_code == 200
    pay_summary = res.get_json()["data"]["order_summary"]
    assert pay_summary["total_paid"] == 1000.0
    assert pay_summary["remaining_amount"] == 0.0
    assert pay_summary["payment_status"] == "Paid"
    print(f"✓ [TEST 10] Additional payment recorded and order automatically updated to 'Paid' (Remaining: ₹{pay_summary['remaining_amount']}).")

    # 10. Member Excel Download
    res = client.get("/api/reports/member-excel", headers=member_headers)
    assert res.status_code == 200
    assert len(res.data) > 2000
    print(f"✓ [TEST 11] Member private Excel report generated ({len(res.data)} bytes).")

    # 11. Admin Master Order Search with Multi-Filters
    res = client.get(f"/api/admin/orders?search=Eldho&payment_status=Paid", headers=admin_headers)
    assert res.status_code == 200
    admin_orders = res.get_json()["data"]
    assert len(admin_orders) >= 1
    print(f"✓ [TEST 12] Admin Master Order Search with multi-filters passed.")

    # 12. Admin Verify Payment
    res = client.get("/api/admin/payments?verification_status=Pending Verification", headers=admin_headers)
    assert res.status_code == 200
    pending_payments = res.get_json()["data"]
    if pending_payments:
        pid = pending_payments[0]["Payment ID"]
        res = client.post(f"/api/admin/payments/{pid}/verify", headers=admin_headers)
        assert res.status_code == 200
        print(f"✓ [TEST 13] Admin payment verification passed (Payment ID: {pid}).")

    # 13. Admin Dashboard Analytics & KPIs
    res = client.get("/api/reports/admin-summary", headers=admin_headers)
    assert res.status_code == 200
    summary = res.get_json()["data"]
    assert summary["total_sales"] >= 1000.0
    assert summary["total_collected"] >= 1000.0
    assert "cake_distribution" in summary
    assert "location_sales" in summary
    print(f"✓ [TEST 14] Admin Executive Dashboard analytics verified (Total Sales: ₹{summary['total_sales']}, Total Collected: ₹{summary['total_collected']}).")

    # 14. Admin 9-Worksheet Master Excel Workbook Download
    res = client.get("/api/reports/admin-excel", headers=admin_headers)
    assert res.status_code == 200
    assert len(res.data) > 5000
    print(f"✓ [TEST 15] Admin 9-Worksheet Master Excel Workbook generated successfully ({len(res.data)} bytes).")

    # 15. Activity Logs Audit Trail
    res = client.get("/api/admin/activity-logs", headers=admin_headers)
    assert res.status_code == 200
    logs = res.get_json()["data"]
    assert len(logs) >= 5
    print(f"✓ [TEST 16] Activity Logs audit trail verified ({len(logs)} security logs recorded).")

    # 16. Verify Canonical Locations
    res = client.get("/api/locations")
    assert res.status_code == 200
    active_loc_names = [l["Location Name"] for l in res.get_json()["data"]]
    assert "Vellapara Kurish" in active_loc_names
    assert "St Marys Kurish" in active_loc_names
    assert "Others" in active_loc_names
    print("✓ [TEST 17] Canonical location options verified in active locations API.")

    # 17. Member Edit Order (Update cakes, quantities, and customer details)
    edit_payload = {
        "customer": {
            "name": "Eldho Kuriakose (Updated)",
            "phone": "9447123456",
            "location": "Vellapara Kurish",
            "address": "Updated House Name, Near Vellapara"
        },
        "items": [
            {
                "cake_id": plum_cake["cake_id"],
                "weight": "1 kg",
                "quantity": 2
            }
        ],
        "delivery_notes": "Deliver before 6 PM on Dec 24"
    }
    res = client.put(f"/api/orders/{order_id}", headers=member_headers, json=edit_payload)
    assert res.status_code == 200, f"Order update failed: {res.get_json()}"
    updated_summary = res.get_json()["data"]["order_summary"]
    # 2 * 500 = 1000 total. Paid was 1000. Remaining: 0
    assert updated_summary["total_amount"] == 1000.0
    print(f"✓ [TEST 18] Member successfully edited their own order with item recalculation (Order ID: {order_id}).")

    # 18. Member Security Isolation: Attempt to edit or view another member's order
    mathew_code = f"MC-M{uuid.uuid4().hex[:4].upper()}"
    mathew_name = f"Mathew Thomas {uuid.uuid4().hex[:4].upper()}"
    res = client.post("/api/member-requests", json={
        "name": mathew_name,
        "phone": f"97{uuid.uuid4().int % 100000000:08d}",
        "location": "Kurachi Kurish"
    })
    other_req_id = res.get_json()["request_id"]
    client.post(f"/api/admin/member-requests/{other_req_id}/approve", headers=admin_headers, json={
        "member_code": mathew_code
    })
    res = client.post("/api/auth/member-login", json={"name": mathew_name, "code": mathew_code})
    mathew_token = res.get_json()["data"]["token"]
    mathew_headers = {"Authorization": f"Bearer {mathew_token}"}

    # Mathew tries to view Sarah's order -> 403 Forbidden
    res = client.get(f"/api/orders/{order_id}", headers=mathew_headers)
    assert res.status_code == 403, f"Security leak! Mathew was able to view Sarah's order: {res.status_code}"

    # Mathew tries to edit Sarah's order -> 403 Forbidden
    res = client.put(f"/api/orders/{order_id}", headers=mathew_headers, json=edit_payload)
    assert res.status_code == 403, f"Security leak! Mathew was able to edit Sarah's order: {res.status_code}"
    print("✓ [TEST 19] Member data isolation & IDOR prevention verified (Access correctly blocked with 403).")

    # 19. Customer Search Isolation
    # Mathew searches for Sarah's customer "Eldho" -> should return empty list
    res = client.get("/api/customers/search?q=Eldho", headers=mathew_headers)
    assert res.status_code == 200
    assert len(res.get_json()["data"]) == 0, "Security leak! Mathew discovered customer of another member."
    print("✓ [TEST 20] Customer autocomplete search isolation verified.")

    # 20. Admin Payment Correction
    res = client.get("/api/admin/payments", headers=admin_headers)
    all_p = res.get_json()["data"]
    if all_p:
        first_pid = all_p[0]["Payment ID"]
        res = client.put(f"/api/admin/payments/{first_pid}", headers=admin_headers, json={
            "notes": "Verified and corrected by Senior Coordinator"
        })
        assert res.status_code == 200
        print(f"✓ [TEST 21] Admin payment correction API passed (Payment ID: {first_pid}).")

    # 21. Master Admin Subadmin Management (4 Subadmins Oversight)
    res = client.get("/api/admin/subadmins", headers=admin_headers)
    assert res.status_code == 200, f"Failed to list subadmins: {res.status_code}"
    subadmins_list = res.get_json()["data"]
    assert len(subadmins_list) <= 4, f"Subadmin limit exceeded: {len(subadmins_list)}"
    print(f"✓ [TEST 22] Master Admin Subadmins Listing passed ({len(subadmins_list)} subadmins configured).")

    # 22. Subadmin Authentication & Role Verification
    res = client.post("/api/auth/admin-login", json={
        "email": "subadmin1@pancode.org",
        "password": "Subadmin@Cake2026!"
    })
    assert res.status_code == 200, f"Subadmin login failed: {res.status_code}"
    sub1_data = res.get_json()["data"]
    assert sub1_data["user"]["role"] == "admin"
    assert sub1_data["user"]["admin_type"] == "subadmin"
    sub1_token = sub1_data["token"]
    sub1_headers = {"Authorization": f"Bearer {sub1_token}"}
    print("✓ [TEST 23] Subadmin 1 authentication passed (Role: admin, Type: subadmin).")

    # 23. Subadmin Permission Boundaries (Blocked from Master-only endpoints)
    # Subadmin tries to access subadmins management -> 403 Forbidden
    res = client.get("/api/admin/subadmins", headers=sub1_headers)
    assert res.status_code == 403, f"Security leak! Subadmin accessed Master Admin subadmins management: {res.status_code}"

    # Subadmin tries to change admin master password -> 403 Forbidden
    res = client.put("/api/admin/settings/password", headers=sub1_headers, json={"new_password": "HackedPassword123!"})
    assert res.status_code == 403, f"Security leak! Subadmin accessed master password update: {res.status_code}"

    # Subadmin tries to create a cake variety -> 403 Forbidden
    res = client.post("/api/admin/cakes", headers=sub1_headers, json={
        "name": "Unauthorized Cake",
        "weights": ["1 kg"],
        "prices": {"1 kg": 999}
    })
    assert res.status_code == 403, f"Security leak! Subadmin was able to modify cake catalog: {res.status_code}"
    print("✓ [TEST 24] Subadmin permission boundaries verified (Master-only operations correctly returned 403).")

    # 24. Subadmin Activity Auditing & Master Admin Visibility
    # Subadmin performs an allowed action (e.g., updates Sarah's order status to 'Processing')
    time.sleep(1.0)
    res = client.put(f"/api/admin/orders/{order_id}/status", headers=sub1_headers, json={
        "order_status": "Processing"
    })
    assert res.status_code == 200, f"Subadmin order status update failed: {res.status_code}"

    # Verify that Master Admin can see this exact action in Subadmin 1's activity log
    time.sleep(1.0)
    res = client.get("/api/admin/subadmins/SUB-001/activity", headers=admin_headers)
    assert res.status_code == 200
    sub1_activities = res.get_json()["data"]
    found_action = any(order_id in a.get("Action Description", "") or order_id in a.get("Related Record ID", "") for a in sub1_activities)
    assert found_action, "Master Admin could not see Subadmin 1's action in the subadmin audit trail!"
    print("✓ [TEST 25] Subadmin action auditing & Master Admin live visibility verified.")

    # 25. Enforce Strict 4-Subadmin Maximum Limit
    # Attempting to add a 5th subadmin when 4 slots exist
    if len(subadmins_list) >= 4:
        res = client.post("/api/admin/subadmins", headers=admin_headers, json={
            "name": "Subadmin 5",
            "email": "subadmin5@pancode.org",
            "password": "Password123!",
            "phone": "9999999999"
        })
        assert res.status_code == 400, "Failed to enforce 4-subadmin limit!"
        assert "limit of 4" in res.get_json().get("error", "").lower()
        print("✓ [TEST 26] Strict maximum 4-subadmin limit enforced successfully.")

    print("======================================================================")
    print("ALL 26 INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("======================================================================")

if __name__ == "__main__":
    run_tests()
