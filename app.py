import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from ics import Calendar
import requests
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'calendar')

# Настройка базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Модель сообщений чата
class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

# ICS календарь
#ICS_URL = "https://outlook.office365.com/owa/calendar/2735ffb1f9bd4648ab3dc9226825c675@lincoln.ac.uk/bd6830136a1749a98a6b452ea4d4e3cc6334812304006105882/calendar.ics"
ICS_URL = "https://outlook.office365.com/owa/calendar/f049117561b64b3daa03684d3fdcbd7e@akb.nis.edu.kz/a5a59de348bf4d449e7757adbc6af4a114622577659288145240/calendar.ics"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/events')
def get_events():
    try:
        response = requests.get(ICS_URL)
        response.raise_for_status()
        calendar = Calendar(response.text)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)

    today_events = []
    current_status = "free"

    status_priority = {
        "OOF": 4,
        "BUSY": 3,
        "TENTATIVE": 2,
        "FREE": 1
    }

    status_labels = {
        "OOF": "out of office",
        "BUSY": "busy",
        "TENTATIVE": "tentative",
        "FREE": "free"
    }

    max_priority = 0

    for event in calendar.timeline.included(today_start, today_end):
        event_status = None



        for extra in event.extra:
            if extra.name.upper() == "X-MICROSOFT-CDO-BUSYSTATUS":
                event_status = extra.value.upper()
                break


        if event.begin <= now <= (event.end or event.begin) and event_status:
            prio = status_priority.get(event_status, 0)
            if prio > max_priority:
                max_priority = prio
                current_status = status_labels.get(event_status, "free")

        today_events.append({
            "title": event.name,
            "start": event.begin.format("HH:mm"),
            "end": event.end.format("HH:mm") if event.end else "",
            "location": event.location or "",
            "description": event.description or ""
        })

    return jsonify({
        "status": current_status,
        "events": today_events
    })


@app.route('/chat')
def get_chat():
    limit_time = datetime.now(timezone.utc) - timedelta(hours=24)
    ChatMessage.query.filter(ChatMessage.timestamp < limit_time).delete()
    db.session.commit()

    # 👇 Эта строка заставляет SQLAlchemy перечитать данные из базы
    db.session.expire_all()

    last_message = ChatMessage.query.order_by(ChatMessage.timestamp.desc()).first()

    if last_message:
        db.session.refresh(last_message)
        return jsonify([{
            "content": last_message.content,
            "timestamp": last_message.timestamp.strftime("%H:%M")
        }])
    else:
        return jsonify([])



# Авторизация
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=False)

