"""Examination Management Portal (MAD-1 educational reference application).
Run: python app.py. SQLite schema is created automatically.
"""
import os
import sqlite3
import secrets
from datetime import datetime, date
from functools import wraps
from pathlib import Path
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash

ROOT = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get('EMP_DB_PATH', str(ROOT / 'emp.sqlite3')))
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'local-development-change-this-key')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

from models import SCHEMA

def db():
    if 'db' not in g:
        DATABASE.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(str(DATABASE), timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()

def init_db():
    with app.app_context():
        db().executescript(SCHEMA)
        if not db().execute("SELECT id FROM users WHERE role='admin'").fetchone():
            email = os.environ.get('ADMIN_EMAIL', 'admin@emp.local')
            password = os.environ.get('ADMIN_PASSWORD', 'ChangeMe123!')
            db().execute('INSERT INTO users(name,email,password_hash,role,approved) VALUES(?,?,?,?,1)',
                         ('Administrator', email, generate_password_hash(password), 'admin'))
        # Ready-to-use local demo accounts. New examiner registrations still require Admin approval.
        demos = [
            ('Demo Examiner', 'examiner@emp.local', 'Examiner123!', 'examiner'),
            ('Demo Student', 'student@emp.local', 'Student123!', 'student'),
        ]
        for name, email, password, role in demos:
            if not db().execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
                db().execute(
                    'INSERT INTO users(name,email,password_hash,role,approved) VALUES(?,?,?,?,1)',
                    (name, email, generate_password_hash(password), role)
                )
        db().commit()

def current_user():
    uid = session.get('uid')
    return db().execute('SELECT * FROM users WHERE id=? AND active=1', (uid,)).fetchone() if uid else None

def role_required(*roles):
    def decorate(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for('login'))
            if user['role'] not in roles:
                abort(403)
            if user['role']=='examiner' and not user['approved']:
                flash('Your examiner registration needs administrator approval.', 'warning')
                return redirect(url_for('pending'))
            return fn(*args, **kwargs)
        return wrapper
    return decorate

@app.before_request
def csrf_protect():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(24)
    if request.method == 'POST' and not secrets.compare_digest(session['csrf_token'], request.form.get('_csrf', '')):
        abort(400, 'Invalid CSRF token; reload the page and try again.')

@app.context_processor
def common():
    return {'me': current_user(), 'today': date.today().isoformat(), 'csrf_token':session.get('csrf_token','')}

def row(sql, params=()):
    return db().execute(sql, params).fetchone()
def rows(sql, params=()):
    return db().execute(sql, params).fetchall()
def required(name):
    val = request.form.get(name, '').strip()
    if not val:
        raise ValueError(name.replace('_',' ').capitalize()+' is required')
    return val
def number(name, minimum=1):
    result = int(required(name))
    if result < minimum: raise ValueError(name+' must be at least '+str(minimum))
    return result
def ensure_order(a,b,description):
    if a > b: raise ValueError(description+' start must not be after end')
def valid_dates():
    a,b,c,d = [required(k) for k in ('creation_start','creation_end','booking_start','booking_end')]
    for x in (a,b,c,d): date.fromisoformat(x)
    ensure_order(a,b,'Slot creation window')
    ensure_order(c,d,'Booking window')
    return a,b,c,d
def allowed_window(exam,kind):
    now = date.today().isoformat()
    return exam[kind+'_start'] <= now <= exam[kind+'_end']
def occupied(slot_id):
    return row("SELECT COUNT(*) n FROM bookings WHERE slot_id=? AND status IN ('booked','completed')", (slot_id,))['n']
def slot_record(slot_id):
    return row('''SELECT s.*, e.title, e.booking_start,e.booking_end,e.creation_start,e.creation_end,
                   e.status exam_status,e.max_marks,e.published FROM slots s JOIN exams e ON e.id=s.exam_id WHERE s.id=?''',(slot_id,))
def owns_exam(exam_id, uid):
    return bool(row('SELECT 1 FROM assignments WHERE exam_id=? AND examiner_id=?',(exam_id,uid)))
def get_booking(booking_id):
    return row('''SELECT b.*, s.exam_id,s.examiner_id,s.slot_date,s.start_time,s.end_time,
        e.title,e.max_marks,e.published, u.name student_name
        FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN exams e ON e.id=s.exam_id
        JOIN users u ON u.id=b.student_id WHERE b.id=?''',(booking_id,))
def audit_error(ex):
    db().rollback()
    flash(str(ex), 'danger')

@app.get('/')
def home():
    return redirect(url_for('dashboard') if current_user() else url_for('login'))

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        try:
            name,email,password,role = (required(x) for x in ('name','email','password','role'))
            if role not in ('student','examiner'): raise ValueError('Invalid role')
            if len(password)<8: raise ValueError('Password needs at least 8 characters')
            db().execute('INSERT INTO users(name,email,password_hash,role,department,approved) VALUES(?,?,?,?,?,?)',
                         (name,email.lower(),generate_password_hash(password),role,request.form.get('department','').strip(),int(role=='student')))
            db().commit()
            flash('Registration successful. Log in to continue.', 'success')
            return redirect(url_for('login'))
        except (ValueError,sqlite3.IntegrityError) as e: audit_error(e)
    return render_template('auth.html',mode='register')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        user = row('SELECT * FROM users WHERE email=?',(request.form.get('email','').strip().lower(),))
        if user and user['active'] and check_password_hash(user['password_hash'],request.form.get('password','')):
            session.clear(); session['uid']=user['id']; session['csrf_token']=secrets.token_hex(24)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials or inactive account.', 'danger')
    return render_template('auth.html',mode='login')

@app.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.get('/pending')
def pending():
    if not current_user(): return redirect(url_for('login'))
    return render_template('page.html',title='Approval pending',message='Your examiner account is waiting for administrator approval.')

@app.get('/dashboard')
@role_required('admin','examiner','student')
def dashboard():
    u=current_user(); stats=[]
    if u['role']=='admin':
        stats=[(t,row('SELECT COUNT(*) n FROM '+tbl)['n']) for t,tbl in
               [('Courses','courses'),('Examinations','exams'),('Examiners',"users WHERE role='examiner'"),
                ('Students',"users WHERE role='student'"),('Slots','slots'),('Bookings','bookings')]]
    elif u['role']=='examiner':
        stats=[('Assigned examinations',row('SELECT COUNT(*) n FROM assignments WHERE examiner_id=?',(u['id'],))['n']),
               ('My slots',row('SELECT COUNT(*) n FROM slots WHERE examiner_id=?',(u['id'],))['n']),
               ('Students booked',row("SELECT COUNT(*) n FROM bookings b JOIN slots s ON b.slot_id=s.id WHERE s.examiner_id=? AND b.status='booked'",(u['id'],))['n']),
               ('Pending evaluations',row("SELECT COUNT(*) n FROM bookings b JOIN slots s ON b.slot_id=s.id LEFT JOIN evaluations v ON v.booking_id=b.id WHERE s.examiner_id=? AND b.status='booked' AND v.booking_id IS NULL",(u['id'],))['n'])]
    else:
        stats=[('Available examinations',row("SELECT COUNT(*) n FROM exams WHERE status='booking_open'")['n']),
               ('Available slots',row("SELECT COUNT(*) n FROM slots s JOIN exams e ON s.exam_id=e.id WHERE e.status='booking_open' AND s.cancelled=0 AND e.booking_start<=? AND e.booking_end>=? AND s.slot_date>=?",(date.today().isoformat(),)*3)['n']),
               ('My bookings',row("SELECT COUNT(*) n FROM bookings WHERE student_id=? AND status='booked'",(u['id'],))['n']),
               ('Results published',row("SELECT COUNT(*) n FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN exams e ON e.id=s.exam_id WHERE b.student_id=? AND e.published=1 AND b.status='completed'",(u['id'],))['n'])]
    return render_template('dashboard.html',stats=stats)

@app.route('/profile',methods=['GET','POST'])
@role_required('student','examiner','admin')
def profile():
    if request.method=='POST':
        try:
            db().execute('UPDATE users SET name=?,department=? WHERE id=?',(required('name'),request.form.get('department','').strip(),current_user()['id']))
            db().commit(); flash('Profile updated','success'); return redirect(url_for('profile'))
        except ValueError as e: audit_error(e)
    return render_template('profile.html')

@app.route('/admin/users')
@role_required('admin')
def admin_users():
    q=request.args.get('q','').strip()
    users=rows('SELECT * FROM users WHERE name LIKE ? OR email LIKE ? OR CAST(id AS TEXT) LIKE ? ORDER BY role,name',('%'+q+'%',)*3)
    return render_template('users.html',users=users,q=q)

@app.post('/admin/users/<int:uid>/toggle')
@role_required('admin')
def toggle_user(uid):
    user=row('SELECT * FROM users WHERE id=?',(uid,))
    if not user or user['role']=='admin': abort(400)
    if request.form.get('action')=='approve' and user['role']=='examiner':
        db().execute('UPDATE users SET approved=1 WHERE id=?',(uid,))
    elif request.form.get('action')=='active':
        db().execute('UPDATE users SET active=1-active WHERE id=?',(uid,))
    else: abort(400)
    db().commit(); flash('Account updated','success')
    return redirect(url_for('admin_users'))

@app.route('/courses',methods=['GET','POST'])
@role_required('admin')
def courses():
    if request.method=='POST':
        try:
            cid=request.form.get('id',type=int)
            values=(required('code'),required('name'),request.form.get('description','').strip(),int(request.form.get('active')=='1'))
            if cid:
                db().execute('UPDATE courses SET code=?,name=?,description=?,active=? WHERE id=?',(*values,cid))
            else:
                db().execute('INSERT INTO courses(code,name,description,active) VALUES(?,?,?,?)',values)
            db().commit(); flash('Course saved','success'); return redirect(url_for('courses'))
        except (ValueError,sqlite3.IntegrityError) as e: audit_error(e)
    return render_template('courses.html',items=rows('SELECT * FROM courses ORDER BY id DESC'), edit=row('SELECT * FROM courses WHERE id=?',(request.args.get('edit',type=int),)) if request.args.get('edit') else None)

@app.post('/courses/<int:cid>/delete')
@role_required('admin')
def delete_course(cid):
    try:
        db().execute('DELETE FROM courses WHERE id=?',(cid,)); db().commit(); flash('Course deleted','success')
    except sqlite3.IntegrityError:
        audit_error(ValueError('Cannot delete a course while examinations reference it. Deactivate it instead.'))
    return redirect(url_for('courses'))

@app.route('/exams',methods=['GET','POST'])
@role_required('admin','examiner','student')
def exams():
    u=current_user()
    if request.method=='POST':
        if u['role']!='admin': abort(403)
        try:
            cid=number('course_id'); title=required('title'); ex_type=required('exam_type')
            if ex_type not in ('Viva','Practical','Project Demo','Assessment'): raise ValueError('Invalid exam type')
            duration=number('duration'); max_marks=number('max_marks'); dates=valid_dates()
            status=required('status')
            if status not in ('draft','slot_creation','booking_open','closed','completed'): raise ValueError('Invalid status')
            values=(cid,title,ex_type,duration,max_marks,*dates,status,int(request.form.get('published')=='1'))
            eid=request.form.get('id',type=int)
            if eid:
                db().execute('''UPDATE exams SET course_id=?,title=?,exam_type=?,duration=?,max_marks=?,creation_start=?,creation_end=?,booking_start=?,booking_end=?,status=?,published=? WHERE id=?''',(*values,eid))
            else:
                db().execute('''INSERT INTO exams(course_id,title,exam_type,duration,max_marks,creation_start,creation_end,booking_start,booking_end,status,published) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',values)
            db().commit(); flash('Examination saved','success'); return redirect(url_for('exams'))
        except (ValueError,sqlite3.IntegrityError) as e: audit_error(e)
    q=request.args.get('q','').strip(); params=['%'+q+'%']*3
    sql='''SELECT e.*,c.code course_code,c.name course_name FROM exams e JOIN courses c ON e.course_id=c.id
       WHERE (e.title LIKE ? OR c.name LIKE ? OR CAST(e.id AS TEXT) LIKE ?)'''
    if u['role']=='examiner':
        sql+=' AND EXISTS(SELECT 1 FROM assignments a WHERE a.exam_id=e.id AND a.examiner_id=?)'; params.append(u['id'])
    if u['role']=='student': sql+=" AND e.status!='draft'"
    sql+=' ORDER BY e.id DESC'
    edit=row('SELECT * FROM exams WHERE id=?',(request.args.get('edit',type=int),)) if u['role']=='admin' and request.args.get('edit') else None
    return render_template('exams.html',items=rows(sql,params),courses=rows('SELECT * FROM courses WHERE active=1'),edit=edit,q=q)

@app.post('/exams/<int:eid>/delete')
@role_required('admin')
def delete_exam(eid):
    if row('SELECT 1 FROM slots WHERE exam_id=?',(eid,)):
        flash('Exam has existing slots. Close the exam rather than deleting historical records.','danger')
    else:
        db().execute('DELETE FROM exams WHERE id=?',(eid,)); db().commit(); flash('Exam deleted','success')
    return redirect(url_for('exams'))

@app.route('/exams/<int:eid>/manage',methods=['GET','POST'])
@role_required('admin')
def manage_exam(eid):
    exam=row('SELECT * FROM exams WHERE id=?',(eid,))
    if not exam: abort(404)
    if request.method=='POST':
        try:
            action=required('action')
            if action=='assign':
                uid=number('examiner_id')
                if not row("SELECT 1 FROM users WHERE id=? AND role='examiner' AND approved=1 AND active=1",(uid,)):
                    raise ValueError('Examiner must be approved and active')
                db().execute('INSERT OR IGNORE INTO assignments(exam_id,examiner_id) VALUES(?,?)',(eid,uid))
            elif action=='unassign':
                uid=number('examiner_id')
                if row('SELECT 1 FROM slots WHERE exam_id=? AND examiner_id=?',(eid,uid)):
                    raise ValueError('Cannot unassign examiner with slots; reassign their slots first')
                db().execute('DELETE FROM assignments WHERE exam_id=? AND examiner_id=?',(eid,uid))
            elif action=='rubric':
                marks=number('max_marks')
                allocated=row('SELECT COALESCE(SUM(max_marks),0) n FROM rubrics WHERE exam_id=?',(eid,))['n']
                if allocated+marks>exam['max_marks']: raise ValueError('Rubric total cannot exceed examination maximum marks')
                db().execute('INSERT INTO rubrics(exam_id,criterion,max_marks,description) VALUES(?,?,?,?)',(eid,required('criterion'),marks,request.form.get('description','')))
            elif action=='delete_rubric':
                rid=number('rubric_id')
                if row('SELECT 1 FROM scores WHERE rubric_id=?',(rid,)): raise ValueError('This rubric has recorded marks and cannot be deleted')
                db().execute('DELETE FROM rubrics WHERE id=? AND exam_id=?',(rid,eid))
            else: abort(400)
            db().commit(); flash('Examination settings updated','success'); return redirect(url_for('manage_exam',eid=eid))
        except (ValueError,sqlite3.IntegrityError) as e: audit_error(e)
    return render_template('manage_exam.html',exam=exam,assigned=rows('SELECT u.* FROM users u JOIN assignments a ON a.examiner_id=u.id WHERE a.exam_id=?',(eid,)),
       examiners=rows("SELECT * FROM users WHERE role='examiner' AND active=1 AND approved=1"),
       rubrics=rows('SELECT * FROM rubrics WHERE exam_id=?',(eid,)))

@app.route('/slots',methods=['GET','POST'])
@role_required('admin','examiner','student')
def slots():
    u=current_user()
    if request.method=='POST':
        if u['role']!='examiner': abort(403)
        try:
            eid=number('exam_id'); ex=row('SELECT * FROM exams WHERE id=?',(eid,))
            if not ex or not owns_exam(eid,u['id']): raise ValueError('Examination is not assigned to you')
            if ex['status']!='slot_creation' or not allowed_window(ex,'creation'): raise ValueError('Slot creation window is closed')
            sid=request.form.get('id',type=int)
            if sid and (row('SELECT 1 FROM bookings WHERE slot_id=?',(sid,)) or date.today().isoformat() >= ex['booking_start']):
                raise ValueError('Slot cannot be edited after booking has begun or a booking exists')
            slot_date,start,end=(required(k) for k in ('slot_date','start_time','end_time'))
            date.fromisoformat(slot_date)
            ensure_order(start,end,'Slot time')
            if start==end: raise ValueError('Slot must have positive duration')
            if slot_date<date.today().isoformat(): raise ValueError('Slot cannot be in the past')
            capacity=number('capacity')
            vals=(eid,u['id'],slot_date,start,end,capacity)
            if sid:
                existing=row('SELECT * FROM slots WHERE id=?',(sid,))
                if not existing or existing['examiner_id']!=u['id'] or existing['exam_id']!=eid: abort(403)
                db().execute('UPDATE slots SET exam_id=?,examiner_id=?,slot_date=?,start_time=?,end_time=?,capacity=? WHERE id=?',(*vals,sid))
            else:
                db().execute('INSERT INTO slots(exam_id,examiner_id,slot_date,start_time,end_time,capacity) VALUES(?,?,?,?,?,?)',vals)
            db().commit(); flash('Slot saved','success'); return redirect(url_for('slots'))
        except (ValueError,sqlite3.IntegrityError) as e: audit_error(e)
    q=request.args.get('q','').strip()
    sql='''SELECT s.*,e.title,e.status exam_status,e.booking_start,e.booking_end,
         u.name examiner_name, (SELECT COUNT(*) FROM bookings b WHERE b.slot_id=s.id AND b.status IN ('booked','completed')) occupied
         FROM slots s JOIN exams e ON s.exam_id=e.id JOIN users u ON s.examiner_id=u.id WHERE e.title LIKE ?'''
    params=['%'+q+'%']
    if u['role']=='examiner': sql+=' AND s.examiner_id=?';params.append(u['id'])
    if u['role']=='student': sql+=" AND e.status='booking_open' AND s.cancelled=0 AND s.slot_date>=?";params.append(date.today().isoformat())
    sql+=' ORDER BY s.slot_date,s.start_time'
    assigned=rows('SELECT e.* FROM exams e JOIN assignments a ON a.exam_id=e.id WHERE a.examiner_id=?',(u['id'],)) if u['role']=='examiner' else []
    edit=row('SELECT * FROM slots WHERE id=? AND examiner_id=?',(request.args.get('edit',type=int),u['id'])) if u['role']=='examiner' and request.args.get('edit') else None
    return render_template('slots.html',items=rows(sql,params),assigned=assigned,edit=edit,q=q, admin_examiners=rows("SELECT * FROM users WHERE role='examiner' AND approved=1 AND active=1") if u['role']=='admin' else [])

@app.post('/slots/<int:sid>/cancel')
@role_required('examiner')
def cancel_slot(sid):
    s=slot_record(sid)
    if not s or s['examiner_id']!=current_user()['id']: abort(403)
    if s['exam_status']!='slot_creation' or not allowed_window(s,'creation') or row('SELECT 1 FROM bookings WHERE slot_id=?',(sid,)):
        flash('Slot can only be removed during slot creation and before any booking exists','danger')
    else:
        db().execute('DELETE FROM slots WHERE id=?',(sid,));db().commit();flash('Slot deleted','success')
    return redirect(url_for('slots'))

@app.post('/slots/<int:sid>/book')
@role_required('student')
def book(sid):
    s=slot_record(sid); u=current_user()
    if not s: abort(404)
    try:
        db().execute('BEGIN IMMEDIATE')
        if s['cancelled'] or s['exam_status']!='booking_open' or not allowed_window(s,'booking') or s['slot_date']<date.today().isoformat():
            raise ValueError('Slot is not open for booking')
        if occupied(sid)>=s['capacity']: raise ValueError('Slot is full')
        if row('''SELECT 1 FROM bookings b JOIN slots t ON b.slot_id=t.id WHERE b.student_id=? AND t.exam_id=? AND b.status IN ('booked','completed')''',(u['id'],s['exam_id'])):
            raise ValueError('You already have an active booking for this examination')
        db().execute('INSERT INTO bookings(student_id,slot_id,booked_at) VALUES(?,?,?)',(u['id'],sid,datetime.now().isoformat(timespec='seconds')))
        db().commit();flash('Booking confirmed','success')
    except (ValueError,sqlite3.IntegrityError) as e: audit_error(e)
    return redirect(url_for('my_bookings'))

@app.get('/bookings')
@role_required('admin','examiner','student')
def my_bookings():
    u=current_user();q=request.args.get('q','').strip()
    sql='''SELECT b.*,s.slot_date,s.start_time,s.end_time,s.examiner_id,e.title,e.published,
       st.name student_name,x.name examiner_name,
       (SELECT SUM(marks) FROM scores WHERE booking_id=b.id) total_marks,
       (SELECT remarks FROM evaluations WHERE booking_id=b.id) remarks
       FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN exams e ON e.id=s.exam_id
       JOIN users st ON st.id=b.student_id JOIN users x ON x.id=s.examiner_id
       WHERE (e.title LIKE ? OR st.name LIKE ? OR CAST(b.id AS TEXT) LIKE ?)'''
    params=['%'+q+'%']*3
    if u['role']=='student': sql+=' AND b.student_id=?';params.append(u['id'])
    if u['role']=='examiner': sql+=' AND s.examiner_id=?';params.append(u['id'])
    sql+=' ORDER BY b.id DESC'
    return render_template('bookings.html',items=rows(sql,params),q=q)

@app.post('/bookings/<int:bid>/cancel')
@role_required('student')
def cancel_booking(bid):
    b=get_booking(bid);u=current_user()
    if not b or b['student_id']!=u['id']: abort(403)
    s=slot_record(b['slot_id'])
    if b['status']!='booked' or date.today().isoformat()>s['booking_end']:
        flash('Booking cancellation deadline has passed or booking is not active','danger')
    else:
        db().execute("UPDATE bookings SET status='cancelled' WHERE id=?",(bid,));db().commit();flash('Booking cancelled; history retained','success')
    return redirect(url_for('my_bookings'))

@app.route('/bookings/<int:bid>/evaluate',methods=['GET','POST'])
@role_required('examiner')
def evaluate(bid):
    b=get_booking(bid)
    if not b or b['examiner_id']!=current_user()['id'] or b['status'] not in ('booked','completed'): abort(403)
    rubrics=rows('SELECT * FROM rubrics WHERE exam_id=? ORDER BY id',(b['exam_id'],))
    if request.method=='POST':
        try:
            if not rubrics: raise ValueError('Ask admin to add examination rubrics first')
            marks=[]
            for r in rubrics:
                m=number('marks_'+str(r['id']),0)
                if m>r['max_marks']: raise ValueError('Marks exceed rubric maximum for '+r['criterion'])
                marks.append((r['id'],m))
            if sum(m for _,m in marks)>b['max_marks']: raise ValueError('Total exceeds examination maximum')
            for rid,m in marks:
                db().execute('INSERT INTO scores(booking_id,rubric_id,marks) VALUES(?,?,?) ON CONFLICT(booking_id,rubric_id) DO UPDATE SET marks=excluded.marks',(bid,rid,m))
            db().execute('INSERT INTO evaluations(booking_id,remarks,evaluated_at) VALUES(?,?,?) ON CONFLICT(booking_id) DO UPDATE SET remarks=excluded.remarks,evaluated_at=excluded.evaluated_at',
                         (bid,request.form.get('remarks','').strip(),datetime.now().isoformat(timespec='seconds')))
            db().execute("UPDATE bookings SET status='completed' WHERE id=?",(bid,))
            db().commit();flash('Evaluation saved. Student can view result once admin publishes it.','success')
            return redirect(url_for('my_bookings'))
        except (ValueError,sqlite3.IntegrityError) as e: audit_error(e)
    scored={r['rubric_id']:r['marks'] for r in rows('SELECT * FROM scores WHERE booking_id=?',(bid,))}
    ev=row('SELECT * FROM evaluations WHERE booking_id=?',(bid,))
    return render_template('evaluate.html',booking=b,rubrics=rubrics,scored=scored,ev=ev)

@app.route('/admin/booking/<int:bid>/reschedule',methods=['GET','POST'])
@role_required('admin')
def reschedule(bid):
    b=get_booking(bid)
    if not b: abort(404)
    choices=rows('''SELECT s.*,u.name examiner_name,
        (SELECT COUNT(*) FROM bookings z WHERE z.slot_id=s.id AND z.status IN ('booked','completed')) taken
        FROM slots s JOIN users u ON u.id=s.examiner_id WHERE s.exam_id=? AND s.cancelled=0 ORDER BY s.slot_date,s.start_time''',(b['exam_id'],))
    if request.method=='POST':
        try:
            sid=number('slot_id'); slot=slot_record(sid)
            if not slot or slot['exam_id']!=b['exam_id'] or slot['cancelled']: raise ValueError('Invalid replacement slot')
            if b['status']=='completed': raise ValueError('Completed evaluations cannot be rescheduled')
            db().execute('BEGIN IMMEDIATE')
            if sid!=b['slot_id'] and occupied(sid)>=slot['capacity']: raise ValueError('Replacement slot is full')
            db().execute('UPDATE bookings SET slot_id=? WHERE id=?',(sid,bid));db().commit()
            flash('Booking rescheduled','success');return redirect(url_for('my_bookings'))
        except (ValueError,sqlite3.IntegrityError) as e: audit_error(e)
    return render_template('reschedule.html',booking=b,choices=choices)

@app.post('/admin/slots/<int:sid>/examiner')
@role_required('admin')
def change_examiner(sid):
    s=slot_record(sid)
    if not s: abort(404)
    try:
        uid=number('examiner_id')
        if not row("SELECT 1 FROM users WHERE id=? AND role='examiner' AND approved=1 AND active=1",(uid,)):
            raise ValueError('Examiner must be approved')
        db().execute('INSERT OR IGNORE INTO assignments(exam_id,examiner_id) VALUES(?,?)',(s['exam_id'],uid))
        db().execute('UPDATE slots SET examiner_id=? WHERE id=?',(uid,sid));db().commit()
        flash('Examiner reassigned','success')
    except (ValueError,sqlite3.IntegrityError) as e: audit_error(e)
    return redirect(url_for('slots'))

@app.errorhandler(403)
def forbidden(e): return render_template('page.html',title='Access denied',message='You do not have permission to perform this action.'),403
@app.errorhandler(404)
def missing(e): return render_template('page.html',title='Not found',message='The requested resource does not exist.'),404
@app.errorhandler(400)
def invalid(e): return render_template('page.html',title='Invalid request',message=str(e)),400

if __name__=='__main__':
    init_db()
    app.run(debug=os.environ.get('FLASK_DEBUG','0')=='1',host='127.0.0.1',port=int(os.environ.get('PORT','5000')))
