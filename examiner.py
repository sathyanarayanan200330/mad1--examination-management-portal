from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from auth import roles_required
from database import get_db, setting
examiner_bp=Blueprint('examiner',__name__)

@examiner_bp.route('/')
@roles_required('examiner')
def dashboard():
 d=get_db(); uid=session['user_id']
 exams=d.execute('SELECT DISTINCT e.*,c.code course_code FROM examinations e JOIN courses c ON c.id=e.course_id JOIN slots s ON s.examination_id=e.id WHERE s.examiner_id=? ORDER BY e.id DESC',(uid,)).fetchall()
 slots=d.execute('''SELECT s.*,e.name exam_name,(SELECT COUNT(*) FROM bookings b WHERE b.slot_id=s.id AND b.status='booked') booked
 FROM slots s JOIN examinations e ON e.id=s.examination_id WHERE s.examiner_id=? ORDER BY s.exam_date,s.start_time''',(uid,)).fetchall()
 pending=d.execute('''SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id=b.slot_id LEFT JOIN evaluations v ON v.booking_id=b.id
 WHERE s.examiner_id=? AND b.status='booked' AND v.id IS NULL''',(uid,)).fetchone()[0]
 return render_template('examiner_dashboard.html',exams=exams,slots=slots,pending=pending,slot_open=setting('slot_creation_open')=='1')

@examiner_bp.route('/slots',methods=['GET','POST'])
@roles_required('examiner')
def slots():
 d=get_db(); uid=session['user_id']
 if request.method=='POST':
  eid=request.form.get('examination_id'); exam=d.execute('SELECT * FROM examinations WHERE id=?',(eid,)).fetchone()
  day=request.form.get('exam_date','')
  if not setting('slot_creation_open')=='1': flash('The administrator has closed slot creation.','danger')
  elif not exam or not (exam['slot_start'] <= day <= exam['slot_end']): flash('Slot date must fall within the examination slot-creation period.','danger')
  elif request.form.get('start_time','') >= request.form.get('end_time',''): flash('End time must be later than start time.','danger')
  else:
   try: d.execute('INSERT INTO slots(examination_id,examiner_id,exam_date,start_time,end_time,capacity) VALUES(?,?,?,?,?,?)',(eid,uid,day,request.form['start_time'],request.form['end_time'],int(request.form['capacity']))); d.commit(); flash('Examination slot created.','success')
   except Exception: d.rollback(); flash('Could not create slot. Check capacity and ensure the time is not already used.','danger')
  return redirect(url_for('examiner.slots'))
 exams=d.execute('SELECT * FROM examinations WHERE status IN ("slot creation","booking open","draft") ORDER BY name').fetchall()
 rows=d.execute('''SELECT s.*,e.name exam_name,(SELECT COUNT(*) FROM bookings b WHERE b.slot_id=s.id AND b.status='booked') booked
 FROM slots s JOIN examinations e ON e.id=s.examination_id WHERE s.examiner_id=? ORDER BY s.exam_date''',(uid,)).fetchall()
 return render_template('examiner_slots.html',exams=exams,slots=rows,slot_open=setting('slot_creation_open')=='1')

@examiner_bp.route('/slots/<int:sid>/delete',methods=['POST'])
@roles_required('examiner')
def delete_slot(sid):
 d=get_db(); s=d.execute('SELECT * FROM slots WHERE id=? AND examiner_id=?',(sid,session['user_id'])).fetchone()
 if s and setting('booking_open')!='1':
  count=d.execute("SELECT COUNT(*) FROM bookings WHERE slot_id=? AND status='booked'",(sid,)).fetchone()[0]
  if count==0: d.execute('DELETE FROM slots WHERE id=?',(sid,)); d.commit(); flash('Slot deleted.','success')
  else: flash('A slot with active bookings cannot be deleted.','danger')
 else: flash('You can remove your slot only before booking starts.','danger')
 return redirect(url_for('examiner.slots'))

@examiner_bp.route('/students')
@roles_required('examiner')
def students():
 rows=get_db().execute('''SELECT b.id booking_id,b.status booking_status,b.booked_at,u.name student_name,u.email,s.exam_date,s.start_time,s.end_time,e.name exam_name,
 v.id evaluation_id FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations e ON e.id=s.examination_id JOIN users u ON u.id=b.student_id
 LEFT JOIN evaluations v ON v.booking_id=b.id WHERE s.examiner_id=? ORDER BY s.exam_date,s.start_time''',(session['user_id'],)).fetchall()
 return render_template('examiner_students.html',bookings=rows)

