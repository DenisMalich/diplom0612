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
from aiogram import Bot, Dispatcher, types
from functools import wraps
from telebot import types

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'QwE123678'
app.config['UPLOAD_FOLDER'] = 'web_bot\\static\\images'

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

category_mapping = {
    'clothing': 'Одежда',
    'accessories': 'Аксессуары',
    'shoes': 'Обувь',
    'headwear': 'Головные уборы',
    'ready_to_wear': 'Готовый образ',
    'default_category': 'Одежда'
}

admin_password_hash = ADMIN_PASSWORD_HASH
logger.info("Admin password hash загружен.")

bot = Bot(token=TOKEN_TELEGRAM)


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

    def __repr__(self):
        return f"<User {self.first_name} {self.last_name}, Email: {self.email}>"


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

    def __repr__(self):
        return f"<Item {self.name}, Price: {self.price}>"


def get_item_by_id(item_id):
    return Item.query.get_or_404(item_id)


@app.route('/item/<int:item_id>', endpoint='item_view')
def item_detail(item_id):
    item = get_item_by_id(item_id)
    return render_template('item_detail.html', item=item)



def configure_server(from_email, password):
    try:
        server = smtplib.SMTP('smtp.mail.ru', 587)
        server.starttls()
        server.login(from_email, password)
        return server
    except Exception as e:
        print(f"Ошибка при настройке сервера: {e}")
        return None

def create_message(subject, body, from_email, to_email):
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    return msg

def send_email(subject, body, to_email="rabotabota24@mail.ru"):
    from_email = "rabotabota24@mail.ru"
    password = "4v0qFjVF65ZwvETPpKzD"

    msg = create_message(subject, body, from_email, to_email)
    
    if server := configure_server(from_email, password):
        try:
            server.sendmail(from_email, to_email, msg.as_string())
            print("Письмо отправлено успешно")
        except Exception as e:
            print(f"Не удалось отправить письмо: {e}")
        finally:
            server.quit()
    else:
        print("Не удалось настроить соединение с сервером")


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

    try:
        item.price = float(request.form['price'])
    except ValueError:
        flash('Некорректная цена. Пожалуйста, введите число.', 'danger')
        logging.warning(
            f"Некорректное значение цены для элемента ID {item_id}.")
        return redirect(url_for('edit_item', item_id=item_id))

    item.status = request.form['status']

    
    image = request.files.get('image')
    if image and image.filename:
        
        if not allowed_file(image.filename):
            flash('Недопустимый тип файла. Пожалуйста, загрузите изображение.', 'danger')
            return redirect(url_for('edit_item', item_id=item_id))

        filename = image.filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        try:
            image.save(file_path)
            item.image = filename
            logging.info(f"Изображение для элемента ID {
                         item_id} успешно обновлено.")
        except Exception as e:
            logging.error(
                f"Ошибка при сохранении изображения для элемента ID {item_id}: {e}")
            flash('Ошибка при загрузке изображения. Попробуйте еще раз.', 'danger')

    
    try:
        db.session.commit()
        logging.info(f"Элемент ID {item_id} успешно обновлен.")
    except Exception as e:
        logging.error(f"Ошибка при обновлении элемента ID {item_id}: {e}")
        flash('Произошла ошибка при обновлении элемента. Попробуйте еще раз.', 'danger')
        db.session.rollback()
        return redirect(url_for('edit_item', item_id=item_id))

    return redirect(url_for('admin_panel'))


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/reservation_success')
def success():
    user_email = request.args.get('user_email', "rabotabota24@mail.ru")
    logging.info(f"Пользователь с email {user_email} успешно завершил бронь.")
    return render_template('reservation_success.html', user_email=user_email)

@app.route('/reserve/<int:item_id>', methods=['GET', 'POST'])
def reserve(item_id):
    item = get_item_by_id(item_id)
    today_date = datetime.now().date()
    max_date = today_date + timedelta(days=30)

    if request.method == 'POST':
        user_name = request.form.get('user_name')
        user_surname = request.form.get('user_surname')
        reservation_type = request.form.get('reservation_type')
        user_phone = request.form.get('user_phone')

        # Валидация телефона
        if not validate_phone(user_phone):
            flash('Некорректный номер телефона. Пожалуйста, введите корректный номер.', 'danger')
            return redirect(url_for('reserve', item_id=item_id))

        
        if reservation_type == 'single_day':
            reservation_date = request.form.get('reservation_date')
            logging.info(f"Бронирование на один день для {user_name} {user_surname} на {reservation_date}.")
        else:  
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            logging.info(f"Бронирование на интервал для {user_name} {user_surname} с {start_date} по {end_date}.")

        return redirect(url_for('success', user_email="rabotabota24@mail.ru"))

    return render_template('reserve.html', item=item, today_date=today_date, max_date=max_date)

def validate_phone(phone):
    
    return len(phone) >= 10 and phone.isdigit()

