from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import logging
import requests
import threading
import asyncio
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import ADMIN_PASSWORD_HASH, TOKEN_TELEGRAM, NGROK_URL, ADMIN_ID, USER_ID
from werkzeug.security import generate_password_hash, check_password_hash
import os
from flask import send_from_directory
from datetime import datetime, timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'QwE123678'
app.config['UPLOAD_FOLDER'] = 'static/images'
db = SQLAlchemy(app)
migrate = Migrate(app, db)

category_mapping = {
    'clothing': 'Одежда',
    'accessories': 'Аксессуары',
    'shoes': 'Обувь',
    'headwear': 'Головные уборы',
    'ready_to_wear': 'Готовый образ',
    'default_category': 'Одежда'
}

admin_password_hash = ADMIN_PASSWORD_HASH
print("Admin password hash:", admin_password_hash)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    size = db.Column(db.String(20))
    color = db.Column(db.String(20))
    return_date = db.Column(db.Date)
    status = db.Column(db.String(20))
    price = db.Column(db.Float)
    image = db.Column(db.String(120))
    category = db.Column(db.String(50))
    description = db.Column(db.String(255))


def get_item_by_id(item_id):
    return Item.query.get_or_404(item_id)


@app.route('/item/<int:item_id>', endpoint='item_view')
def item_detail(item_id):
    item = get_item_by_id(item_id)
    return render_template('item_detail.html', item=item)


def send_email(subject, body, to_email="rabotabota24@mail.ru"):
    from_email = "rabotabota24@mail.ru"
    password = "4v0qFjVF65ZwvETPpKzD"

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.mail.ru', 587)
        server.starttls()
        server.login(from_email, password)
        text = msg.as_string()
        server.sendmail(from_email, to_email, text)
        server.quit()
        print("Письмо отправлено успешно")
    except Exception as e:
        print(f"Не удалось отправить письмо: {e}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/items')
def items():
    category = request.args.get('category')
    print(f"Selected category: {category}")

    if category:
        category_english = {
            'Одежда': 'clothing',
            'Аксессуары': 'accessories',
            'Обувь': 'shoes',
            'Головные уборы': 'headwear',
            'Готовый образ': 'ready_to_wear'
        }.get(category, category)

        print(f"Category in English: {category_english}")
        items = Item.query.filter_by(category=category_english).all()
    else:
        items = Item.query.all()

    print(f"Number of items found: {len(items)}")
    return render_template('items.html', items=items)


@app.route('/edit_item/<int:item_id>', methods=['GET'])
def edit_item(item_id):
    item = get_item_by_id(item_id)
    return render_template('edit_item.html', item=item)


@app.route('/update_item/<int:item_id>', methods=['POST'])
def update_item(item_id):
    item = Item.query.get_or_404(item_id)
    item.name = request.form['name']
    item.size = request.form['size']
    item.color = request.form['color']
    item.description = request.form.get('description', '')
    item.category = request.form['category']
    item.price = float(request.form['price'])
    item.status = request.form['status']

    image = request.files.get('image')
    if image and image.filename:
        filename = image.filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(file_path)
        item.image = filename

    db.session.commit()
    return redirect(url_for('admin_panel'))


@app.route('/reservation_success')
def success():
    user_email = "example@example.com"
    return render_template('reservation_success.html', user_email=user_email)


@app.route('/reserve/<int:item_id>', methods=['GET', 'POST'])
def reserve(item_id):
    item = Item.query.get_or_404(item_id)
    today_date = datetime.now().date()
    max_date = today_date + timedelta(days=365)

    if request.method == 'POST':
        user_name = request.form['user_name']
        user_surname = request.form['user_surname']
        reservation_type = request.form['reservation_type']
        reservation_date = request.form.get('reservation_date')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        payment_method = request.form['payment_method']
        user_phone = request.form['user_phone']

        subject = "Новая бронь"
        body = (f"Новая бронь:\n"
                f"Имя: {user_name}\n"
                f"Фамилия: {user_surname}\n"
                f"Тип бронирования: {
                    'Один день' if reservation_type == 'single_day' else 'Интервал'}\n"
                f"Дата резервирования: {
                    reservation_date if reservation_type == 'single_day' else ''}\n"
                f"Дата начала: {
                    start_date if reservation_type == 'interval' else ''}\n"
                f"Дата окончания: {
                    end_date if reservation_type == 'interval' else ''}\n"
                f"Метод оплаты: {payment_method}\n"
                f"Номер телефона: {user_phone}")

        send_email(subject, body, "vetgid@mail.ru")

        return redirect(url_for('success'))

    return render_template('reserve.html', item=item, today_date=today_date, max_date=max_date)


