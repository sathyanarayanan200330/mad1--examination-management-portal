from flask import Blueprint, render_template, request, redirect, url_for, flash
from auth import roles_required
from database import get_db, set_setting
admin_bp=Blueprint('admin',__name__)

@admin_bp.route('/')
@roles_required('admin')
def dashboard():
 d=get_db(); stats={k:d.execute(q).fetchone()[0] for k,q in {
 'courses':'SELECT COUNT(*) FROM courses','examinations':'SELECT COUNT(*) FROM examinations',
 'examiners':"SELECT COUNT(*) FROM users WHERE role='examiner'",'students':"SELECT COUNT(*) FROM users WHERE role='student'",
 'slots':'SELECT COUNT(*) FROM slots','bookings':"SELECT COUNT(*) FROM bookings WHERE status='booked'"}.items()}
 return render_template('admin_dashboard.html',stats=stats,examiners=d.execute("SELECT * FROM users WHERE role='examiner' ORDER BY created_at DESC").fetchall(),
 slot_open=d.execute("SELECT value FROM settings WHERE key='slot_creation_open'").fetchone()['value']=='1', booking_open=d.execute("SELECT value FROM settings WHERE key='booking_open'").fetchone()['value']=='1')

@admin_bp.route('/courses',methods=['GET','POST'])
@roles_required('admin')
def courses():
 d=get_db()
 if request.method=='POST':
  try:
   d.execute('INSERT INTO courses(code,name,description,status) VALUES(?,?,?,?)',(request.form['code'].strip().upper(),request.form['name'].strip(),request.form.get('description',''),request.form.get('status','active'))); d.commit(); flash('Course created.','success')
  except Exception: d.rollback(); flash('Could not create course. Check that the course code is unique.','danger')
  return redirect(url_for('admin.courses'))
 return render_template('courses.html',courses=d.execute('SELECT * FROM courses ORDER BY id DESC').fetchall())

@admin_bp.route('/courses/<int:cid>/delete',methods=['POST'])
@roles_required('admin')
def delete_course(cid):
 d=get_db()
 try: d.execute('DELETE FROM courses WHERE id=?',(cid,)); d.commit(); flash('Course removed.','success')
 except Exception: d.rollback(); flash('Course is in use by an examination and cannot be removed.','danger')
 return redirect(url_for('admin.courses'))