@app.route('/confirm_reservation', methods=['POST'])
def confirm_reservation():
    item_id = request.form['item_id']
    reservation_date_str = request.form['reservation_date']
    user_email = request.form.get('user_email', "rabotabota24@mail.ru")

    try:
        reservation_date = datetime.strptime(reservation_date_str, '%Y-%m-%d').date()
        item = Item.query.get_or_404(item_id)

        
        today_date = datetime.now().date()
        max_date = today_date + timedelta(days=30)

        if reservation_date < today_date or reservation_date > max_date:
            flash(f'Дата бронирования должна быть между {today_date} и {max_date}.', 'danger')
            return redirect(url_for('reserve', item_id=item_id))

       
        item.status = 'reserved'
        item.return_date = reservation_date
        db.session.commit()

        logging.info(f"Предмет ID {item_id} успешно забронирован до {reservation_date}.")

        return redirect(url_for('reservation_success', user_email=user_email))

    except ValueError:
        flash('Некорректная дата. Попробуйте снова.', 'danger')
        logging.warning("Пользователь ввел некорректную дату.")
        return redirect(url_for('reserve', item_id=item_id))

    except Exception as e:
        logging.error(f"Ошибка при подтверждении бронирования: {e}")
        flash('Произошла ошибка при подтверждении бронирования. Попробуйте еще раз.', 'danger')
        return redirect(url_for('reserve', item_id=item_id))



@app.route('/items/<string:category>')
def items_by_category(category):
    try:
        
        items = Item.query.filter_by(category=category).all()
        logging.info(f"Получено {len(items)} предметов категории '{category}'.")

       
        if not items:
            flash(f'Предметы категории "{category}" не найдены.', 'warning')

        return render_template('items.html', items=items)

    except Exception as e:
        logging.error(f"Ошибка при получении предметов категории '{category}': {e}")
        flash('Произошла ошибка при загрузке предметов. Попробуйте снова.', 'danger')
        return render_template('items.html', items=[])


@app.route('/clothing')
def clothing():
    return items_by_category('clothing')  # Используйте английские названия

@app.route('/accessories')
def accessories():
    return items_by_category('accessories')

@app.route('/footwear')
def footwear():
    return items_by_category('shoes')

@app.route('/headwear')
def headwear():
    return items_by_category('headwear')

@app.route('/complete_outfit')
def complete_outfit():
    return items_by_category('ready_to_wear')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            logging.warning("Неудачная попытка доступа без входа.")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def handle_error(e, redirect_url, message):
    logging.error(message)
    flash('Произошла ошибка. Попробуйте снова.', 'danger')
    return redirect(redirect_url)

@app.route('/profile')
def profile():
    try:
        user = User.query.first_or_404()  # Используем first_or_404 для обработки отсутствия пользователя

        rentals = Rental.query.filter_by(user_id=user.id).all()
        logging.info(f"Найдены {len(rentals)} записи(ей) истории аренды для пользователя {user.id}.")
        return render_template('profile.html', user=user, rentals=rentals)

    except Exception as e:
        return handle_error(e, 'index', f"Ошибка при получении профиля пользователя: {e}")



@app.route('/admin', methods=['GET'])
@admin_required
def admin_panel():
    category = request.args.get('category')
    try:
        if category:
            items = Item.query.filter_by(category=category).all()
            logging.info(f"Загружены предметы для категории: {
                         category}, количество: {len(items)}.")
        else:
            items = Item.query.all()
            logging.info(f"Загружены все предметы, количество: {len(items)}.")
        return render_template('admin_panel.html', items=items)

    except Exception as e:
        return handle_error(e, 'admin_panel', f"Ошибка при загрузке панели администратора: {e}")


@app.route('/admin/add_item', methods=['POST'])
@admin_required
def add_item():
    
    name = request.form['name']
    size = request.form['size']
    color = request.form['color']
    description = request.form.get('description', '')
    category = request.form['category']
    price = request.form['price']
    status = request.form['status']
    image = request.files.get('image')
    filename = image.filename if image else None

    if not all([name, size, color, category, price, status]):
        flash('Пожалуйста, заполните все обязательные поля.', 'danger')
        logging.warning("Пользователь не заполнил обязательные поля.")
        return redirect(url_for('admin_panel'))

    try:
        price = float(price)
    except ValueError:
        flash('Некорректная цена. Пожалуйста, введите числовое значение.', 'danger')
        logging.warning("Пользователь ввел некорректную цену.")
        return redirect(url_for('admin_panel'))

    if image and filename:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(file_path)

    new_item = Item(
        name=name, size=size, color=color, description=description,
        category=category, price=price, status=status, image=filename
    )
    db.session.add(new_item)
    db.session.commit()
    logging.info(f"Предмет '{name}' успешно добавлен администратором.")

    return redirect(url_for('admin_panel'))


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            logging.warning("Неудачная попытка доступа без входа.")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


def handle_error(e, redirect_url, message):
    logging.error(message)
    flash('Произошла ошибка. Попробуйте снова.', 'danger')
    return redirect(redirect_url)


