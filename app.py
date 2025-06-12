import os
import pytz
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from ics import Calendar
import requests
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'calendar')

# Настройка базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

LONDON = pytz.timezone('Europe/London')

def get_london_time():
    print("time=",datetime.now(LONDON))
    return datetime.now(LONDON)



class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=get_london_time)

ICS_URL = "https://outlook.office365.com/owa/calendar/f049117561b64b3daa03684d3fdcbd7e@akb.nis.edu.kz/a5a59de348bf4d449e7757adbc6af4a114622577659288145240/calendar.ics"

@app.route('/')
def index():
    return render_template('index.html')
LONDON = ZoneInfo("Europe/London")

def get_london_time():
    # возвращаем сейчас в Europe/London, автоматически учитывая DST
    return datetime.now(tz=LONDON)

@app.route('/events')
def get_events():
    # ... загрузка ICS, calendar = Calendar(response.text) и т.п.

    now = get_london_time()
    # границы «сегодня» в лондонской зоне:
    today_start = datetime(now.year, now.month, now.day, tzinfo=LONDON)
    today_end   = today_start + timedelta(days=1)

    today_events   = []
    status_priority = {"OOF":4, "BUSY":3, "TENTATIVE":2, "FREE":1}
    status_labels   = {"OOF":"out of office","BUSY":"busy","TENTATIVE":"tentative","FREE":"free"}
    current_status = "free"
    max_priority   = status_priority[current_status]

    for event in calendar.timeline.included(today_start, today_end):
        # 1) Извлекаем чистые datetime из Arrow
        start_dt = getattr(event.begin, "naive", event.begin)
        end_dt   = getattr(event.end,   "naive", event.end) or start_dt

        # 2) Локализуем плавающие и конвертим зонные в London
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=LONDON)
        else:
            start_dt = start_dt.astimezone(LONDON)

        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=LONDON)
        else:
            end_dt = end_dt.astimezone(LONDON)

        # 3) Отсеиваем завершённые
        if end_dt <= now:
            continue

        # 4) Читаем X-Microsoft статус
        event_status = next(
            (e.value.upper() for e in event.extra
             if e.name.upper()=="X-MICROSOFT-CDO-BUSYSTATUS"),
            "FREE"
        )
        # Обновляем статус, если событие сейчас активно
        if start_dt <= now <= end_dt:
            prio = status_priority.get(event_status, 0)
            if prio > max_priority:
                max_priority    = prio
                current_status  = status_labels[event_status]

        # 5) Собираем вывод
        today_events.append({
            "title":       event.name,
            "start":       start_dt.strftime("%H:%M"),
            "end":         end_dt.strftime("%H:%M"),
            "location":    event.location or "",
            "description": event.description or ""
        })

    return jsonify({
        "status": current_status,
        "events": today_events
    })

@app.route('/chat')
def get_chat():
    now = get_london_time()
    start_of_day = datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)

    limit_time = now - timedelta(hours=24)
    ChatMessage.query.filter(ChatMessage.timestamp < limit_time).delete()
    db.session.commit()

    messages = ChatMessage.query \
        .filter(ChatMessage.timestamp >= start_of_day) \
        .order_by(ChatMessage.timestamp.asc()).all()

    return jsonify([
        {
            "content": msg.content,
            "timestamp": msg.timestamp.strftime("%H:%M %d.%m.%Y")
        } for msg in messages
    ])

USERNAME = 'admin'
PASSWORD = 'qwerty123'

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        if user == USERNAME and pwd == PASSWORD:
            session['logged_in'] = True
            flash('Успешный вход!', 'success')
            return redirect(url_for('send_form'))
        else:
            flash('Неверный логин или пароль.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash("Вы вышли из аккаунта.", "success")
    return redirect(url_for('login'))

@app.route('/send', methods=['GET', 'POST'])
def send_form():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        content = request.form.get('content')
        if not content:
            flash("Пустое сообщение недопустимо.", "error")
        else:
            db.session.add(ChatMessage(content=content))
            db.session.commit()
            flash("Сообщение успешно отправлено!", "success")
        return redirect(url_for('send_form'))

    return render_template('send.html')

@app.route('/init-db')
def init_db():
    with app.app_context():
        db.create_all()
    return "Таблицы созданы!"

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=False)
