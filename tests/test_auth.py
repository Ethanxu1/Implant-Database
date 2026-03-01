"""Tests for authentication routes."""
from database import db, User


class TestLogin:
    def test_get_login_page(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Login" in resp.data

    def test_login_valid_credentials(self, client, user):
        resp = client.post(
            "/login",
            data={"username": "testuser", "password": "password123"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Redirected to inventory dashboard
        assert b"Inventory" in resp.data or b"IMPLANTDB" in resp.data

    def test_login_wrong_password(self, client, user):
        resp = client.post(
            "/login",
            data={"username": "testuser", "password": "wrong"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Invalid username or password" in resp.data

    def test_login_nonexistent_user(self, client):
        resp = client.post(
            "/login",
            data={"username": "nobody", "password": "password"},
            follow_redirects=True,
        )
        assert b"Invalid username or password" in resp.data

    def test_authenticated_user_redirected_from_login(self, auth_client):
        resp = auth_client.get("/login", follow_redirects=False)
        assert resp.status_code == 302
        assert "/" in resp.headers["Location"]


class TestLogout:
    def test_logout_redirects_to_login(self, auth_client):
        resp = auth_client.get("/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]

    def test_logout_requires_login(self, client):
        resp = client.get("/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]


class TestRegister:
    def test_get_register_page(self, client):
        resp = client.get("/register")
        assert resp.status_code == 200
        assert b"Register" in resp.data

    def test_register_success(self, client):
        resp = client.post(
            "/register",
            data={
                "username": "newuser",
                "password": "securepass",
                "confirm_password": "securepass",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Registration successful" in resp.data
        assert User.query.filter_by(username="newuser").first() is not None

    def test_register_duplicate_username(self, client, user):
        resp = client.post(
            "/register",
            data={
                "username": "testuser",
                "password": "pass",
                "confirm_password": "pass",
            },
            follow_redirects=True,
        )
        assert b"Username already exists" in resp.data

    def test_register_password_mismatch(self, client):
        resp = client.post(
            "/register",
            data={
                "username": "newuser",
                "password": "pass1",
                "confirm_password": "pass2",
            },
            follow_redirects=True,
        )
        assert b"Passwords do not match" in resp.data
        assert User.query.filter_by(username="newuser").first() is None

    def test_authenticated_user_redirected_from_register(self, auth_client):
        resp = auth_client.get("/register", follow_redirects=False)
        assert resp.status_code == 302


class TestProfile:
    def test_get_profile_page(self, auth_client, user):
        resp = auth_client.get("/profile")
        assert resp.status_code == 200
        assert b"testuser" in resp.data

    def test_profile_requires_login(self, client):
        resp = client.get("/profile", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]


class TestChangePassword:
    def test_change_password_success(self, auth_client, user):
        resp = auth_client.post(
            "/change_password",
            data={
                "current_password": "password123",
                "new_password": "newpassword",
                "confirm_password": "newpassword",
            },
            follow_redirects=True,
        )
        assert b"Password changed successfully" in resp.data
        db.session.refresh(user)
        assert user.check_password("newpassword") is True

    def test_change_password_wrong_current(self, auth_client, user):
        resp = auth_client.post(
            "/change_password",
            data={
                "current_password": "wrong",
                "new_password": "newpassword",
                "confirm_password": "newpassword",
            },
            follow_redirects=True,
        )
        assert b"Current password is incorrect" in resp.data
        db.session.refresh(user)
        assert user.check_password("password123") is True

    def test_change_password_mismatch(self, auth_client, user):
        resp = auth_client.post(
            "/change_password",
            data={
                "current_password": "password123",
                "new_password": "new1",
                "confirm_password": "new2",
            },
            follow_redirects=True,
        )
        assert b"New passwords do not match" in resp.data
        db.session.refresh(user)
        assert user.check_password("password123") is True

    def test_change_password_requires_login(self, client):
        resp = client.post("/change_password", data={}, follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]


class TestDeleteAccount:
    def test_delete_account_success(self, auth_client, user):
        user_id = user.id
        resp = auth_client.post(
            "/delete_account",
            data={"password": "password123"},
            follow_redirects=True,
        )
        assert b"has been permanently deleted" in resp.data
        assert db.session.get(User, user_id) is None

    def test_delete_account_wrong_password(self, auth_client, user):
        user_id = user.id
        resp = auth_client.post(
            "/delete_account",
            data={"password": "wrongpass"},
            follow_redirects=True,
        )
        assert b"Password is incorrect" in resp.data
        assert db.session.get(User, user_id) is not None

    def test_delete_account_requires_login(self, client):
        resp = client.post("/delete_account", data={}, follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]
