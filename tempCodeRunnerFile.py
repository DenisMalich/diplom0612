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

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'QwE123678'
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Хеш пароля администратора
admin_password_hash = ADMIN_PASSWORD_HASH
print("Admin password hash:", admin_password_hash)

# Определение моделей базы данных


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

# Определение маршрутов Flask


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/items')
def items():
    items = Item.query.all()
    return render_template('items.html', items=items)


@app.route('/reserve/<int:item_id>')
def reserve(item_id):
    item = Item.query.get_or_404(item_id)
    return render_template('reserve.html', item=item)


@app.route('/confirm_reservation', methods=['POST'])
def confirm_reservation():
    item_id = request.form['item_id']
    item = Item.query.get_or_404(item_id)
    item.status = 'reserved'
    db.session.commit()
    return redirect(url_for('items'))


@app.route('/profile')
def profile():
    user = User.query.first()
    rentals = []  # добавьте логику для получения истории аренды
    return render_template('profile.html', user=user, rentals=rentals)


@app.route('/admin')
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    items = Item.query.all()
    return render_template('admin_panel.html', items=items)


@app.route('/admin/add_item', methods=['POST'])
def add_item():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    name = request.form.get('name')
    size = request.form.get('size')
    color = request.form.get('color')
    price = request.form.get('price')

    try:
        price = float(price)
    except ValueError:
        logging.error(f'Некорректная цена: {price}')
        return redirect(url_for('admin_panel'))

    new_item = Item(name=name, size=size, color=color,
                    price=price, status='free')
    db.session.add(new_item)
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
            flash('Неверный пароль. Попробуйте снова.')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

# Инициализация Telegram бота


@app.route(f'/{TOKEN_TELEGRAM}', methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    update = Update.de_json(json.loads(json_str), application.bot)
    application.process_update(update)
    return '', 200


def set_webhook():
    url = f"{NGROK_URL}"
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
    user_id = update.message.from_user.id
    logging.info(f"Received /start command from user ID: {user_id}")
    if is_authorized_user(user_id):
        await update.message.reply_text("Привет! Я ваш бот.")
    else:
        await update.message.reply_text("У вас нет доступа к этому боту.")


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