@examiner_bp.route('/evaluate/<int:bid>',methods=['GET','POST'])
@roles_required('examiner')
def evaluate(bid):
 d=get_db(); b=d.execute('''SELECT b.*,s.examiner_id,s.examination_id,e.name exam_name,u.name student_name FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations e ON e.id=s.examination_id JOIN users u ON u.id=b.student_id WHERE b.id=? AND s.examiner_id=? AND b.status='booked' ''',(bid,session['user_id'])).fetchone()
 if not b: flash('This booking is not assigned to you or is no longer active.','danger'); return redirect(url_for('examiner.students'))
 rubrics=d.execute('SELECT * FROM rubrics WHERE examination_id=?',(b['examination_id'],)).fetchall()
 if not rubrics: flash('The administrator has not configured a rubric for this examination.','warning'); return redirect(url_for('examiner.students'))
 if request.method=='POST':
  try:
   marks=[]; total=0
   exam_max=d.execute('SELECT max_marks FROM examinations WHERE id=?',(b['examination_id'],)).fetchone()['max_marks']
   for r in rubrics:
    m=float(request.form.get(f'marks_{r["id"]}','0'))
    if m<0 or m>r['max_marks']: raise ValueError('Marks must be within each criterion maximum.')
    marks.append((r,m,request.form.get(f'remarks_{r["id"]}',''))); total+=m
   if total>exam_max: raise ValueError('Total marks cannot exceed the examination maximum.')
   old=d.execute('SELECT id FROM evaluations WHERE booking_id=?',(bid,)).fetchone()
   if old:
    d.execute('DELETE FROM evaluation_items WHERE evaluation_id=?',(old['id'],)); d.execute('UPDATE evaluations SET examiner_id=?,total_marks=?,remarks=?,published=?,evaluated_at=CURRENT_TIMESTAMP WHERE id=?',(session['user_id'],total,request.form.get('remarks',''),1 if request.form.get('publish')=='1' else 0,old['id'])); vid=old['id']
   else:
    cur=d.execute('INSERT INTO evaluations(booking_id,examiner_id,total_marks,remarks,published) VALUES(?,?,?,?,?)',(bid,session['user_id'],total,request.form.get('remarks',''),1 if request.form.get('publish')=='1' else 0)); vid=cur.lastrowid
   for r,m,remark in marks: d.execute('INSERT INTO evaluation_items(evaluation_id,rubric_id,marks,remarks) VALUES(?,?,?,?)',(vid,r['id'],m,remark))
   d.commit(); flash('Evaluation saved'+(' and published.' if request.form.get('publish')=='1' else ' as draft.'),'success'); return redirect(url_for('examiner.students'))
  except ValueError as e: d.rollback(); flash(str(e),'danger')
  except Exception: d.rollback(); flash('Could not save evaluation.','danger')
 existing=d.execute('SELECT * FROM evaluations WHERE booking_id=?',(bid,)).fetchone()
 items={x['rubric_id']:x for x in d.execute('SELECT i.* FROM evaluation_items i JOIN evaluations v ON v.id=i.evaluation_id WHERE v.booking_id=?',(bid,)).fetchall()}
 return render_template('evaluate.html',booking=b,rubrics=rubrics,existing=existing,items=items)

@examiner_bp.route('/slots/<int:sid>/edit',methods=['GET','POST'])
@roles_required('examiner')
def edit_slot(sid):
 d=get_db(); s=d.execute('SELECT * FROM slots WHERE id=? AND examiner_id=?',(sid,session['user_id'])).fetchone()
 if not s: flash('Slot not found.','danger'); return redirect(url_for('examiner.slots'))
 active=d.execute("SELECT COUNT(*) FROM bookings WHERE slot_id=? AND status='booked'",(sid,)).fetchone()[0]
 if setting('booking_open')=='1' or active:
  flash('Slots can be edited only before booking starts and before they have bookings.','danger'); return redirect(url_for('examiner.slots'))
 if request.method=='POST':
  try:
   exam=d.execute('SELECT * FROM examinations WHERE id=?',(s['examination_id'],)).fetchone(); day=request.form['exam_date']
   if not exam['slot_start']<=day<=exam['slot_end'] or request.form['start_time']>=request.form['end_time']: raise ValueError()
   d.execute('UPDATE slots SET exam_date=?,start_time=?,end_time=?,capacity=? WHERE id=?',(day,request.form['start_time'],request.form['end_time'],int(request.form['capacity']),sid)); d.commit(); flash('Slot updated.','success'); return redirect(url_for('examiner.slots'))
  except Exception: d.rollback(); flash('Could not update slot. Check date, time and capacity.','danger')
 return render_template('edit_slot.html',slot=s)
