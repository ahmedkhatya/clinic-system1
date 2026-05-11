from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


class Clinic(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200), nullable=False)        # اسم العيادة
    doctor_name  = db.Column(db.String(200))                        # اسم الدكتور للروشتة
    specialty    = db.Column(db.String(200))                        # التخصص
    address      = db.Column(db.String(300))
    phone        = db.Column(db.String(30))
    work_hours   = db.Column(db.String(100))                        # مثلاً "6م - 11م"
    work_days    = db.Column(db.String(100))                        # مثلاً "يومياً عدا الجمعة"
    logo_path    = db.Column(db.String(300))                        # مسار اللوجو لو موجود
    created_at   = db.Column(db.DateTime, default=datetime.now)

    users        = db.relationship('User',          backref='clinic', lazy=True)
    patients     = db.relationship('Patient',       backref='clinic', lazy=True)
    inventory    = db.relationship('Inventory',     backref='clinic', lazy=True)
    finances     = db.relationship('FinancialEntry',backref='clinic', lazy=True)


class User(db.Model, UserMixin):
    id         = db.Column(db.Integer, primary_key=True)
    clinic_id  = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=True)  # None = super admin
    username   = db.Column(db.String(150), unique=True, nullable=False)
    password   = db.Column(db.String(150), nullable=False)
    role       = db.Column(db.String(50),  nullable=False)  # 'superadmin' | 'doctor' | 'nurse'
    name       = db.Column(db.String(150))


class Patient(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    clinic_id  = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    name       = db.Column(db.String(200), nullable=False)
    phone      = db.Column(db.String(20),  nullable=False)
    age        = db.Column(db.Integer)
    gender     = db.Column(db.String(10))
    notes      = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    visits     = db.relationship('Visit', backref='patient', lazy=True)


class Visit(db.Model):
    id                = db.Column(db.Integer, primary_key=True)
    clinic_id         = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    patient_id        = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_id         = db.Column(db.Integer, db.ForeignKey('user.id'))
    visit_date        = db.Column(db.DateTime, default=datetime.now)
    status            = db.Column(db.String(50), default='waiting')   # 'waiting' | 'done' | 'archived'
    diagnosis         = db.Column(db.Text)
    treatment         = db.Column(db.Text)
    visit_type        = db.Column(db.String(50))
    price             = db.Column(db.Float, default=0.0)
    consultation_date = db.Column(db.String(100))
    archived_at       = db.Column(db.DateTime)                         # وقت التقفيل
    attachments       = db.relationship('Attachment', backref='visit', lazy=True)


class Attachment(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    visit_id    = db.Column(db.Integer, db.ForeignKey('visit.id'), nullable=False)
    file_path   = db.Column(db.String(300), nullable=False)
    file_type   = db.Column(db.String(50))
    uploaded_at = db.Column(db.DateTime, default=datetime.now)


class Inventory(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    clinic_id    = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    item_name    = db.Column(db.String(200), nullable=False)
    quantity     = db.Column(db.Integer, default=0)
    min_quantity = db.Column(db.Integer, default=5)
    unit         = db.Column(db.String(50))


class FinancialEntry(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    clinic_id   = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    category    = db.Column(db.String(100))
    amount      = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(300))
    entry_type  = db.Column(db.String(20), default='expense')   # 'income' | 'expense'
    date        = db.Column(db.DateTime, default=datetime.now)
