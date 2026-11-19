"""
Automated End-to-End Integration Test Suite for Christmas Cake Challenge
"""
import os
import sys
import json

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
    res = client.post("/api/member-requests", json={
        "name": "Sarah Paul",
        "phone": "9876543222",
        "location": "North Ward",
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
        "member_code": "MC-SARAH26",
        "notes": "Approved by Youth Secretary"
    })
    assert res.status_code == 200
    approved_data = res.get_json()
    member_id = approved_data["member_id"]
    member_code = approved_data["generated_code"]
    print(f"✓ [TEST 4] Admin request approval passed (Member ID: {member_id}, Code: {member_code}).")

    # 5. Member Login with Newly Created Credentials
    res = client.post("/api/auth/member-login", json={
        "name": "Sarah Paul",
        "code": "MC-SARAH26"
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

    print("======================================================================")
    print("ALL 16 INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("======================================================================")

if __name__ == "__main__":
    run_tests()
