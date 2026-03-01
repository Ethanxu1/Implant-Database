from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    # Relationships
    implants = db.relationship('Implant', backref='owner', lazy=True, cascade='all, delete-orphan')
    procedures = db.relationship('Procedure', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Implant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    size = db.Column(db.String(50), nullable=False)
    brand = db.Column(db.String(100), nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    min_stock = db.Column(db.Integer, nullable=True)
    # Foreign key to associate with user
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def is_low_stock(self):
        if self.min_stock is None:
            return False
        return self.stock <= self.min_stock

class Procedure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(150), nullable=False)
    date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    items = db.relationship('ProcedureImplant', backref='procedure', lazy=True, cascade='all, delete-orphan')

class ProcedureImplant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    procedure_id = db.Column(db.Integer, db.ForeignKey('procedure.id'), nullable=False)
    implant_id = db.Column(db.Integer, db.ForeignKey('implant.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    implant = db.relationship('Implant', lazy=True)