@admin_bp.route('/examinations',methods=['GET','POST'])
@roles_required('admin')
def examinations():
 d=get_db(); courses=d.execute("SELECT * FROM courses WHERE status='active'").fetchall()
 if request.method=='POST':
  try:
   d.execute('''INSERT INTO examinations(course_id,name,exam_type,duration,max_marks,slot_start,slot_end,booking_start,booking_end,status,description)
   VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(request.form['course_id'],request.form['name'].strip(),request.form['exam_type'],int(request.form['duration']),float(request.form['max_marks']),request.form['slot_start'],request.form['slot_end'],request.form['booking_start'],request.form['booking_end'],request.form.get('status','draft'),request.form.get('description',''))); d.commit(); flash('Examination created.','success')
  except Exception as e: d.rollback(); flash('Could not create examination. Check all fields and dates.','danger')
  return redirect(url_for('admin.examinations'))
 exams=d.execute('SELECT e.*,c.code course_code,c.name course_name FROM examinations e JOIN courses c ON c.id=e.course_id ORDER BY e.id DESC').fetchall()
 return render_template('examinations.html',courses=courses,exams=exams)

@admin_bp.route('/examinations/<int:eid>/delete',methods=['POST'])
@roles_required('admin')
def delete_exam(eid):
 d=get_db()
 try: d.execute('DELETE FROM examinations WHERE id=?',(eid,)); d.commit(); flash('Examination removed.','success')
 except Exception: d.rollback(); flash('Cannot remove an examination with existing slots or bookings.','danger')
 return redirect(url_for('admin.examinations'))

@admin_bp.route('/examinations/<int:eid>/rubrics',methods=['GET','POST'])
@roles_required('admin')
def rubrics(eid):
 d=get_db(); exam=d.execute('SELECT * FROM examinations WHERE id=?',(eid,)).fetchone()
 if not exam: flash('Examination not found.','danger'); return redirect(url_for('admin.examinations'))
 if request.method=='POST':
  try: d.execute('INSERT INTO rubrics(examination_id,criterion,max_marks,weightage,description) VALUES(?,?,?,?,?)',(eid,request.form['criterion'].strip(),float(request.form['max_marks']),float(request.form.get('weightage') or 1),request.form.get('description',''))); d.commit(); flash('Rubric criterion added.','success')
  except Exception: d.rollback(); flash('Could not add rubric.','danger')
  return redirect(url_for('admin.rubrics',eid=eid))
 return render_template('rubrics.html',exam=exam,rubrics=d.execute('SELECT * FROM rubrics WHERE examination_id=?',(eid,)).fetchall())

@admin_bp.route('/rubrics/<int:rid>/delete',methods=['POST'])
@roles_required('admin')
def delete_rubric(rid):
 d=get_db(); row=d.execute('SELECT examination_id FROM rubrics WHERE id=?',(rid,)).fetchone()
 if row:
  try: d.execute('DELETE FROM rubrics WHERE id=?',(rid,)); d.commit(); flash('Rubric criterion removed.','success')
  except Exception: d.rollback(); flash('Rubric is already used in an evaluation.','danger')
  return redirect(url_for('admin.rubrics',eid=row['examination_id']))
 return redirect(url_for('admin.examinations'))

@admin_bp.route('/examiner/<int:uid>/<action>',methods=['POST'])
@roles_required('admin')
def examiner_status(uid,action):
 if action not in ('approve','deactivate','activate'): return redirect(url_for('admin.dashboard'))
 status={'approve':'active','activate':'active','deactivate':'inactive'}[action]
 d=get_db(); d.execute("UPDATE users SET status=? WHERE id=? AND role='examiner'",(status,uid)); d.commit(); flash('Examiner account updated.','success'); return redirect(url_for('admin.dashboard'))

@admin_bp.route('/controls',methods=['POST'])
@roles_required('admin')
def controls():
 set_setting('slot_creation_open','1' if request.form.get('slot_creation_open')=='1' else '0')
 set_setting('booking_open','1' if request.form.get('booking_open')=='1' else '0')
 flash('Examination access windows updated.','success'); return redirect(url_for('admin.dashboard'))

@admin_bp.route('/slots')
@roles_required('admin')
def slots():
 rows=get_db().execute('''SELECT s.*,e.name exam_name,u.name examiner_name,
 (SELECT COUNT(*) FROM bookings b WHERE b.slot_id=s.id AND b.status='booked') booked
 FROM slots s JOIN examinations e ON e.id=s.examination_id JOIN users u ON u.id=s.examiner_id ORDER BY s.exam_date,s.start_time''').fetchall()
 return render_template('admin_slots.html',slots=rows)

@admin_bp.route('/bookings',methods=['GET','POST'])
@roles_required('admin')
def bookings():
 d=get_db()
 if request.method=='POST':
  bid=request.form.get('booking_id'); slot_id=request.form.get('slot_id'); examiner_id=request.form.get('examiner_id')
  b=d.execute('SELECT * FROM bookings WHERE id=? AND status="booked"',(bid,)).fetchone()
  s=d.execute('SELECT * FROM slots WHERE id=?',(slot_id,)).fetchone() if slot_id else None
  if b and s:
   old_exam=d.execute('SELECT examination_id FROM slots WHERE id=?',(b['slot_id'],)).fetchone()['examination_id']
   used=d.execute("SELECT COUNT(*) FROM bookings WHERE slot_id=? AND status='booked' AND id<>?",(slot_id,bid)).fetchone()[0]
   duplicate=d.execute("SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id=b.slot_id WHERE b.student_id=? AND s.examination_id=? AND b.status='booked' AND b.id<>?",(b['student_id'],s['examination_id'],bid)).fetchone()[0]
   if s['examination_id']!=old_exam: flash('A booking can only be rescheduled to another slot of the same examination.','danger')
   elif duplicate: flash('Student already has another active booking for this examination.','danger')
   elif used < s['capacity']:
    d.execute('UPDATE bookings SET slot_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(slot_id,bid)); d.execute("UPDATE slots SET status=CASE WHEN (SELECT COUNT(*) FROM bookings WHERE slot_id=? AND status='booked')>=capacity THEN 'full' ELSE 'available' END WHERE id=?",(slot_id,slot_id)); d.execute("UPDATE slots SET status='available' WHERE id=? AND status='full'",(b['slot_id'],)); d.commit(); flash('Booking rescheduled.','success')
   else: flash('The selected slot has no available capacity.','danger')
  elif b and examiner_id:
   d.execute('UPDATE slots SET examiner_id=? WHERE id=?',(examiner_id,b['slot_id'])); d.commit(); flash('Examiner assignment changed for the booking slot.','success')
  else: flash('Select a valid booking and a new slot or examiner.','danger')
  return redirect(url_for('admin.bookings'))
 q=request.args.get('q','').strip()
 rows=d.execute('''SELECT b.*,s.exam_date,s.start_time,s.end_time,e.name exam_name,u.name student_name,u.email student_email,x.name examiner_name,s.id slot_id
 FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations e ON e.id=s.examination_id JOIN users u ON u.id=b.student_id JOIN users x ON x.id=s.examiner_id
 WHERE (?='' OR u.name LIKE ? OR u.email LIKE ? OR e.name LIKE ? OR CAST(b.id AS TEXT)=?) ORDER BY b.booked_at DESC''',(q,f'%{q}%',f'%{q}%',f'%{q}%',q)).fetchall()
 allslots=d.execute('SELECT s.id,e.name exam_name,s.exam_date,s.start_time,s.end_time,s.capacity FROM slots s JOIN examinations e ON e.id=s.examination_id ORDER BY s.exam_date').fetchall()
 examiners=d.execute("SELECT id,name FROM users WHERE role='examiner' AND status='active'").fetchall()
 return render_template('admin_bookings.html',bookings=rows,slots=allslots,examiners=examiners,q=q)

@admin_bp.route('/search')
@roles_required('admin')
def search():
 q=request.args.get('q','').strip(); d=get_db(); like=f'%{q}%'
 users=d.execute("SELECT id,name,email,role,status FROM users WHERE role IN ('student','examiner') AND (name LIKE ? OR email LIKE ? OR CAST(id AS TEXT)=?)",(like,like,q)).fetchall()
 exams=d.execute('SELECT id,name,status FROM examinations WHERE name LIKE ? OR CAST(id AS TEXT)=?',(like,q)).fetchall()
 return render_template('admin_search.html',q=q,users=users,exams=exams)

@admin_bp.route('/courses/<int:cid>/edit',methods=['GET','POST'])
@roles_required('admin')
def edit_course(cid):
 d=get_db(); c=d.execute('SELECT * FROM courses WHERE id=?',(cid,)).fetchone()
 if not c: flash('Course not found.','danger'); return redirect(url_for('admin.courses'))
 if request.method=='POST':
  try: d.execute('UPDATE courses SET code=?,name=?,description=?,status=? WHERE id=?',(request.form['code'].strip().upper(),request.form['name'].strip(),request.form.get('description',''),request.form.get('status','active'),cid)); d.commit(); flash('Course updated.','success'); return redirect(url_for('admin.courses'))
  except Exception: d.rollback(); flash('Could not update course. Course code may already exist.','danger')
 return render_template('edit_course.html',course=c)

@admin_bp.route('/examinations/<int:eid>/edit',methods=['GET','POST'])
@roles_required('admin')
def edit_exam(eid):
 d=get_db(); e=d.execute('SELECT * FROM examinations WHERE id=?',(eid,)).fetchone()
 if not e: flash('Examination not found.','danger'); return redirect(url_for('admin.examinations'))
 if request.method=='POST':
  try:
   d.execute('''UPDATE examinations SET course_id=?,name=?,exam_type=?,duration=?,max_marks=?,slot_start=?,slot_end=?,booking_start=?,booking_end=?,status=?,description=? WHERE id=?''',
   (request.form['course_id'],request.form['name'].strip(),request.form['exam_type'],int(request.form['duration']),float(request.form['max_marks']),request.form['slot_start'],request.form['slot_end'],request.form['booking_start'],request.form['booking_end'],request.form['status'],request.form.get('description',''),eid)); d.commit(); flash('Examination updated.','success'); return redirect(url_for('admin.examinations'))
  except Exception: d.rollback(); flash('Could not update examination. Check the supplied values.','danger')
 return render_template('edit_exam.html',exam=e,courses=d.execute("SELECT * FROM courses WHERE status='active'").fetchall())
