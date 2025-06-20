import os
import pytz
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from ics import Calendar
import requests
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'calendar')

# Настройка базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Time zone used for all date calculations. It can be overridden by
# the TIMEZONE environment variable so deployments can display local
# times correctly.
LOCAL_TZ = pytz.timezone(os.environ.get('TIMEZONE', 'Europe/London'))

def get_local_time():
    """Return current time in the configured time zone."""
    current = datetime.now(LOCAL_TZ)
    print("time=", current)
    return current



class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500))
    # Store timezone-aware datetimes to avoid off-by-one-hour shifts
    timestamp = db.Column(db.DateTime(timezone=True), default=get_local_time)

ICS_URL = "https://outlook.office365.com/owa/calendar/2735ffb1f9bd4648ab3dc9226825c675@lincoln.ac.uk/bd6830136a1749a98a6b452ea4d4e3cc6334812304006105882/calendar.ics"
# Outlook’s ICS uses Microsoft time zone identifiers like
# ``West Asia Standard Time``. These are not recognized by ``pytz``,
# which leads to naive datetimes that are treated as London time.
# To keep event times correct we replace the Microsoft IDs with
# equivalent IANA names before parsing the calendar.
MS_TIMEZONE_MAP = {
    "West Asia Standard Time": "Asia/Qyzylorda",
    "Qyzylorda Standard Time": "Asia/Qyzylorda",
    "GMT Standard Time": "Europe/London",
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/events')
def get_events():
    try:
        response = requests.get(ICS_URL, headers={"Cache-Control": "no-cache"})
        response.raise_for_status()

        ics_text = response.text
        for ms_name, iana_name in MS_TIMEZONE_MAP.items():
            ics_text = ics_text.replace(ms_name, iana_name)

        calendar = Calendar(ics_text)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    now = get_local_time()
    today_start = datetime(now.year, now.month, now.day, tzinfo=LOCAL_TZ)
    today_end   = today_start + timedelta(days=1)

    today_events   = []
    current_status = "free"
    status_priority = {"OOF": 4, "BUSY": 3, "TENTATIVE": 2, "FREE": 1}
    status_labels   = {"OOF": "out of office", "BUSY": "busy", "TENTATIVE": "tentative", "FREE": "free"}
    max_priority    = 0

    for event in calendar.timeline.included(today_start, today_end):
        # 1) Извлекаем чистые datetime из ICS
        start_dt = event.begin.datetime
        end_dt   = event.end.datetime if event.end else start_dt

        # 2) Если нет tzinfo — "надеваем" локальную зону, иначе конвертим
        if start_dt.tzinfo is None:
            start_dt = LOCAL_TZ.localize(start_dt)
        else:
            start_dt = start_dt.astimezone(LOCAL_TZ)

        if end_dt.tzinfo is None:
            end_dt = LOCAL_TZ.localize(end_dt)
        else:
            end_dt = end_dt.astimezone(LOCAL_TZ)

        # 3) Пропускаем, если уже закончилось
        if end_dt <= now:
            continue

        # 4) Читаем статус события
        event_status = next(
            (e.value.upper() for e in event.extra
             if e.name.upper() == "X-MICROSOFT-CDO-BUSYSTATUS"),
            "FREE"
        )
        # Если оно прямо сейчас активно — обновляем статус ответа
        if start_dt <= now <= end_dt:
            prio = status_priority.get(event_status, 0)
            if prio > max_priority:
                max_priority    = prio
                current_status  = status_labels.get(event_status, "free")

        # 5) Добавляем в список будущих/текущих
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
    now = get_local_time()
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
            # Convert timestamps back to the configured time zone when displaying
            # and add one hour to the display time as requested
            "timestamp": (
                msg.timestamp.astimezone(LOCAL_TZ) + timedelta(hours=1)
            ).strftime("%H:%M %d.%m.%Y")
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
