"""Tests for implant management routes."""
import json
from database import db, Implant
from tests.helpers import AJAX_HEADERS


class TestIndex:
    def test_index_requires_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]

    def test_index_shows_implants(self, auth_client, implant):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        assert b"Hiossen" in resp.data
        assert b"4.5x11.5" in resp.data

    def test_index_empty_for_new_user(self, auth_client):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        assert b"No implants found" in resp.data

    def test_index_size_filter(self, auth_client, implant):
        resp = auth_client.get("/?size_filter=4.5")
        assert resp.status_code == 200
        assert b"4.5x11.5" in resp.data

    def test_index_size_filter_no_match(self, auth_client, implant):
        resp = auth_client.get("/?size_filter=9.9")
        assert resp.status_code == 200
        assert b"No implants found" in resp.data

    def test_index_brand_filter(self, auth_client, implant):
        resp = auth_client.get("/?brand_filter=Hiossen")
        assert resp.status_code == 200
        assert b"Hiossen" in resp.data

    def test_index_brand_filter_no_match(self, auth_client, implant):
        resp = auth_client.get("/?brand_filter=Astra")
        assert resp.status_code == 200
        assert b"No implants found" in resp.data


class TestAddImplant:
    def test_get_add_page(self, auth_client):
        resp = auth_client.get("/add")
        assert resp.status_code == 200
        assert b"Add New Implant" in resp.data

    def test_add_requires_login(self, client):
        resp = client.get("/add", follow_redirects=False)
        assert resp.status_code == 302

    def test_add_common_brand(self, auth_client):
        resp = auth_client.post(
            "/add",
            data={"size": "3.5x10.0", "brand": "Astra", "custom_brand": "", "stock": "5", "min_stock": "2"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Implant added successfully" in resp.data
        assert Implant.query.filter_by(size="3.5x10.0", brand="Astra").first() is not None

    def test_add_custom_brand(self, auth_client, user):
        resp = auth_client.post(
            "/add",
            data={"size": "4.0x12.0", "brand": "Other", "custom_brand": "Nobel Biocare", "stock": "3", "min_stock": "1"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        i = Implant.query.filter_by(brand="Nobel Biocare", user_id=user.id).first()
        assert i is not None
        assert i.size == "4.0x12.0"

    def test_add_duplicate_rejected(self, auth_client, implant):
        resp = auth_client.post(
            "/add",
            data={"size": "4.5x11.5", "brand": "Hiossen", "custom_brand": "", "stock": "3", "min_stock": "1"},
            follow_redirects=True,
        )
        assert b"already exists" in resp.data

    def test_add_initial_stock_zero(self, auth_client, user):
        resp = auth_client.post(
            "/add",
            data={"size": "3.7x8.0", "brand": "Megagen", "custom_brand": "", "stock": "0", "min_stock": "2"},
            follow_redirects=True,
        )
        assert b"Implant added successfully" in resp.data
        i = Implant.query.filter_by(size="3.7x8.0", user_id=user.id).first()
        assert i.stock == 0


class TestEditImplant:
    def test_get_edit_page(self, auth_client, implant):
        resp = auth_client.get(f"/edit/{implant.id}")
        assert resp.status_code == 200
        assert b"Edit Implant" in resp.data
        assert b"4.5x11.5" in resp.data

    def test_edit_requires_login(self, client, implant):
        resp = client.get(f"/edit/{implant.id}", follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_success(self, auth_client, implant):
        resp = auth_client.post(
            f"/edit/{implant.id}",
            data={"size": "4.5x13.0", "brand": "Hiossen", "custom_brand": "", "stock": "8", "min_stock": "3"},
            follow_redirects=True,
        )
        assert b"Implant updated successfully" in resp.data
        db.session.refresh(implant)
        assert implant.size == "4.5x13.0"
        assert implant.stock == 8
        assert implant.min_stock == 3

    def test_edit_duplicate_rejected(self, auth_client, user, implant):
        other = Implant(size="3.5x10.0", brand="Megagen", stock=5, min_stock=1, user_id=user.id)
        db.session.add(other)
        db.session.commit()

        resp = auth_client.post(
            f"/edit/{implant.id}",
            data={"size": "3.5x10.0", "brand": "Megagen", "custom_brand": "", "stock": "5", "min_stock": "1"},
            follow_redirects=True,
        )
        assert b"already exists" in resp.data

    def test_edit_nonexistent_implant_404(self, auth_client):
        resp = auth_client.get("/edit/99999")
        assert resp.status_code == 404


class TestUseImplant:
    def test_use_decrements_stock(self, auth_client, implant):
        original_stock = implant.stock
        resp = auth_client.post(f"/use/{implant.id}", follow_redirects=True)
        assert resp.status_code == 200
        db.session.refresh(implant)
        assert implant.stock == original_stock - 1

    def test_use_ajax_response_ok(self, auth_client, implant):
        original_stock = implant.stock
        resp = auth_client.post(f"/use/{implant.id}", headers=AJAX_HEADERS)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["new_stock"] == original_stock - 1

    def test_use_zero_stock_blocked(self, auth_client, zero_stock_implant):
        resp = auth_client.post(f"/use/{zero_stock_implant.id}", follow_redirects=True)
        assert resp.status_code == 200
        db.session.refresh(zero_stock_implant)
        assert zero_stock_implant.stock == 0

    def test_use_zero_stock_ajax_returns_error(self, auth_client, zero_stock_implant):
        resp = auth_client.post(f"/use/{zero_stock_implant.id}", headers=AJAX_HEADERS)
        data = json.loads(resp.data)
        assert data["ok"] is False
        assert "zero" in data["message"].lower()

    def test_use_requires_login(self, client, implant):
        resp = client.post(f"/use/{implant.id}", follow_redirects=False)
        assert resp.status_code == 302

    def test_use_nonexistent_implant_404(self, auth_client):
        resp = auth_client.post("/use/99999")
        assert resp.status_code == 404


class TestAddStock:
    def test_get_add_stock_page(self, auth_client, implant):
        resp = auth_client.get(f"/add_stock/{implant.id}")
        assert resp.status_code == 200

    def test_add_stock_increases_stock(self, auth_client, implant):
        original_stock = implant.stock
        resp = auth_client.post(
            f"/add_stock/{implant.id}",
            data={"quantity": "5"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        db.session.refresh(implant)
        assert implant.stock == original_stock + 5

    def test_add_stock_to_zero_stock_implant(self, auth_client, zero_stock_implant):
        resp = auth_client.post(
            f"/add_stock/{zero_stock_implant.id}",
            data={"quantity": "10"},
            follow_redirects=True,
        )
        db.session.refresh(zero_stock_implant)
        assert zero_stock_implant.stock == 10

    def test_add_stock_requires_login(self, client, implant):
        resp = client.get(f"/add_stock/{implant.id}", follow_redirects=False)
        assert resp.status_code == 302

    def test_add_stock_nonexistent_404(self, auth_client):
        resp = auth_client.get("/add_stock/99999")
        assert resp.status_code == 404


class TestRemoveImplant:
    def test_remove_implant_success(self, auth_client, implant):
        implant_id = implant.id
        resp = auth_client.get(f"/remove/{implant_id}", follow_redirects=True)
        assert resp.status_code == 200
        assert b"removed successfully" in resp.data
        assert db.session.get(Implant, implant_id) is None

    def test_remove_blocked_by_pending_procedure(self, auth_client, procedure_with_implant, implant):
        resp = auth_client.get(f"/remove/{implant.id}", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Cannot remove" in resp.data
        assert db.session.get(Implant, implant.id) is not None

    def test_remove_requires_login(self, client, implant):
        resp = client.get(f"/remove/{implant.id}", follow_redirects=False)
        assert resp.status_code == 302

    def test_remove_nonexistent_404(self, auth_client):
        resp = auth_client.get("/remove/99999")
        assert resp.status_code == 404


class TestUpdateMinStock:
    def test_update_min_stock_success(self, auth_client, implant):
        resp = auth_client.post(
            f"/update_min_stock/{implant.id}",
            data={"min_stock": "5"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"Minimum stock level updated" in resp.data
        db.session.refresh(implant)
        assert implant.min_stock == 5

    def test_update_min_stock_to_zero(self, auth_client, implant):
        resp = auth_client.post(
            f"/update_min_stock/{implant.id}",
            data={"min_stock": "0"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        db.session.refresh(implant)
        assert implant.min_stock == 0

    def test_update_min_stock_requires_login(self, client, implant):
        resp = client.post(
            f"/update_min_stock/{implant.id}",
            data={"min_stock": "5"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]

    def test_update_min_stock_nonexistent_404(self, auth_client):
        resp = auth_client.post("/update_min_stock/99999", data={"min_stock": "5"})
        assert resp.status_code == 404
