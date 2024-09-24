from app import app, db, Item  # Импортируйте ваше приложение и модели

# Создайте контекст приложения
with app.app_context():
    # Ваш код здесь
    items = Item.query.all()
    for item in items:
        print(item.id, item.name, item.category)
