def test_register_new_user(client):
    response = client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "testpassword123",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "hashed_password" not in data


def test_register_duplicate_email(client):
    client.post("/auth/register", json={"email": "dup@example.com", "password": "pass1234"})
    response = client.post("/auth/register", json={"email": "dup@example.com", "password": "pass5678"})
    assert response.status_code == 400


def test_login_success(client):
    client.post("/auth/register", json={"email": "login@example.com", "password": "mypassword"})
    response = client.post("/auth/login", json={"email": "login@example.com", "password": "mypassword"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password(client):
    client.post("/auth/register", json={"email": "wrong@example.com", "password": "correctpass"})
    response = client.post("/auth/login", json={"email": "wrong@example.com", "password": "wrongpass"})
    assert response.status_code == 401


def test_me_requires_auth(client):
    response = client.get("/auth/me")
    assert response.status_code == 403  # HTTPBearer returns 403 when no header is sent at all


def test_me_with_valid_token(client):
    client.post("/auth/register", json={"email": "me@example.com", "password": "mypassword"})
    login_response = client.post("/auth/login", json={"email": "me@example.com", "password": "mypassword"})
    token = login_response.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"