@app.route('/admin/delete_item/<int:item_id>', methods=['POST'])
@admin_required
def delete_item(item_id):
    try:
        item = Item.query.get_or_404(item_id)
        db.session.delete(item)
        db.session.commit()
        logging.info(f"Предмет ID {item_id} успешно удален администратором.")
        flash('Предмет успешно удален.', 'success')
    except Exception as e:
        return handle_error(e, 'admin_panel', f"Ошибка при удалении предмета ID {item_id}.")

    return redirect(url_for('admin_panel'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')

        if check_password_hash(admin_password_hash, password):
            session['admin_logged_in'] = True
            flash('Вы успешно вошли в систему.', 'success')
            logging.info("Администратор вошел в систему.")
            return redirect(url_for('admin_panel'))
        else:
            flash('Неверный пароль. Попробуйте снова.', 'danger')
            logging.warning(
                "Неудачная попытка входа администратора: неверный пароль.")

    return render_template('admin_login.html')


@app.route('/item/<int:item_id>')
def item_detail(item_id):
    item = get_item_by_id(item_id)

    if item is None:
        flash('Предмет не найден.', 'danger')
        logging.warning(
            f"Попытка доступа к несуществующему предмету с ID {item_id}.")
        return redirect(url_for('items'))

    logging.info(f"Детали предмета с ID {item_id} были успешно загружены.")
    return render_template('item_detail.html', item=item)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    logging.info("Администратор вышел из системы.")
    flash('Вы успешно вышли из системы.', 'success')
    return redirect(url_for('admin_login'))


async def process_webhook(update: Update) -> None:
    try:
        await application.process_update(update)
    except Exception as e:
        logging.error(f"Ошибка при обработке обновления: {e}")
        logging.info("Обновление обработано.")


@app.route('/webhook', methods=['POST'])
async def webhook():
    update = request.get_json()
    logging.info(f"Webhook вызван: {update}")

    
    await application.process_update(Update.de_json(update, application.bot))
    return 'OK'


def set_webhook():
    url = "https://smoothly-fun-cicada.ngrok-free.app/webhook"
    try:
        response = requests.post(
            f'https://api.telegram.org/bot{TOKEN_TELEGRAM}/setWebhook',
            json={'url': url}
        )
        response.raise_for_status()
        logging.info(f'Set webhook response: {response.json()}')
    except requests.RequestException as e:
        logging.error(f'Ошибка установки webhook: {e}')
        if e.response is not None:
            logging.error(f'Response content: {e.response.content}')
        else:
            logging.error("Не удалось получить ответ от сервера Telegram.")


AUTHORIZED_USERS = {701768868}


def is_authorized_user(user_id):
    return user_id in AUTHORIZED_USERS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.message.reply_text("Привет! Перейдите на нашу стартовую страницу: {url}")
    except Exception as e:
        logging.error(f"Error while replying to message: {e}")
    logging.info("Команда /start получена.")
    user_id = update.message.from_user.id
    logging.info(f"User ID {user_id} initiated /start command.")

    if not is_authorized_user(user_id):
        await update.message.reply_text("У вас нет прав для использования этого бота.")
        logging.warning(f"Unauthorized access attempt by User ID {user_id}.")
        return

    url = f"{NGROK_URL}/"
    await update.message.reply_text(f"Привет! Перейдите на нашу стартовую страницу: {url}")
    logging.info(f"Response sent to User ID {
                 user_id}: Привет! Перейдите на нашу стартовую страницу: {url}")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logging.info(f"Received /admin command from user ID: {user_id}")

    if user_id == ADMIN_ID:
        await update.message.reply_text("Вы вошли в панель администратора.")
        logging.info(f"User ID {user_id} granted access to admin panel.")
    else:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        logging.warning(f"Unauthorized access attempt by User ID: {
                        user_id} for /admin command.")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    logging.info(f"Received /stop command from user ID: {user_id}")

    if user_id == ADMIN_ID:
        await update.message.reply_text("Останавливаю сервер и бота...")
        shutdown_server()
    else:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        logging.warning(f"Unauthorized access attempt by User ID: {
                        user_id} for /stop command.")


def shutdown_server():
    func = request.environ.get('werkzeug.server.shutdown')
    if func:
        func()
        logging.info("Сервер успешно остановлен.")
    else:
        logging.error("Ошибка: сервер не использует Werkzeug.")


async def bot_main() -> None:
    global application
    application = ApplicationBuilder().token(TOKEN_TELEGRAM).build()

    application.add_handler(CommandHandler("start", start))

    await application.initialize()
    await application.bot.set_webhook(f"{NGROK_URL}/webhook")
    logging.info("Webhook установлен.")

    await application.start()
    logging.info("Бот запущен и ждет обновлений.")

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logging.info("Остановка бота...")
        await application.stop()
        logging.info("Бот успешно остановлен.")


def run_bot():
    asyncio.run(bot_main())


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  
    set_webhook()

    flask_thread = threading.Thread(target=lambda: app.run(
        debug=True, host='0.0.0.0', port=8080, use_reloader=False))
    flask_thread.start()

    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    flask_thread.join()
    bot_thread.join()
    asyncio.run(bot_main())
    app.run(port=8080)
