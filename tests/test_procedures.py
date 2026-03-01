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

    def test_add_implant_exceeds_stock_warns(self, auth_client, procedure, implant):
        # Exceeding stock is now allowed — returns ok=True with warning=True
        resp = auth_client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": str(implant.stock + 1)},
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["warning"] is True
        item = ProcedureImplant.query.filter_by(procedure_id=procedure.id).first()
        assert item is not None
        assert item.quantity == implant.stock + 1

    def test_add_implant_merge_exceeds_stock_allowed(self, auth_client, procedure, implant):
        # Merging beyond stock is now allowed
        auth_client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "8"},
            headers=AJAX_HEADERS,
        )
        resp = auth_client.post(
            f"/procedures/{procedure.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "3"},
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        item = ProcedureImplant.query.filter_by(procedure_id=procedure.id, implant_id=implant.id).first()
        assert item.quantity == 11

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

    def test_set_quantity_exceeds_stock_warns(self, auth_client, procedure_with_implant, implant):
        # Exceeding stock is now allowed — returns ok=True with warning=True
        item = procedure_with_implant.items[0]
        resp = auth_client.post(
            f"/procedures/{procedure_with_implant.id}/item/{item.id}/set-quantity",
            data={"quantity": str(implant.stock + 1)},
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["warning"] is True
        db.session.refresh(item)
        assert item.quantity == implant.stock + 1

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


class TestCrossProcedureStockWarnings:
    def test_add_implant_warns_when_combined_exceeds_stock(self, auth_client, user, implant):
        """Two procedures share an implant; combined qty > stock → second gets warning=True."""
        # implant.stock = 10; reserve 8 in proc_a first
        proc_a = Procedure(patient_name="Patient A", user_id=user.id)
        proc_b = Procedure(patient_name="Patient B", user_id=user.id)
        db.session.add_all([proc_a, proc_b])
        db.session.commit()

        auth_client.post(
            f"/procedures/{proc_a.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "8"},
            headers=AJAX_HEADERS,
        )

        # Add 4 to proc_b — combined 8+4=12 > 10, so warning=True, available=2
        resp = auth_client.post(
            f"/procedures/{proc_b.id}/add-implant",
            data={"implant_id": implant.id, "quantity": "4"},
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["warning"] is True
        assert data["available"] == 2  # stock(10) - other_pending(8) = 2

    def test_confirm_blocked_by_cross_procedure_overcommit(self, auth_client, user, implant):
        """Confirm is blocked when item.quantity + other_pending > stock."""
        # implant.stock = 10; proc_a holds 7, proc_b holds 5 → combined 12 > 10
        proc_a = Procedure(patient_name="Patient A", user_id=user.id)
        proc_b = Procedure(patient_name="Patient B", user_id=user.id)
        db.session.add_all([proc_a, proc_b])
        db.session.flush()
        db.session.add(ProcedureImplant(procedure_id=proc_a.id, implant_id=implant.id, quantity=7))
        db.session.add(ProcedureImplant(procedure_id=proc_b.id, implant_id=implant.id, quantity=5))
        db.session.commit()

        original_stock = implant.stock

        # Confirming proc_b: 5 + other_pending(7) = 12 > stock(10) → blocked
        resp = auth_client.post(
            f"/procedures/{proc_b.id}/confirm",
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is False
        assert "insufficient" in data["message"].lower()
        db.session.refresh(implant)
        assert implant.stock == original_stock

    def test_confirm_allowed_when_combined_exactly_meets_stock(self, auth_client, user, implant):
        """Confirm succeeds when item.quantity + other_pending == stock (not over)."""
        # implant.stock = 10; proc_a holds 6, proc_b holds 4 → combined 10 == 10 → no overcommit
        proc_a = Procedure(patient_name="Patient A", user_id=user.id)
        proc_b = Procedure(patient_name="Patient B", user_id=user.id)
        db.session.add_all([proc_a, proc_b])
        db.session.flush()
        db.session.add(ProcedureImplant(procedure_id=proc_a.id, implant_id=implant.id, quantity=6))
        db.session.add(ProcedureImplant(procedure_id=proc_b.id, implant_id=implant.id, quantity=4))
        db.session.commit()

        # Confirming proc_b: 4 + other_pending(6) = 10 == stock(10) → allowed
        resp = auth_client.post(
            f"/procedures/{proc_b.id}/confirm",
            headers=AJAX_HEADERS,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        db.session.refresh(implant)
        assert implant.stock == 6  # 10 - 4 deducted
