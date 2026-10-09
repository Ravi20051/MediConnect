"""
MediConnect Authentication Test Suite
Tests backend login, registration, validation, role restrictions, and duplicate handling.
"""
from fastapi.testclient import TestClient
from backend.main import app

def test_full_auth_flow():
    client = TestClient(app)
    
    # 1. Valid login with existing seeded user
    res_login = client.post("/api/auth/login", json={"username": "asha_sunita", "password": "asha123"})
    assert res_login.status_code == 200, f"Expected 200, got {res_login.status_code}"
    body = res_login.json()
    assert body.get("token") is not None
    assert body.get("user", {}).get("username") == "asha_sunita"
    print("PASS 1: Valid Login with asha_sunita")
    
    # 2. Invalid password
    res_bad_pwd = client.post("/api/auth/login", json={"username": "asha_sunita", "password": "wrongpassword"})
    assert res_bad_pwd.status_code == 401
    print("PASS 2: Invalid password rejected with 401")

    # 3. Non-existent user
    res_no_user = client.post("/api/auth/login", json={"username": "non_existent_user_999", "password": "any"})
    assert res_no_user.status_code == 401
    print("PASS 3: Non-existent user rejected with 401")

    # 4. Valid Registration
    import time
    new_username = f"asha_test_{int(time.time())}"
    reg_payload = {
        "full_name": "Pooja Verma",
        "username": new_username,
        "password": "securepassword123",
        "village": "Chandpur",
        "sub_center": "Chandpur Sub-Center",
        "phone": "9876543210"
    }
    res_reg = client.post("/api/auth/register", json=reg_payload)
    assert res_reg.status_code == 201, f"Expected 201, got {res_reg.status_code}: {res_reg.text}"
    reg_data = res_reg.json()
    assert reg_data.get("success") is True
    assert reg_data.get("user", {}).get("role") == "asha_worker", "Role must strictly be asha_worker"
    print(f"PASS 4: Valid Registration for {new_username}")

    # 5. Duplicate username rejection
    res_dup = client.post("/api/auth/register", json=reg_payload)
    assert res_dup.status_code == 400
    assert "already registered" in res_dup.json().get("detail", "").lower()
    print("PASS 5: Duplicate username properly rejected with 400")

    # 6. Immediate login with the new registered account
    res_new_login = client.post("/api/auth/login", json={"username": new_username, "password": "securepassword123"})
    assert res_new_login.status_code == 200
    new_login_data = res_new_login.json()
    assert new_login_data.get("user", {}).get("full_name") == "Pooja Verma"
    assert new_login_data.get("user", {}).get("village") == "Chandpur"
    print("PASS 6: Immediate login with newly registered account successful")

    print("\nALL 6 AUTHENTICATION CONTRACT TESTS PASSED!")

if __name__ == "__main__":
    test_full_auth_flow()
