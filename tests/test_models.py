"""Tests for model methods and business logic."""
from database import db, User, Implant, Procedure, ProcedureImplant


class TestIsLowStock:
    def test_stock_above_min_is_not_low(self, app):
        i = Implant(size="4.5x11.5", brand="Hiossen", stock=5, min_stock=2, user_id=1)
        assert i.is_low_stock() is False

    def test_stock_equal_to_min_is_low(self, app):
        # Threshold is inclusive: stock == min_stock → low
        i = Implant(size="4.5x11.5", brand="Hiossen", stock=2, min_stock=2, user_id=1)
        assert i.is_low_stock() is True

    def test_stock_below_min_is_low(self, app):
        i = Implant(size="4.5x11.5", brand="Hiossen", stock=1, min_stock=2, user_id=1)
        assert i.is_low_stock() is True

    def test_zero_stock_is_low(self, app):
        i = Implant(size="4.5x11.5", brand="Hiossen", stock=0, min_stock=2, user_id=1)
        assert i.is_low_stock() is True

    def test_zero_min_stock_not_low_when_stock_positive(self, app):
        i = Implant(size="4.5x11.5", brand="Hiossen", stock=1, min_stock=0, user_id=1)
        assert i.is_low_stock() is False

    def test_zero_stock_and_zero_min_is_low(self, app):
        i = Implant(size="4.5x11.5", brand="Hiossen", stock=0, min_stock=0, user_id=1)
        assert i.is_low_stock() is True


class TestUserPassword:
    def test_set_and_check_password(self, app, user):
        assert user.check_password("password123") is True

    def test_wrong_password_fails(self, app, user):
        assert user.check_password("wrongpassword") is False

    def test_empty_password_fails(self, app, user):
        assert user.check_password("") is False

    def test_password_hash_is_not_plaintext(self, app, user):
        assert user.password_hash != "password123"

    def test_change_password(self, app, user):
        user.set_password("newpassword")
        db.session.commit()
        assert user.check_password("newpassword") is True
        assert user.check_password("password123") is False


class TestCascadeDelete:
    def test_deleting_user_deletes_implants(self, app, user, implant):
        user_id = user.id
        db.session.delete(user)
        db.session.commit()
        assert Implant.query.filter_by(user_id=user_id).count() == 0

    def test_deleting_user_deletes_procedures(self, app, user, procedure):
        user_id = user.id
        db.session.delete(user)
        db.session.commit()
        assert Procedure.query.filter_by(user_id=user_id).count() == 0

    def test_deleting_user_deletes_procedure_items(self, app, user, procedure_with_implant):
        procedure_id = procedure_with_implant.id
        db.session.delete(user)
        db.session.commit()
        assert ProcedureImplant.query.filter_by(procedure_id=procedure_id).count() == 0

    def test_deleting_procedure_deletes_items(self, app, procedure_with_implant):
        procedure_id = procedure_with_implant.id
        db.session.delete(procedure_with_implant)
        db.session.commit()
        assert ProcedureImplant.query.filter_by(procedure_id=procedure_id).count() == 0
