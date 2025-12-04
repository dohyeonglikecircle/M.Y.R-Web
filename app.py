from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'moyeo-rock-secret-key'

database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- [DB 모델] ---
team_members = db.Table('team_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('team_id', db.Integer, db.ForeignKey('team.id'))
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    cohort = db.Column(db.Float, nullable=True)
    session = db.Column(db.String(50), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    schedule_json = db.Column(db.Text, nullable=True)
    teams = db.relationship('Team', secondary=team_members, backref='members')

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    leader_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    confirmed_schedules = db.relationship('ConfirmedSchedule', backref='team', cascade="all, delete-orphan")

class ConfirmedSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    target_date = db.Column(db.String(20), nullable=False)
    time_index = db.Column(db.Integer, nullable=False)

class Notice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

class Instrument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_available = db.Column(db.Boolean, default=True)

class InstrumentReservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_type = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    user = db.relationship('User', backref='reservations')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def init_instruments():
    try:
        if Instrument.query.count() == 0:
            base = [
                {'code': 'guitar1', 'name': 'Squire - FSR Affinity Stratocaster', 'is_available': True},
                {'code': 'guitar2', 'name': 'Ibanez - RG350DXZ', 'is_available': True},
                {'code': 'guitar3', 'name': 'Beyond - 모델 모르겠어요....ㅠ', 'is_available': True},
                {'code': 'geffect', 'name': 'Mytone - DX1 (Distortion)', 'is_available': True},
                {'code': 'bass1', 'name': 'Twoman - TJB-100', 'is_available': True},
                {'code': 'bass2', 'name': 'Swing - Jazz King Plus Red Burst', 'is_available': True},
                {'code': 'bass3', 'name': 'Swing - Jazz King WH(M)', 'is_available': True},
                {'code': 'beffect', 'name': 'Valeton - Dapper Bass', 'is_available': True},
                {'code': 'keyboard', 'name': 'Main Keyboard (Yamaha/Kurzweil)', 'is_available': True},
                {'code': 'drum', 'name': 'Main Drum Set', 'is_available': True}
            ]
            for item in base:
                db.session.add(Instrument(code=item['code'], name=item['name'], is_available=item['is_available']))
            db.session.commit()
    except: pass

def get_calendar_weeks():
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    weeks = []
    for w in range(5):
        week_days = []
        for d in range(7):
            current_day = start_of_week + timedelta(weeks=w, days=d)
            date_str = current_day.strftime('%Y-%m-%d')
            weekday_kor = ['월', '화', '수', '목', '금', '토', '일'][current_day.weekday()]
            display_str = f"{current_day.month}/{current_day.day} ({weekday_kor})"
            week_days.append({'date': date_str, 'display': display_str, 'is_past': current_day < today})
        weeks.append(week_days)
    return weeks

# --- [라우팅] ---

@app.route('/')
def home():
    try: notices = Notice.query.order_by(Notice.date_posted.desc()).limit(3).all()
    except: notices = []
    return render_template('index.html', notices=notices)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form.get('username'); password = request.form.get('password'); name = request.form.get('name')
        if User.query.filter_by(username=username).first(): flash('이미 존재하는 아이디입니다.'); return redirect(url_for('register'))
        if username == 'admin': is_admin=True; final_cohort=None; final_session='admin'
        else:
            if not request.form.get('cohort'): flash('기수/세션 필수'); return redirect(url_for('register'))
            is_admin=False; final_cohort=float(request.form.get('cohort')); final_session=request.form.get('session')
        db.session.add(User(username=username, password=password, name=name, cohort=final_cohort, session=final_session, is_admin=is_admin)); db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'): login_user(user); return redirect(url_for('home'))
        flash('아이디 또는 비밀번호 확인')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('home'))

@app.route('/notice')
def notice_list(): return render_template('notice.html', notices=Notice.query.order_by(Notice.date_posted.desc()).all())

@app.route('/notice/new', methods=['GET', 'POST'])
@login_required
def new_notice():
    if not current_user.is_admin: return "관리자만 접근 가능합니다."
    if request.method == 'POST':
        db.session.add(Notice(title=request.form.get('title'), content=request.form.get('content')))
        db.session.commit(); return redirect(url_for('notice_list'))
    return render_template('notice_form.html')

@app.route('/schedule', methods=['GET', 'POST'])
def schedule():
    if request.method == 'POST':
        if not current_user.is_admin: return redirect(url_for('schedule'))
        try:
            s = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
            e = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date() if request.form.get('end_date') else s
            db.session.add(Schedule(title=request.form.get('title'), start_date=s, end_date=e)); db.session.commit()
        except: flash("오류")
        return redirect(url_for('schedule'))
    ev = [{'title':e.title, 'start':e.start_date.strftime('%Y-%m-%d'), 'end':(e.end_date+timedelta(days=1)).strftime('%Y-%m-%d'), 'color':'#dc3545' if '공연' in e.title else '#0d6efd'} for e in Schedule.query.all()]
    return render_template('schedule.html', events_data=ev)

@app.route('/myschedule', methods=['GET', 'POST'])
@login_required
def myschedule():
    if request.method == 'POST':
        new_data = json.loads(request.form.get('schedule_data'))
        current_data = json.loads(current_user.schedule_json) if current_user.schedule_json else {}
        current_data.update(new_data)
        current_user.schedule_json = json.dumps(current_data)
        db.session.commit()
        flash("시간표가 저장되었습니다.")
        return redirect(url_for('myschedule'))
    
    weeks = get_calendar_weeks()
    my_schedule = json.loads(current_user.schedule_json) if current_user.schedule_json else {}
    return render_template('myschedule.html', weeks=weeks, my_schedule=my_schedule)

@app.route('/team', methods=['GET', 'POST'])
@login_required
def team_dashboard():
    if request.method == 'POST':
        tn = request.form.get('team_name')
        if tn:
            t = Team(name=tn, leader_id=current_user.id); t.members.append(current_user); db.session.add(t); db.session.commit()
            flash('생성 완료')
        return redirect(url_for('team_dashboard'))
    return render_template('team.html', teams=current_user.teams)

@app.route('/api/search_user', methods=['GET'])
@login_required
def api_search_user():
    q = request.args.get('query','').strip(); res = []
    if not q: return jsonify([])
    for u in User.query.filter(User.name.contains(q)).all():
        cohort = str(int(u.cohort)) if u.cohort and u.cohort.is_integer() else str(u.cohort)
        d = f"관리자 ({u.name})" if u.is_admin else f"{cohort}{u.session[0]} {u.name}"
        res.append({'id':u.id, 'username':u.username, 'display':d})
    return jsonify(res)

@app.route('/team/<int:team_id>', methods=['GET', 'POST'])
@login_required
def team_detail(team_id):
    team = Team.query.get_or_404(team_id)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_member_by_id':
            u = User.query.get(request.form.get('target_user_id'))
            if u and u not in team.members: team.members.append(u); db.session.commit(); flash("초대 완료")
            return redirect(url_for('team_detail', team_id=team_id))
        elif action == 'batch_confirm':
            slots = json.loads(request.form.get('selected_slots'))
            count = 0
            for slot in slots:
                date_str, idx = slot.split('_'); idx = int(idx)
                if not ConfirmedSchedule.query.filter_by(team_id=team.id, target_date=date_str, time_index=idx).first():
                    db.session.add(ConfirmedSchedule(team_id=team.id, target_date=date_str, time_index=idx)); count += 1
            if count > 0: db.session.commit(); flash(f"{count}개 확정!")
            return redirect(url_for('team_detail', team_id=team_id))
        elif action == 'delete_confirm':
            t = ConfirmedSchedule.query.filter_by(team_id=team.id, target_date=request.form.get('date'), time_index=int(request.form.get('time_index'))).first()
            if t: db.session.delete(t); db.session.commit()
            return redirect(url_for('team_detail', team_id=team_id))
        elif action == 'delete_team':
            if team.leader_id==current_user.id: db.session.delete(team); db.session.commit(); return redirect(url_for('team_dashboard'))

    weeks = get_calendar_weeks()
    overlap_data = {}
    all_dates = [d['date'] for w in weeks for d in w]
    for d in all_dates: overlap_data[d] = [0]*30

    confirmed_slots = [f"{c.target_date}_{c.time_index}" for c in team.confirmed_schedules]

    for member in team.members:
        if not member.schedule_json: continue
        sched = json.loads(member.schedule_json)
        busy_slots = []
        for t in member.teams:
            if t.id == team.id: continue
            for cs in t.confirmed_schedules: busy_slots.append(f"{cs.target_date}_{cs.time_index}")
        
        for date_str in all_dates:
            if date_str in sched:
                for i in range(30):
                    if sched[date_str][i] == 1 and f"{date_str}_{i}" not in busy_slots: overlap_data[date_str][i] += 1

    return render_template('team_detail.html', team=team, weeks=weeks, overlap_data=overlap_data, confirmed_slots=confirmed_slots, total_members=len(team.members))

@app.route('/session/<type>', methods=['GET', 'POST'])
@login_required
def session_page(type):
    session_type = type.lower()
    if request.method == 'POST':
        action = request.form.get('action_type')
        if action == 'toggle_status':
            if not current_user.is_admin: flash("관리자만 변경할 수 있습니다."); return redirect(url_for('session_page', type=type))
            target_code = request.form.get('target_code')
            inst = Instrument.query.filter_by(code=target_code).first()
            if inst: inst.is_available = not inst.is_available; db.session.commit(); flash("상태 변경됨")
            return redirect(url_for('session_page', type=type))
        elif action == 'reserve':
            item = request.form.get('item_type'); start_str = request.form.get('start_date'); end_str = request.form.get('end_date')
            target_inst = Instrument.query.filter_by(code=item).first()
            if target_inst and not target_inst.is_available: flash("현재 사용 불가"); return redirect(url_for('session_page', type=type))
            try:
                start_obj = datetime.strptime(start_str, '%Y-%m-%dT%H:%M'); end_obj = datetime.strptime(end_str, '%Y-%m-%dT%H:%M')
                if start_obj >= end_obj: flash("시간 오류"); return redirect(url_for('session_page', type=type))
                if (end_obj - start_obj).total_seconds() / 3600 > 72: flash("최대 72시간"); return redirect(url_for('session_page', type=type))
                if InstrumentReservation.query.filter(InstrumentReservation.item_type == item, InstrumentReservation.start_date < end_obj, InstrumentReservation.end_date > start_obj).first(): flash("이미 예약됨"); return redirect(url_for('session_page', type=type))
                db.session.add(InstrumentReservation(user_id=current_user.id, item_type=item, start_date=start_obj, end_date=end_obj)); db.session.commit(); flash("예약 완료")
            except: flash("오류 발생")
            return redirect(url_for('session_page', type=type))

    leader_info = None
    if session_type == 'vocal': leader_info = {'name': '김서연', 'intro': '보컬 파트장', 'insta': 'https://www.instagram.com/florescence_328'}
    elif session_type == 'guitar': leader_info = {'name': '배은성', 'intro': '기타 파트장', 'insta': 'https://www.instagram.com/shawn_t.s_/'}
    elif session_type == 'bass': leader_info = {'name': '김하은', 'intro': '베이스 파트장', 'insta': 'https://www.instagram.com/ovwewo/'}
    elif session_type == 'keyboard': leader_info = {'name': '김민현', 'intro': '키보드 파트장', 'insta': 'https://www.instagram.com/galsgus/'}
    elif session_type == 'drum': leader_info = {'name': '추서현', 'intro': '드럼 파트장', 'insta': 'https://www.instagram.com/seohyun_choo/'}

    events_data = []; instruments_status = {}
    target_items = []
    if session_type == 'guitar': target_items = ['guitar1', 'guitar2', 'guitar3', 'geffect']
    elif session_type == 'bass': target_items = ['bass1', 'bass2', 'bass3', 'beffect']
    elif session_type == 'keyboard': target_items = ['keyboard']
    elif session_type == 'drum': target_items = ['drum']

    if target_items:
        all_insts = Instrument.query.filter(Instrument.code.in_(target_items)).all()
        instruments_status = {inst.code: inst for inst in all_insts}
        color_map = {'guitar1': '#dc3545', 'guitar2': '#ffc107', 'guitar3': '#198754', 'geffect': '#0d6efd', 'bass1': '#198754', 'bass2': '#0d6efd', 'bass3': '#6f42c1', 'beffect': '#ffc107', 'keyboard': '#ffc107', 'drum': '#dc3545'}
        session_initials = {'Vocal': 'V', 'Guitar': 'G', 'Bass': 'B', 'Keyboard': 'K', 'Drum': 'D', 'admin': 'A'}
        reservations = InstrumentReservation.query.filter(InstrumentReservation.item_type.in_(target_items)).all()
        for res in reservations:
            u = res.user; initial = session_initials.get(u.session, '?')
            cohort_str = str(int(u.cohort)) if u.cohort and u.cohort.is_integer() else str(u.cohort)
            display = "관리자" if u.is_admin else f"{cohort_str}{initial} {u.name}"
            events_data.append({'title': display, 'start': res.start_date.isoformat(), 'end': res.end_date.isoformat(), 'color': color_map.get(res.item_type, '#6c757d')})

    return render_template('instruments.html', type=type.upper(), leader=leader_info, session_type=session_type, events_data=events_data, inst_status=instruments_status)

@app.route('/sys_init')
def sys_init():
    # 1. 기존 데이터베이스 삭제 (가장 중요!)
    db.drop_all()
    
    # 2. 깨끗한 상태에서 다시 생성
    db.create_all()
    
    # 3. 기본 악기 데이터 채우기
    init_instruments()
    
    return "🎉 데이터베이스가 싹 지워지고(Reset) 새로 만들어졌습니다! 이제 기존 계정은 없습니다."

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True, port=5001)