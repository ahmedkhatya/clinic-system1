from flask import (Flask, render_template, redirect, url_for,
                   request, flash, abort, jsonify)
from flask_login import (LoginManager, login_user, login_required,
                         logout_user, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, Clinic, User, Patient, Visit, Attachment, Inventory, FinancialEntry
from datetime import datetime, date, timedelta
from functools import wraps
import os, urllib.parse

app = Flask(__name__)
app.config['SECRET_KEY']             = os.environ.get('SECRET_KEY', 'clinic_secret_v3')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clinic.db'
app.config['UPLOAD_FOLDER']          = 'static/uploads'
app.config['MAX_CONTENT_LENGTH']     = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# ─── helpers ────────────────────────────────────────────────────────────────
def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def today_range():
    # نستخدم datetime.now() (توقيت محلي) مش utcnow()
    today_local = datetime.now().date()
    s = datetime.combine(today_local, datetime.min.time())
    return s, s + timedelta(days=1)

def require_roles(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator

@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))


# ─── Auth ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            if user.role == 'superadmin':
                return redirect(url_for('super_dashboard'))
            if user.role == 'doctor':
                return redirect(url_for('doctor_dashboard'))
            return redirect(url_for('nurse_dashboard'))
        flash('اسم المستخدم أو كلمة المرور غلط', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ─────────────────────────────────────────────────────────────────────────────
#  SUPER ADMIN
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/super')
@login_required
@require_roles('superadmin')
def super_dashboard():
    clinics = Clinic.query.all()
    stats = []
    for c in clinics:
        ts, te = today_range()
        today_v  = Visit.query.filter_by(clinic_id=c.id).filter(
            Visit.visit_date >= ts, Visit.visit_date < te).count()
        total_p  = Patient.query.filter_by(clinic_id=c.id).count()
        revenue  = db.session.query(db.func.sum(Visit.price)).filter_by(
            clinic_id=c.id).filter(Visit.status == 'done').scalar() or 0
        low_stock = Inventory.query.filter_by(clinic_id=c.id).filter(
            Inventory.quantity <= Inventory.min_quantity).count()
        stats.append({'clinic': c, 'today': today_v,
                      'patients': total_p, 'revenue': revenue, 'low': low_stock})
    return render_template('super_dashboard.html', stats=stats)


@app.route('/super/clinics', methods=['GET', 'POST'])
@login_required
@require_roles('superadmin')
def manage_clinics():
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        if action == 'add':
            c = Clinic(
                name        = request.form['name'],
                doctor_name = request.form.get('doctor_name', ''),
                specialty   = request.form.get('specialty', ''),
                address     = request.form.get('address', ''),
                phone       = request.form.get('phone', ''),
                work_hours  = request.form.get('work_hours', ''),
                work_days   = request.form.get('work_days', ''),
            )
            db.session.add(c)
            db.session.commit()
            flash(f'✅ تم إضافة عيادة {c.name}', 'success')
        elif action == 'edit':
            c = Clinic.query.get_or_404(request.form['clinic_id'])
            c.name        = request.form['name']
            c.doctor_name = request.form.get('doctor_name', c.doctor_name)
            c.specialty   = request.form.get('specialty',   c.specialty)
            c.address     = request.form.get('address',     c.address)
            c.phone       = request.form.get('phone',       c.phone)
            c.work_hours  = request.form.get('work_hours',  c.work_hours)
            c.work_days   = request.form.get('work_days',   c.work_days)
            db.session.commit()
            flash('✅ تم تعديل بيانات العيادة', 'success')
        elif action == 'delete':
            c = Clinic.query.get_or_404(request.form['clinic_id'])
            db.session.delete(c)
            db.session.commit()
            flash('🗑️ تم حذف العيادة', 'warning')
        return redirect(url_for('manage_clinics'))
    clinics = Clinic.query.all()
    return render_template('manage_clinics.html', clinics=clinics)


@app.route('/super/users', methods=['GET', 'POST'])
@login_required
@require_roles('superadmin')
def manage_users():
    clinics = Clinic.query.all()
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        if action == 'add':
            if User.query.filter_by(username=request.form['username']).first():
                flash('اسم المستخدم موجود مسبقاً', 'danger')
            else:
                cid = request.form.get('clinic_id') or None
                u = User(
                    clinic_id = int(cid) if cid else None,
                    username  = request.form['username'],
                    password  = generate_password_hash(request.form['password']),
                    role      = request.form['role'],
                    name      = request.form['name'],
                )
                db.session.add(u)
                db.session.commit()
                flash(f'✅ تم إضافة {u.name}', 'success')
        elif action == 'delete':
            u = User.query.get_or_404(request.form['user_id'])
            if u.id != current_user.id:
                db.session.delete(u)
                db.session.commit()
                flash('🗑️ تم حذف المستخدم', 'warning')
        return redirect(url_for('manage_users'))
    users = User.query.all()
    return render_template('manage_users.html', users=users, clinics=clinics)


@app.route('/super/clinic/<int:clinic_id>')
@login_required
@require_roles('superadmin')
def clinic_detail(clinic_id):
    """صفحة تفاصيل عيادة معينة للسوبر أدمن"""
    clinic = Clinic.query.get_or_404(clinic_id)
    ts, te = today_range()

    visits_today = (db.session.query(Visit, Patient)
                    .join(Patient)
                    .filter(Visit.clinic_id == clinic_id)
                    .filter(Visit.visit_date >= ts, Visit.visit_date < te)
                    .order_by(Visit.visit_date.desc()).all())

    rev = db.session.query(db.func.sum(Visit.price)).filter_by(
        clinic_id=clinic_id).filter(Visit.status == 'done').scalar() or 0
    exp = db.session.query(db.func.sum(FinancialEntry.amount)).filter_by(
        clinic_id=clinic_id, entry_type='expense').scalar() or 0
    low_stock = Inventory.query.filter_by(clinic_id=clinic_id).filter(
        Inventory.quantity <= Inventory.min_quantity).all()

    return render_template('clinic_detail.html',
                           clinic=clinic, visits=visits_today,
                           rev=rev, exp=exp, net=rev-exp, low_stock=low_stock)


# ─────────────────────────────────────────────────────────────────────────────
#  NURSE  (استقبال / تمريض)
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/nurse', methods=['GET', 'POST'])
@login_required
@require_roles('nurse')
def nurse_dashboard():
    cid = current_user.clinic_id
    clinic = Clinic.query.get(cid)

    if request.method == 'POST':
        action = request.form.get('action')

        # ── مريض جديد ──
        if action == 'new_patient':
            p = Patient(
                clinic_id = cid,
                name      = request.form['name'],
                phone     = request.form['phone'],
                age       = request.form.get('age') or None,
                gender    = request.form.get('gender', ''),
                notes     = request.form.get('notes', '')
            )
            db.session.add(p)
            db.session.commit()
            v = Visit(clinic_id=cid, patient_id=p.id, status='waiting',
                      visit_type=request.form.get('visit_type', 'كشف جديد'))
            db.session.add(v)
            db.session.commit()
            flash(f'✅ تم تسجيل {p.name}', 'success')

        # ── مريض قديم ──
        elif action == 'returning_patient':
            p = Patient.query.filter_by(clinic_id=cid, id=request.form.get('patient_id')).first()
            if p:
                v = Visit(clinic_id=cid, patient_id=p.id, status='waiting',
                          visit_type=request.form.get('visit_type', 'إعادة'))
                db.session.add(v)
                db.session.commit()
                flash(f'✅ تم إضافة {p.name} لقائمة الانتظار', 'success')
            else:
                flash('المريض مش موجود', 'danger')

        # ── تقفيل اليوم ──
        elif action == 'close_day':
            ts, te = today_range()
            visits = Visit.query.filter_by(clinic_id=cid).filter(
                Visit.visit_date >= ts, Visit.visit_date < te,
                Visit.status != 'archived').all()
            now = datetime.now()
            for v in visits:
                v.status      = 'archived'
                v.archived_at = now
            db.session.commit()
            flash(f'📁 تم تقفيل اليوم وأرشفة {len(visits)} زيارة', 'success')

        return redirect(url_for('nurse_dashboard'))

    ts, te = today_range()
    visits_today = (db.session.query(Visit, Patient)
                    .join(Patient)
                    .filter(Visit.clinic_id == cid)
                    .filter(Visit.visit_date >= ts, Visit.visit_date < te)
                    .filter(Visit.status != 'archived')
                    .order_by(Visit.visit_date)
                    .all())

    waiting_count = sum(1 for v, p in visits_today if v.status == 'waiting')
    done_count    = sum(1 for v, p in visits_today if v.status == 'done')

    return render_template('nurse_dashboard.html',
                           clinic=clinic,
                           visits=visits_today,
                           waiting_count=waiting_count,
                           done_count=done_count)


# ─── API: بحث مريض قديم (للممرضة) ──────────────────────────────────────────
@app.route('/search_patients')
@login_required
def search_patients():
    cid = current_user.clinic_id
    q   = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    pts = Patient.query.filter_by(clinic_id=cid).filter(
        (Patient.name.ilike(f'%{q}%')) | (Patient.phone.ilike(f'%{q}%'))
    ).limit(10).all()
    return jsonify([{'id': p.id, 'name': p.name,
                     'phone': p.phone, 'age': p.age} for p in pts])


# ─── API: حالة قائمة الانتظار (للـ refresh) ─────────────────────────────────
@app.route('/api/queue')
@login_required
def api_queue():
    cid = current_user.clinic_id
    ts, te = today_range()
    rows = (db.session.query(Visit, Patient)
            .join(Patient)
            .filter(Visit.clinic_id == cid)
            .filter(Visit.visit_date >= ts, Visit.visit_date < te)
            .filter(Visit.status != 'archived')
            .order_by(Visit.visit_date).all())
    return jsonify([{
        'id':         v.id,
        'patient':    p.name,
        'phone':      p.phone,
        'age':        p.age,
        'visit_type': v.visit_type,
        'status':     v.status,
        'time':       v.visit_date.strftime('%I:%M %p'),
        'notes':      p.notes or '',
    } for v, p in rows])


# ─────────────────────────────────────────────────────────────────────────────
#  DOCTOR
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/doctor')
@login_required
@require_roles('doctor')
def doctor_dashboard():
    cid = current_user.clinic_id
    clinic = Clinic.query.get(cid)
    ts, te = today_range()

    # كل مرضى اليوم (انتظار + تم) — مش أرشيف
    visits_today = (db.session.query(Visit, Patient)
                    .join(Patient)
                    .filter(Visit.clinic_id == cid)
                    .filter(Visit.visit_date >= ts, Visit.visit_date < te)
                    .filter(Visit.status != 'archived')
                    .order_by(Visit.visit_date)
                    .all())

    return render_template('doctor_dashboard.html',
                           clinic=clinic, visits=visits_today)


# ─── API: قائمة اليوم للدكتور (للـ refresh) ─────────────────────────────────
@app.route('/api/doctor_queue')
@login_required
@require_roles('doctor')
def api_doctor_queue():
    cid = current_user.clinic_id
    ts, te = today_range()
    rows = (db.session.query(Visit, Patient)
            .join(Patient)
            .filter(Visit.clinic_id == cid)
            .filter(Visit.visit_date >= ts, Visit.visit_date < te)
            .filter(Visit.status != 'archived')
            .order_by(Visit.visit_date).all())
    return jsonify([{
        'id':         v.id,
        'patient':    p.name,
        'phone':      p.phone,
        'age':        p.age,
        'notes':      p.notes or '',
        'visit_type': v.visit_type,
        'status':     v.status,
        'time':       v.visit_date.strftime('%I:%M %p'),
        'examine_url': url_for('examine_patient', visit_id=v.id),
        'patient_id': p.id,
    } for v, p in rows])


# ─── بحث الدكتور عن مريض قديم ───────────────────────────────────────────────
@app.route('/doctor/search')
@login_required
@require_roles('doctor')
def doctor_search():
    cid         = current_user.clinic_id
    q           = request.args.get('q', '').strip()
    date_filter = request.args.get('date', '').strip()
    patients    = []
    if q and len(q) >= 2:
        patients = Patient.query.filter_by(clinic_id=cid).filter(
            (Patient.name.ilike(f'%{q}%')) | (Patient.phone.ilike(f'%{q}%'))
        ).all()
    elif date_filter:
        try:
            d  = datetime.strptime(date_filter, '%Y-%m-%d')
            te = d + timedelta(days=1)
            pids = [v.patient_id for v in Visit.query.filter_by(clinic_id=cid)
                    .filter(Visit.visit_date >= d, Visit.visit_date < te).all()]
            patients = Patient.query.filter(Patient.id.in_(pids)).all()
        except ValueError:
            pass
    return render_template('doctor_search.html', patients=patients, q=q,
                           date_filter=date_filter, clinic=Clinic.query.get(cid))


@app.route('/doctor/patient/<int:patient_id>')
@login_required
@require_roles('doctor')
def patient_history(patient_id):
    cid        = current_user.clinic_id
    p          = Patient.query.filter_by(id=patient_id, clinic_id=cid).first_or_404()
    date_filter = request.args.get('date')          # فلتر التاريخ
    q_visits   = Visit.query.filter_by(patient_id=p.id)
    if date_filter:
        try:
            from datetime import timedelta
            d   = datetime.strptime(date_filter, '%Y-%m-%d')
            q_visits = q_visits.filter(Visit.visit_date >= d,
                                       Visit.visit_date < d + timedelta(days=1))
        except ValueError:
            pass
    visits = q_visits.order_by(Visit.visit_date.desc()).all()
    # جيب المرفقات لكل زيارة
    attachments_map = {}
    for v in visits:
        attachments_map[v.id] = Attachment.query.filter_by(visit_id=v.id).all()
    return render_template('patient_history.html',
                           patient=p, visits=visits,
                           attachments_map=attachments_map,
                           date_filter=date_filter,
                           clinic=Clinic.query.get(cid))


# ─── كشف المريض ─────────────────────────────────────────────────────────────
@app.route('/examine/<int:visit_id>', methods=['GET', 'POST'])
@login_required
@require_roles('doctor')
def examine_patient(visit_id):
    visit   = Visit.query.get_or_404(visit_id)
    patient = Patient.query.get(visit.patient_id)
    clinic  = Clinic.query.get(visit.clinic_id)

    # تأكد الدكتور تاع نفس العيادة
    if visit.clinic_id != current_user.clinic_id:
        abort(403)

    if request.method == 'POST':
        visit.diagnosis         = request.form.get('diagnosis', '')
        visit.treatment         = request.form.get('treatment', '')
        visit.consultation_date = request.form.get('consultation_date', '')
        visit.price             = float(request.form.get('price', 0) or 0)
        visit.status            = 'done'
        visit.doctor_id         = current_user.id

        # رفع ملفات
        for file in request.files.getlist('attachments'):
            if file and file.filename and allowed_file(file.filename):
                fname = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                ext   = fname.rsplit('.', 1)[1].lower()
                ftype = 'image' if ext in {'png','jpg','jpeg','gif'} else 'pdf'
                db.session.add(Attachment(visit_id=visit.id, file_path=fname, file_type=ftype))

        db.session.commit()

        # تسجيل الإيراد تلقائياً
        if visit.price > 0:
            db.session.add(FinancialEntry(
                clinic_id   = visit.clinic_id,
                category    = 'كشف',
                amount      = visit.price,
                description = f'{visit.visit_type} - {patient.name}',
                entry_type  = 'income'
            ))
            db.session.commit()

        flash('✅ تم حفظ الكشف بنجاح', 'success')
        return redirect(url_for('doctor_dashboard'))

    history     = (Visit.query.filter_by(patient_id=patient.id)
                   .filter(Visit.status.in_(['done','archived']))
                   .order_by(Visit.visit_date.desc()).all())
    attachments = Attachment.query.filter_by(visit_id=visit.id).all()

    return render_template('doctor_examine.html',
                           visit=visit, patient=patient, clinic=clinic,
                           history=history, attachments=attachments)


# ─── روشتة وواتساب ──────────────────────────────────────────────────────────
@app.route('/prescription/<int:visit_id>')
@login_required
def print_prescription(visit_id):
    v = Visit.query.get_or_404(visit_id)
    p = Patient.query.get(v.patient_id)
    c = Clinic.query.get(v.clinic_id)
    return render_template('prescription.html', visit=v, patient=p, clinic=c)

@app.route('/whatsapp/<int:visit_id>')
@login_required
def generate_whatsapp(visit_id):
    v    = Visit.query.get_or_404(visit_id)
    p    = Patient.query.get(v.patient_id)
    link = url_for('print_prescription', visit_id=v.id, _external=True)
    msg  = f"أهلاً {p.name}،\nيمكنك عرض روشتتك من هنا:\n{link}"
    return redirect(f"https://wa.me/2{p.phone}?text={urllib.parse.quote(msg)}")


# ─────────────────────────────────────────────────────────────────────────────
#  ADMIN للعيادة (ممكن الدكتور أو السوبر أدمن يدخل)
# ─────────────────────────────────────────────────────────────────────────────
def get_clinic_or_403(clinic_id=None):
    """يرجع العيادة المناسبة حسب الدور"""
    if current_user.role == 'superadmin':
        return Clinic.query.get_or_404(clinic_id)
    return Clinic.query.get_or_404(current_user.clinic_id)


@app.route('/clinic/<int:clinic_id>/inventory', methods=['GET', 'POST'])
@login_required
@require_roles('superadmin', 'doctor')
def manage_inventory(clinic_id):
    clinic = get_clinic_or_403(clinic_id)
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        if action == 'add':
            db.session.add(Inventory(
                clinic_id    = clinic.id,
                item_name    = request.form['name'],
                quantity     = int(request.form['qty']),
                min_quantity = int(request.form['min']),
                unit         = request.form.get('unit', 'قطعة')
            ))
            db.session.commit()
            flash('✅ تم الإضافة', 'success')
        elif action == 'update_qty':
            item = Inventory.query.filter_by(id=request.form['item_id'], clinic_id=clinic.id).first()
            if item:
                item.quantity = int(request.form.get('new_qty', item.quantity))
                db.session.commit()
                flash('✅ تم التحديث', 'success')
        elif action == 'delete':
            item = Inventory.query.filter_by(id=request.form['item_id'], clinic_id=clinic.id).first()
            if item:
                db.session.delete(item)
                db.session.commit()
                flash('🗑️ تم الحذف', 'warning')
        return redirect(url_for('manage_inventory', clinic_id=clinic.id))

    items = Inventory.query.filter_by(clinic_id=clinic.id).order_by(Inventory.quantity).all()
    return render_template('admin_inventory.html', clinic=clinic, items=items)


@app.route('/clinic/<int:clinic_id>/finances', methods=['GET', 'POST'])
@login_required
@require_roles('superadmin', 'doctor')
def manage_finances(clinic_id):
    clinic = get_clinic_or_403(clinic_id)
    if request.method == 'POST':
        db.session.add(FinancialEntry(
            clinic_id   = clinic.id,
            category    = request.form['category'],
            amount      = float(request.form['amount']),
            description = request.form.get('desc', ''),
            entry_type  = request.form.get('entry_type', 'expense')
        ))
        db.session.commit()
        flash('✅ تم التسجيل', 'success')
        return redirect(url_for('manage_finances', clinic_id=clinic.id))

    entries       = FinancialEntry.query.filter_by(clinic_id=clinic.id).order_by(FinancialEntry.date.desc()).all()
    total_income  = sum(e.amount for e in entries if e.entry_type == 'income')
    total_expense = sum(e.amount for e in entries if e.entry_type == 'expense')
    return render_template('admin_finances.html',
                           clinic=clinic, entries=entries,
                           total_income=total_income, total_expense=total_expense)


# ─────────────────────────────────────────────────────────────────────────────
#  تهيئة قاعدة البيانات + بيانات أولية
# ─────────────────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()

    # سوبر أدمن
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(
            username='admin',
            password=generate_password_hash('123'),
            role='superadmin',
            name='Super Admin'
        ))
        db.session.commit()

    # عيادة تجريبية
    if not Clinic.query.first():
        c = Clinic(
            name        = 'عيادة د. محمد يوسف',
            doctor_name = 'د. محمد يوسف',
            specialty   = 'أخصائي القلب والأوعية الدموية',
            address     = 'شبرا الخيمة - ش 15 مايو',
            phone       = '01093079334',
            work_hours  = '6م - 11م',
            work_days   = 'يومياً عدا الجمعة',
        )
        db.session.add(c)
        db.session.commit()

        db.session.add(User(username='doctor1',
                            password=generate_password_hash('123'),
                            role='doctor', name='د. محمد يوسف', clinic_id=c.id))
        db.session.add(User(username='nurse1',
                            password=generate_password_hash('123'),
                            role='nurse', name='الممرضة سارة', clinic_id=c.id))
        db.session.commit()


if __name__ == '__main__':
    app.run(debug=True)
