"""Tests for procedure workflow routes."""
import json
from datetime import date
from database import db, Implant, Procedure, ProcedureImplant
from tests.helpers import AJAX_HEADERS


class TestProceduresList:
    def test_list_requires_login(self, client):
        resp = client.get("/procedures", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]

    def test_list_shows_pending_procedures(self, auth_client, procedure):
        resp = auth_client.get("/procedures")
        assert resp.status_code == 200
        assert b"Alice Smith" in resp.data

    def test_list_garbage_collects_completed(self, auth_client, user, procedure_with_implant, implant):
        # Confirm the procedure so it becomes completed
        resp = auth_client.post(f"/procedures/{procedure_with_implant.id}/confirm", headers=AJAX_HEADERS)
        assert json.loads(resp.data)["ok"] is True
        # Visiting the list again should delete that completed procedure
        auth_client.get("/procedures")
        assert db.session.get(Procedure, procedure_with_implant.id) is None


class TestNewProcedure:
    def test_get_new_procedure_page(self, auth_client):
        resp = auth_client.get("/procedures/new")
        assert resp.status_code == 200
        assert b"Patient" in resp.data

    def test_create_procedure_without_date(self, auth_client, user):
        resp = auth_client.post(
            "/procedures/new",
            data={"patient_name": "Jane Doe", "date": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        p = Procedure.query.filter_by(patient_name="Jane Doe", user_id=user.id).first()
        assert p is not None
        assert p.date is None
        assert p.status == "pending"

    def test_create_procedure_with_date(self, auth_client, user):
        resp = auth_client.post(
            "/procedures/new",
            data={"patient_name": "John Doe", "date": "2026-03-15"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        p = Procedure.query.filter_by(patient_name="John Doe", user_id=user.id).first()
        assert p.date == date(2026, 3, 15)

    def test_create_procedure_empty_name_rejected(self, auth_client, user):
        resp = auth_client.post(
            "/procedures/new",
            data={"patient_name": "   ", "date": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"required" in resp.data.lower()
        assert Procedure.query.filter_by(user_id=user.id).count() == 0

    def test_create_procedure_invalid_date_rejected(self, auth_client, user):
        resp = auth_client.post(
            "/procedures/new",
            data={"patient_name": "Valid Name", "date": "not-a-date"},
            follow_redirects=True,
        )
        assert b"Invalid date" in resp.data
        assert Procedure.query.filter_by(patient_name="Valid Name").count() == 0

    def test_create_requires_login(self, client):
        resp = client.post("/procedures/new", data={}, follow_redirects=False)
        assert resp.status_code == 302


class TestEditProcedure:
    def test_get_edit_page(self, auth_client, procedure):
        resp = auth_client.get(f"/procedures/{procedure.id}/edit")
        assert resp.status_code == 200
        assert b"Alice Smith" in resp.data

    def test_edit_requires_login(self, client, procedure):
        resp = client.get(f"/procedures/{procedure.id}/edit", follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_updates_patient_name(self, auth_client, procedure):
        resp = auth_client.post(
            f"/procedures/{procedure.id}/edit",
            data={"patient_name": "Alice Jones", "date": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        db.session.refresh(procedure)
        assert procedure.patient_name == "Alice Jones"

    def test_edit_empty_name_rejected(self, auth_client, procedure):
        resp = auth_client.post(
            f"/procedures/{procedure.id}/edit",
            data={"patient_name": "  ", "date": ""},
            follow_redirects=True,
        )
        assert b"required" in resp.data.lower()
        db.session.refresh(procedure)
        assert procedure.patient_name == "Alice Smith"

    def test_edit_nonexistent_procedure_404(self, auth_client):
        resp = auth_client.get("/procedures/99999/edit")
        assert resp.status_code == 404

    def test_edit_with_filter_params_preserved(self, auth_client, procedure):
        resp = auth_client.get(
            f"/procedures/{procedure.id}/edit?size_filter=4.5&brand_filter=Hiossen"
        )
        assert resp.status_code == 200


class TestAddProcedureImplant:
    def test_add_implant_to_procedure(self, auth_client, procedure, implant):
        resp = auth_client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "2"},
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["quantity"] == 2
        assert data["is_existing"] is False
        item = ProcedureImplant.query.filter_by(
            procedure_id=procedure.id, implant_id=implant.id
        ).first()
        assert item is not None
        assert item.quantity == 2

    def test_add_implant_merges_existing(self, auth_client, procedure, implant):
        # Add once
        auth_client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "2"},
            headers=AJAX_HEADERS,
        )
        # Add again — should merge
        resp = auth_client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "3"},
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["is_existing"] is True
        assert data["quantity"] == 5

    def test_add_implant_exceeds_stock_rejected(self, auth_client, procedure, implant):
        resp = auth_client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": str(implant.stock + 1)},
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is False
        assert ProcedureImplant.query.filter_by(procedure_id=procedure.id).count() == 0

    def test_add_implant_merge_exceeds_stock_rejected(self, auth_client, procedure, implant):
        # Reserve 8 of 10 in stock
        auth_client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "8"},
            headers=AJAX_HEADERS,
        )
        # Attempting to add 3 more (8+3=11 > 10) should be rejected
        resp = auth_client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "3"},
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is False
        # Existing item quantity must still be 8
        item = ProcedureImplant.query.filter_by(procedure_id=procedure.id, implant_id=implant.id).first()
        assert item.quantity == 8

    def test_add_implant_exactly_at_stock_allowed(self, auth_client, procedure, implant):
        resp = auth_client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": str(implant.stock)},
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True

    def test_add_implant_requires_login(self, client, procedure, implant):
        resp = client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "1"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_add_implant_nonexistent_procedure_404(self, auth_client, implant):
        resp = auth_client.post(
            "/procedures/99999/add-implant",
            data={"implant_id": implant.id, "quantity": "1"},
            headers=AJAX_HEADERS,
        )
        assert resp.status_code == 404


class TestSetProcedureItemQuantity:
    def test_set_quantity_updates(self, auth_client, procedure_with_implant):
        item = procedure_with_implant.items[0]
        resp = auth_client.post(
            f"/procedures/{procedure_with_implant.id}/item/{item.id}/set-quantity",
            data={"quantity": "5"},
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["removed"] is False
        assert data["quantity"] == 5
        db.session.refresh(item)
        assert item.quantity == 5

    def test_set_quantity_zero_removes_item(self, auth_client, procedure_with_implant):
        item = procedure_with_implant.items[0]
        item_id = item.id
        resp = auth_client.post(
            f"/procedures/{procedure_with_implant.id}/item/{item_id}/set-quantity",
            data={"quantity": "0"},
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["removed"] is True
        assert db.session.get(ProcedureImplant, item_id) is None

    def test_set_quantity_negative_removes_item(self, auth_client, procedure_with_implant):
        item = procedure_with_implant.items[0]
        item_id = item.id
        resp = auth_client.post(
            f"/procedures/{procedure_with_implant.id}/item/{item_id}/set-quantity",
            data={"quantity": "-1"},
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["removed"] is True

    def test_set_quantity_exceeds_stock_rejected(self, auth_client, procedure_with_implant, implant):
        item = procedure_with_implant.items[0]
        resp = auth_client.post(
            f"/procedures/{procedure_with_implant.id}/item/{item.id}/set-quantity",
            data={"quantity": str(implant.stock + 1)},
        )
        data = json.loads(resp.data)
        assert data["ok"] is False

    def test_set_quantity_nonexistent_item_404(self, auth_client, procedure):
        resp = auth_client.post(
            f"/procedures/{procedure.id}/item/99999/set-quantity",
            data={"quantity": "1"},
        )
        assert resp.status_code == 404


class TestRemoveProcedureImplant:
    def test_remove_implant_from_procedure(self, auth_client, procedure_with_implant):
        item = procedure_with_implant.items[0]
        item_id = item.id
        resp = auth_client.post(
            f"/procedures/{procedure_with_implant.id}/remove-implant/{item_id}",
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert db.session.get(ProcedureImplant, item_id) is None

    def test_remove_implant_requires_login(self, client, procedure_with_implant):
        item = procedure_with_implant.items[0]
        resp = client.post(
            f"/procedures/{procedure_with_implant.id}/remove-implant/{item.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestConfirmProcedure:
    def test_confirm_deducts_stock(self, auth_client, procedure_with_implant, implant):
        original_stock = implant.stock
        item_qty = procedure_with_implant.items[0].quantity

        resp = auth_client.post(
            f"/procedures/{procedure_with_implant.id}/confirm",
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True

        db.session.refresh(implant)
        assert implant.stock == original_stock - item_qty

    def test_confirm_sets_status_completed(self, auth_client, procedure_with_implant):
        auth_client.post(
            f"/procedures/{procedure_with_implant.id}/confirm",
            headers=AJAX_HEADERS,
        )
        db.session.refresh(procedure_with_implant)
        assert procedure_with_implant.status == "completed"

    def test_confirm_empty_procedure_rejected(self, auth_client, procedure):
        resp = auth_client.post(
            f"/procedures/{procedure.id}/confirm",
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is False
        assert "no implants" in data["message"].lower()

    def test_confirm_insufficient_stock_rejected(self, auth_client, procedure, implant):
        original_stock = implant.stock
        # Reserve more than in stock
        item = ProcedureImplant(
            procedure_id=procedure.id,
            implant_id=implant.id,
            quantity=implant.stock + 5,
        )
        db.session.add(item)
        db.session.commit()

        resp = auth_client.post(
            f"/procedures/{procedure.id}/confirm",
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is False
        assert "insufficient" in data["message"].lower()

        # Stock must not have changed
        db.session.refresh(implant)
        assert implant.stock == original_stock

    def test_confirm_requires_login(self, client, procedure_with_implant):
        resp = client.post(
            f"/procedures/{procedure_with_implant.id}/confirm",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_confirm_nonexistent_procedure_404(self, auth_client):
        resp = auth_client.post("/procedures/99999/confirm", headers=AJAX_HEADERS)
        assert resp.status_code == 404


class TestUndoProcedure:
    def test_undo_restores_stock(self, auth_client, procedure_with_implant, implant):
        original_stock = implant.stock
        item_qty = procedure_with_implant.items[0].quantity

        # First confirm
        auth_client.post(
            f"/procedures/{procedure_with_implant.id}/confirm",
            headers=AJAX_HEADERS,
        )
        db.session.refresh(implant)
        assert implant.stock == original_stock - item_qty

        # Then undo
        resp = auth_client.post(
            f"/procedures/{procedure_with_implant.id}/undo",
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True

        db.session.refresh(implant)
        assert implant.stock == original_stock

    def test_undo_sets_status_pending(self, auth_client, procedure_with_implant):
        auth_client.post(
            f"/procedures/{procedure_with_implant.id}/confirm",
            headers=AJAX_HEADERS,
        )
        auth_client.post(
            f"/procedures/{procedure_with_implant.id}/undo",
            headers=AJAX_HEADERS,
        )
        db.session.refresh(procedure_with_implant)
        assert procedure_with_implant.status == "pending"

    def test_undo_pending_procedure_404(self, auth_client, procedure):
        # Can't undo a procedure that was never confirmed
        resp = auth_client.post(
            f"/procedures/{procedure.id}/undo",
            headers=AJAX_HEADERS,
        )
        assert resp.status_code == 404

    def test_undo_requires_login(self, client, procedure_with_implant):
        resp = client.post(
            f"/procedures/{procedure_with_implant.id}/undo",
            follow_redirects=False,
        )
        assert resp.status_code == 302


class TestCancelProcedure:
    def test_cancel_deletes_procedure(self, auth_client, procedure):
        procedure_id = procedure.id
        resp = auth_client.post(
            f"/procedures/{procedure_id}/cancel",
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert db.session.get(Procedure, procedure_id) is None

    def test_cancel_deletes_procedure_items(self, auth_client, procedure_with_implant):
        procedure_id = procedure_with_implant.id
        auth_client.post(
            f"/procedures/{procedure_id}/cancel",
            headers=AJAX_HEADERS,
        )
        assert ProcedureImplant.query.filter_by(procedure_id=procedure_id).count() == 0

    def test_cancel_does_not_restore_stock(self, auth_client, procedure_with_implant, implant):
        # Confirm first to deduct stock
        original_stock = implant.stock
        item_qty = procedure_with_implant.items[0].quantity
        auth_client.post(
            f"/procedures/{procedure_with_implant.id}/confirm",
            headers=AJAX_HEADERS,
        )
        db.session.refresh(implant)
        assert implant.stock == original_stock - item_qty

        # Cancel the completed procedure — stock should NOT be restored
        auth_client.post(
            f"/procedures/{procedure_with_implant.id}/cancel",
            headers=AJAX_HEADERS,
        )
        db.session.refresh(implant)
        assert implant.stock == original_stock - item_qty

    def test_cancel_requires_login(self, client, procedure):
        resp = client.post(
            f"/procedures/{procedure.id}/cancel",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_cancel_nonexistent_procedure_404(self, auth_client):
        resp = auth_client.post("/procedures/99999/cancel", headers=AJAX_HEADERS)
        assert resp.status_code == 404
