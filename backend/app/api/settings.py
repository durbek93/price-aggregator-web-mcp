# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserSettings
from app.schemas import UserSettingsSchema
from app.api.dependencies import get_current_user
from app.defaults import DEFAULT_COLUMNS, DEFAULT_PRODUCERS

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("", response_model=UserSettingsSchema)
def get_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Возвращает настройки пользователя."""
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not user_settings:
        # Если настроек нет, создаем дефолтные
        user_settings = UserSettings(
            user_id=current_user.id,
            columns=DEFAULT_COLUMNS,
            producers=DEFAULT_PRODUCERS,
            use_catalog_matching=False,
            legacy_priority_rules=False,
            clear_inputs_after_processing=True
        )
        db.add(user_settings)
        db.commit()
        db.refresh(user_settings)
    else:
        # Самовосстановление (self-healing): добавляем новые стандартные кандидаты, если их нет
        modified = False
        user_cols = dict(user_settings.columns or {})
        for k, default_list in DEFAULT_COLUMNS.items():
            current_list = list(user_cols.get(k, []))
            added = False
            for cand in default_list:
                if cand not in current_list:
                    current_list.append(cand)
                    added = True
            if added:
                user_cols[k] = current_list
                modified = True
        if modified:
            user_settings.columns = user_cols
            db.commit()
            db.refresh(user_settings)
    return user_settings



@router.put("", response_model=UserSettingsSchema)
def update_settings(
    settings_data: UserSettingsSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Обновляет настройки пользователя."""
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not user_settings:
        user_settings = UserSettings(user_id=current_user.id)
        db.add(user_settings)
    
    user_settings.columns = settings_data.columns
    user_settings.producers = settings_data.producers
    user_settings.use_catalog_matching = settings_data.use_catalog_matching
    user_settings.legacy_priority_rules = settings_data.legacy_priority_rules
    user_settings.clear_inputs_after_processing = settings_data.clear_inputs_after_processing
    
    db.commit()
    db.refresh(user_settings)
    return user_settings
