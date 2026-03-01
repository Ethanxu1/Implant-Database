import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from app import app as flask_app
from database import db as _db, User, Implant, Procedure, ProcedureImplant


@pytest.fixture()
def app():
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret-key",
    )
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(app):
    u = User(username="testuser")
    u.set_password("password123")
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture()
def second_user(app):
    u = User(username="otheruser")
    u.set_password("password456")
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture()
def auth_client(client, user):
    client.post("/login", data={"username": "testuser", "password": "password123"})
    return client


@pytest.fixture()
def implant(app, user):
    i = Implant(
        size="4.5x11.5",
        brand="Hiossen",
        stock=10,
        min_stock=2,
        user_id=user.id,
    )
    _db.session.add(i)
    _db.session.commit()
    return i


@pytest.fixture()
def zero_stock_implant(app, user):
    i = Implant(
        size="3.5x10.0",
        brand="Megagen",
        stock=0,
        min_stock=2,
        user_id=user.id,
    )
    _db.session.add(i)
    _db.session.commit()
    return i


@pytest.fixture()
def procedure(app, user):
    p = Procedure(patient_name="Alice Smith", user_id=user.id)
    _db.session.add(p)
    _db.session.commit()
    return p


@pytest.fixture()
def procedure_with_implant(app, user, implant):
    p = Procedure(patient_name="Bob Jones", user_id=user.id)
    _db.session.add(p)
    _db.session.flush()
    item = ProcedureImplant(procedure_id=p.id, implant_id=implant.id, quantity=2)
    _db.session.add(item)
    _db.session.commit()
    return p
