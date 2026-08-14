import uuid
import jwt
from datetime import datetime, timedelta
from app.config import settings
from app.database import SessionLocal
from app.models import User, UserSettings

def generate_magic_link(user_id: int, telegram_id: int) -> str:
    """Генерирует одноразовый JWT токен и Magic Link для авторизации в веб-версии (TTL 15 минут)."""
    jti = uuid.uuid4().hex
    payload = {
        "user_id": user_id,
        "telegram_id": telegram_id,
        "jti": jti,
        "type": "magic_link",
        "exp": datetime.utcnow() + timedelta(minutes=15)  # Токен активен 15 минут
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    # Используем базовый адрес фронтенда из настроек
    base_url = settings.FRONTEND_URL.rstrip('/')
    return f"{base_url}/auth?token={token}"


def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> User:
    """Получает пользователя из базы данных или создает нового, если его нет."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Создаем также пустые настройки по умолчанию
            user_settings = UserSettings(
                user_id=user.id,
                columns={
                    "key_candidates": ["Артикул", "Код", "SKU", "ID", "Код товара"],
                    "name_candidates": ["Препарат", "Наименование", "Наименование препарата", "Наименование товаров", "Наименование товара", "Наименование препаратов", "Наименование медикаментов", "Товары", "Махсулот номи", "Номенклатура", "Товар", "Название", "Name", "Позиция"],
                    "price_candidates": ["Цена отпускная под 100%", "Цена", "Цена руб", "Цена с НДС", "Цена (100%) с НДС", "Цена При 100 % оплате цена", "При 100 % оплате цена", "Тип цены Сотув", "Цена 100%", "Цена с НДС 100%", "Цена для клиента с предоплатой 100%", "Цена без НДС", "Цена отпускная под 25%", "Цена Спец мин 1млн", "Тип цены При 100% Оплате (перечисление)", "При 100% Оплате", "Цена договорная", "Цена (с НДС)", "Цена Договорная", "Цена переч", "Цена переч:", "Цена реал", "ПриходЦена", "Сумма заказ", "Сумма", "Отп. Цена", "Price", "Нарх", "Розница", "Опт", "Стоимость", "Тариф"],
                    "stock_candidates": ["Остаток", "Количество", "Склад", "Доступно", "Кол-во"],
                    "producer_candidates": ["Производитель", "Бренд", "Завод", "Фирма"]
                },
                producers=["материа", "materia"],
                use_catalog_matching=False,
                legacy_priority_rules=False,
                clear_inputs_after_processing=True
            )
            db.add(user_settings)
            db.commit()
            db.refresh(user)
            
        db.expunge(user)
        return user
    finally:
        db.close()