@app.route('/confirm_reservation', methods=['POST'])
def confirm_reservation():
    item_id = request.form['item_id']
    reservation_date_str = request.form['reservation_date']
    try:
        reservation_date = datetime.strptime(
            reservation_date_str, '%Y-%m-%d').date()
        item = Item.query.get_or_404(item_id)
        item.status = 'reserved'
        item.return_date = reservation_date
        db.session.commit()
        return redirect(url_for('items'))
    except ValueError:
        flash('Некорректная дата. Попробуйте снова.', 'danger')


@app.route('/clothing')
def clothing():
    items = Item.query.filter_by(category='Одежда').all()
    return render_template('items.html', items=items)


@app.route('/accessories')
def accessories():
    items = Item.query.filter_by(category='Аксессуары').all()
    return render_template('items.html', items=items)


@app.route('/footwear')
def footwear():
    items = Item.query.filter_by(category='Обувь').all()
    return render_template('items.html', items=items)


@app.route('/headwear')
def headwear():
    items = Item.query.filter_by(category='Головные уборы').all()
    return render_template('items.html', items=items)


@app.route('/complete_outfit')
def complete_outfit():
    items = Item.query.filter_by(category='Готовый образ').all()
    return render_template('items.html', items=items)


@app.route('/profile')
def profile():
    user = User.query.first()
    rentals = []  # добавьте логику для получения истории аренды
    return render_template('profile.html', user=user, rentals=rentals)


@app.route('/admin', methods=['GET'])
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    category = request.args.get('category')
    if category:
        items = Item.query.filter_by(category=category).all()
    else:
        items = Item.query.all()

    return render_template('admin_panel.html', items=items)


@app.route('/admin/add_item', methods=['POST'])
def add_item():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    name = request.form['name']
    size = request.form['size']
    color = request.form['color']
    description = request.form.get('description', '')
    category = request.form['category']
    price = float(request.form['price'])
    status = request.form['status']
    image = request.files.get('image')
    filename = image.filename if image else None

    if image and filename:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(file_path)

    new_item = Item(name=name, size=size, color=color, description=description,
                    category=category, price=price, status=status, image=filename)
    db.session.add(new_item)
    db.session.commit()
    return redirect(url_for('admin_panel'))


@app.route('/admin/delete_item/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    item = Item.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('admin_panel'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if check_password_hash(admin_password_hash, password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            flash('Неверный пароль. Попробуйте снова.', 'danger')
    return render_template('admin_login.html')


@app.route('/item/<int:item_id>')
def item_detail(item_id):
    item = get_item_by_id(item_id)
    return render_template('item_detail.html', item=item)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))


async def process_webhook(update: Update) -> None:
    await application.process_update(update)


@app.route(f'/{TOKEN_TELEGRAM}', methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    update = Update.de_json(json.loads(json_str), application.bot)

    # Создаем новый цикл событий
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Запускаем асинхронную задачу
    asyncio.run_coroutine_threadsafe(
        process_webhook(update), loop)

    return '', 200


def set_webhook():
    url = f"{NGROK_URL}/{TOKEN_TELEGRAM}"
    try:
        response = requests.post(
            f'https://api.telegram.org/bot{TOKEN_TELEGRAM}/setWebhook',
            json={'url': url}
        )
        response.raise_for_status()
        logging.info(f'Set webhook response: {response.json()}')
    except requests.RequestException as e:
        logging.error(f'Ошибка установки webhook: {e}')


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)


def is_authorized_user(user_id):
    return user_id == ADMIN_ID or user_id == USER_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = 'https://smoothly-fun-cicada.ngrok-free.app/'
    await update.message.reply_text(f"Привет! Перейдите на нашу стартовую страницу: {url}")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logging.info(f"Received /admin command from user ID: {user_id}")
    if user_id == ADMIN_ID:
        await update.message.reply_text("Эта команда доступна только администратору.")
    else:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logging.info(f"Received /stop command from user ID: {user_id}")
    if user_id == ADMIN_ID:
        await update.message.reply_text("Останавливаю сервер и бота...")
        shutdown_server()
    else:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")


def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func:
        func()
    else:
        logging.error("Ошибка: сервер не использует Werkzeug.")


async def bot_main() -> None:
    global application
    application = ApplicationBuilder().token(TOKEN_TELEGRAM).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("stop", stop))

    await application.initialize()
    set_webhook()
    await application.start()

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await application.stop()


def run_bot():
    asyncio.run(bot_main())


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    flask_thread = threading.Thread(target=lambda: app.run(
        debug=True, host='0.0.0.0', port=8080, use_reloader=False))
    flask_thread.start()

    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()

    flask_thread.join()
    bot_thread.join()
