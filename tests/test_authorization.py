"""Tests verifying users cannot access each other's resources."""
import json
import pytest
from database import db, Implant, Procedure, ProcedureImplant
from tests.helpers import AJAX_HEADERS


@pytest.fixture()
def implant_b(app, second_user):
    i = Implant(
        size="5.0x14.0",
        brand="Astra",
        stock=8,
        min_stock=1,
        user_id=second_user.id,
    )
    db.session.add(i)
    db.session.commit()
    return i


@pytest.fixture()
def procedure_b(app, second_user):
    p = Procedure(patient_name="Bob Patient", user_id=second_user.id)
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture()
def procedure_b_with_implant(app, second_user, implant_b):
    p = Procedure(patient_name="Bob Procedure", user_id=second_user.id)
    db.session.add(p)
    db.session.flush()
    item = ProcedureImplant(procedure_id=p.id, implant_id=implant_b.id, quantity=2)
    db.session.add(item)
    db.session.commit()
    return p


class TestImplantAuthorization:
    """User A (auth_client) cannot operate on User B's implants."""

    def test_cannot_view_edit_form_for_other_users_implant(self, auth_client, implant_b):
        resp = auth_client.get(f"/edit/{implant_b.id}")
        assert resp.status_code == 404

    def test_cannot_edit_other_users_implant(self, auth_client, implant_b):
        resp = auth_client.post(
            f"/edit/{implant_b.id}",
            data={"size": "5.0x14.0", "brand": "Astra", "custom_brand": "", "stock": "0", "min_stock": "1"},
        )
        assert resp.status_code == 404
        db.session.refresh(implant_b)
        assert implant_b.stock == 8  # Unchanged

    def test_cannot_use_other_users_implant(self, auth_client, implant_b):
        resp = auth_client.post(f"/use/{implant_b.id}", headers=AJAX_HEADERS)
        assert resp.status_code == 404
        db.session.refresh(implant_b)
        assert implant_b.stock == 8

    def test_cannot_add_stock_to_other_users_implant(self, auth_client, implant_b):
        resp = auth_client.post(
            f"/add_stock/{implant_b.id}",
            data={"quantity": "5"},
        )
        assert resp.status_code == 404
        db.session.refresh(implant_b)
        assert implant_b.stock == 8

    def test_cannot_remove_other_users_implant(self, auth_client, implant_b):
        resp = auth_client.get(f"/remove/{implant_b.id}")
        assert resp.status_code == 404
        assert db.session.get(Implant, implant_b.id) is not None

    def test_other_users_implants_not_shown_in_index(self, auth_client, implant_b):
        resp = auth_client.get("/")
        assert resp.status_code == 200
        # User B's implant should not appear in User A's inventory
        assert b"5.0x14.0" not in resp.data

    def test_cannot_update_min_stock_for_other_users_implant(self, auth_client, implant_b):
        resp = auth_client.post(
            f"/update_min_stock/{implant_b.id}",
            data={"min_stock": "99"},
        )
        assert resp.status_code == 404
        db.session.refresh(implant_b)
        assert implant_b.min_stock == 1  # Unchanged


class TestProcedureAuthorization:
    """User A cannot operate on User B's procedures."""

    def test_cannot_edit_other_users_procedure(self, auth_client, procedure_b):
        resp = auth_client.get(f"/procedures/{procedure_b.id}/edit")
        assert resp.status_code == 404

    def test_cannot_add_implant_to_other_users_procedure(self, auth_client, procedure_b, implant):
        resp = auth_client.post(
            f"/procedures/{procedure_b.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "1"},
            headers=AJAX_HEADERS,
        )
        assert resp.status_code == 404

    def test_cannot_confirm_other_users_procedure(self, auth_client, procedure_b_with_implant):
        resp = auth_client.post(
            f"/procedures/{procedure_b_with_implant.id}/confirm",
            headers=AJAX_HEADERS,
        )
        assert resp.status_code == 404

    def test_cannot_cancel_other_users_procedure(self, auth_client, procedure_b):
        resp = auth_client.post(
            f"/procedures/{procedure_b.id}/cancel",
            headers=AJAX_HEADERS,
        )
        assert resp.status_code == 404
        assert db.session.get(Procedure, procedure_b.id) is not None

    def test_cannot_undo_other_users_procedure(self, auth_client, procedure_b_with_implant):
        # Force procedure into completed state directly so we can test undo authorization
        procedure_b_with_implant.status = "completed"
        db.session.commit()

        resp = auth_client.post(
            f"/procedures/{procedure_b_with_implant.id}/undo",
            headers=AJAX_HEADERS,
        )
        assert resp.status_code == 404
        db.session.refresh(procedure_b_with_implant)
        assert procedure_b_with_implant.status == "completed"

    def test_other_users_procedures_not_shown(self, auth_client, procedure_b):
        resp = auth_client.get("/procedures")
        assert resp.status_code == 200
        assert b"Bob Patient" not in resp.data

    def test_cannot_set_item_quantity_for_other_users_procedure(
        self, auth_client, procedure_b_with_implant
    ):
        item = procedure_b_with_implant.items[0]
        resp = auth_client.post(
            f"/procedures/{procedure_b_with_implant.id}/item/{item.id}/set-quantity",
            data={"quantity": "10"},
        )
        assert resp.status_code == 404

    def test_cannot_remove_implant_from_other_users_procedure(
        self, auth_client, procedure_b_with_implant
    ):
        item = procedure_b_with_implant.items[0]
        resp = auth_client.post(
            f"/procedures/{procedure_b_with_implant.id}/remove-implant/{item.id}",
            headers=AJAX_HEADERS,
        )
        assert resp.status_code == 404
        assert db.session.get(ProcedureImplant, item.id) is not None
