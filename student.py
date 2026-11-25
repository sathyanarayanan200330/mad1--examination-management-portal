from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from auth import roles_required
from database import get_db, setting
student_bp=Blueprint('student',__name__)

@student_bp.route('/')
@roles_required('student')
def dashboard():
 d=get_db(); uid=session['user_id']
 available=d.execute('''SELECT e.*,c.code course_code,c.name course_name,COUNT(s.id) slot_count FROM examinations e JOIN courses c ON c.id=e.course_id JOIN slots s ON s.examination_id=e.id
 WHERE e.booking_start<=date('now','localtime') AND e.booking_end>=date('now','localtime') AND s.status='available' GROUP BY e.id ORDER BY e.booking_start''').fetchall()
 bookings=d.execute('''SELECT b.*,s.exam_date,s.start_time,s.end_time,e.name exam_name,x.name examiner_name FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations e ON e.id=s.examination_id JOIN users x ON x.id=s.examiner_id WHERE b.student_id=? ORDER BY s.exam_date DESC''',(uid,)).fetchall()
 results=d.execute('''SELECT v.*,e.name exam_name,s.exam_date FROM evaluations v JOIN bookings b ON b.id=v.booking_id JOIN slots s ON s.id=b.slot_id JOIN examinations e ON e.id=s.examination_id WHERE b.student_id=? AND v.published=1 ORDER BY v.evaluated_at DESC''',(uid,)).fetchall()
 return render_template('student_dashboard.html',available=available,bookings=bookings,results=results,booking_open=setting('booking_open')=='1')

@student_bp.route('/examinations')
@roles_required('student')
def examinations():
 q=request.args.get('q','').strip(); like=f'%{q}%'
 rows=get_db().execute('''SELECT e.*,c.code course_code,c.name course_name FROM examinations e JOIN courses c ON c.id=e.course_id
 WHERE (e.name LIKE ? OR c.name LIKE ? OR c.code LIKE ? OR e.exam_type LIKE ?) ORDER BY e.name''',(like,like,like,like)).fetchall()
 return render_template('student_examinations.html',exams=rows,q=q)

@student_bp.route('/examinations/<int:eid>/slots')
@roles_required('student')
def available_slots(eid):
 d=get_db(); exam=d.execute('SELECT * FROM examinations WHERE id=?',(eid,)).fetchone()
 if not exam: flash('Examination not found.','danger'); return redirect(url_for('student.examinations'))
 rows=d.execute('''SELECT s.*,u.name examiner_name,(SELECT COUNT(*) FROM bookings b WHERE b.slot_id=s.id AND b.status='booked') booked
 FROM slots s JOIN users u ON u.id=s.examiner_id WHERE s.examination_id=? AND s.status='available' ORDER BY s.exam_date,s.start_time''',(eid,)).fetchall()
 return render_template('student_slots.html',exam=exam,slots=rows,booking_open=setting('booking_open')=='1')

@student_bp.route('/book/<int:sid>',methods=['POST'])
@roles_required('student')
def book(sid):
 d=get_db(); uid=session['user_id']
 if setting('booking_open')!='1': flash('Student slot booking is currently closed.','danger'); return redirect(url_for('student.dashboard'))
 s=d.execute('SELECT s.*,e.booking_start,e.booking_end,e.id exam_id FROM slots s JOIN examinations e ON e.id=s.examination_id WHERE s.id=?',(sid,)).fetchone()
 if not s or s['status']!='available' or not (s['booking_start'] <= __import__('datetime').date.today().isoformat() <= s['booking_end']): flash('This slot is not currently available for booking.','danger'); return redirect(url_for('student.dashboard'))
 duplicate=d.execute('''SELECT COUNT(*) FROM bookings b JOIN slots x ON x.id=b.slot_id WHERE b.student_id=? AND x.examination_id=? AND b.status='booked' ''',(uid,s['exam_id'])).fetchone()[0]
 if duplicate: flash('You already have an active booking for this examination.','warning'); return redirect(url_for('student.dashboard'))
 count=d.execute("SELECT COUNT(*) FROM bookings WHERE slot_id=? AND status='booked'",(sid,)).fetchone()[0]
 if count>=s['capacity']: d.execute("UPDATE slots SET status='full' WHERE id=?",(sid,)); d.commit(); flash('This slot is full.','danger'); return redirect(url_for('student.available_slots',eid=s['exam_id']))
 d.execute('INSERT INTO bookings(student_id,slot_id) VALUES(?,?)',(uid,sid))
 if count+1>=s['capacity']: d.execute("UPDATE slots SET status='full' WHERE id=?",(sid,))
 d.commit(); flash('Examination slot booked successfully.','success'); return redirect(url_for('student.dashboard'))

@student_bp.route('/cancel/<int:bid>',methods=['POST'])
@roles_required('student')
def cancel(bid):
 d=get_db(); b=d.execute('''SELECT b.*,s.id sid,e.booking_end FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations e ON e.id=s.examination_id WHERE b.id=? AND b.student_id=?''',(bid,session['user_id'])).fetchone()
 if b and b['status']=='booked' and __import__('datetime').date.today().isoformat()<=b['booking_end']:
  d.execute("UPDATE bookings SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=?",(bid,)); d.execute("UPDATE slots SET status='available' WHERE id=? AND status='full'",(b['sid'],)); d.commit(); flash('Booking cancelled. The booking history has been retained.','success')
 else: flash('Booking cannot be cancelled after the booking deadline.','danger')
 return redirect(url_for('student.dashboard'))

@student_bp.route('/profile',methods=['GET','POST'])
@roles_required('student')
def profile():
 d=get_db(); u=d.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
 if request.method=='POST':
  d.execute('UPDATE users SET name=?,phone=?,department=? WHERE id=?',(request.form['name'].strip(),request.form.get('phone','').strip(),request.form.get('department','').strip(),session['user_id'])); d.commit(); session['name']=request.form['name'].strip(); flash('Profile updated.','success'); return redirect(url_for('student.profile'))
 return render_template('profile.html',user=u)
