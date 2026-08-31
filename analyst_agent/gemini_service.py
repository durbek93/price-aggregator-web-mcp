# -*- coding: utf-8 -*-
import json
import logging
import re
import asyncio
from typing import Optional
import google.generativeai as genai

import config

logger = logging.getLogger("analyst_agent.gemini_service")

# Configure Gemini
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)
else:
    logger.error("GEMINI_API_KEY is not configured! Gemini API calls will fail.")


def sanitize_telegram_html(text: str) -> str:
    """Очищает HTML-текст от неподдерживаемых Telegram тегов."""
    text = text.strip()
    
    # 1. Удаление markdown code block wrapper (например ```html ... ```)
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    # 2. Замена заголовков h1-h6 на жирный текст
    text = re.sub(r'<h[1-6][^>]*>', '<b>', text, flags=re.IGNORECASE)
    text = re.sub(r'</h[1-6]>', '</b>\n', text, flags=re.IGNORECASE)
    
    # 3. Замена br, p, div, span, ul, ol, li
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?ul[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?ol[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?div[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?span[^>]*>', '', text, flags=re.IGNORECASE)
    
    # Замена неразрывных пробелов
    text = text.replace('&nbsp;', ' ')
    
    # 4. Убираем избыточные переводы строк (> 2 подряд)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


async def generate_ai_report(analysis_data: dict, include_deficit: bool = True) -> str:
    """Генерирует текст аналитического отчета через Gemini 2.5 Flash."""
    if include_deficit:
        blocks_section = (
            "5. Отчет должен быть строго разделен на три блока:\n"
            "   - 🏆 Лидеры недели (Минимальные цены): В этом блоке должны выводиться ТОЛЬКО 4 препарата: Анаферон Детский, Анаферон Детский капли, Эргоферон и Ренгалин. Для каждого из этих 4 препаратов выведи ТОЛЬКО 1 предложение с самой дешевой ценой (1 дистрибьютор и его минимальная цена). Не выводи топ-3, выводи только одного абсолютного лидера по цене.\n"
            "   - 📈 Изменение цен (Динамика): Описание подорожавших/подешевевших позиций по конкретным дистрибьюторам.\n"
            "   - 🚨 Дефицит / Важные изменения: Чётко перечисли позиции, которые отсутствуют в наличии у конкретных дистрибьюторов (на основе полей deficit_details и missing_suppliers в JSON), а также вымывшиеся из прошлых прайсов позиции.\n"
        )
    else:
        blocks_section = (
            "5. Отчет должен быть строго разделен на два блока:\n"
            "   - 🏆 Лидеры недели (Минимальные цены): В этом блоке должны выводиться ТОЛЬКО 4 препарата: Анаферон Детский, Анаферон Детский капли, Эргоферон и Ренгалин. Для каждого из этих 4 препаратов выведи ТОЛЬКО 1 предложение с самой дешевой ценой (1 дистрибьютор и его минимальная цена). Не выводи топ-3, выводи только одного абсолютного лидера по цене.\n"
            "   - 📈 Изменение цен (Динамика): Описание подорожавших/подешевевших позиций по конкретным дистрибьюторам.\n"
            "   КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО добавлять блок о дефиците, пропавших или вымывшихся позициях.\n"
        )

    system_instruction = (
        "Ты — опытный коммерческий директор и аналитик фармацевтического рынка Узбекистана. "
        "Твоя цель — превратить сухой JSON-отчет сравнения цен в структурированный, легко читаемый бизнес-отчет для Telegram-канала продаж.\n\n"
        "Правила оформления:\n"
        "1. Используй ТОЛЬКО разрешенные теги Telegram HTML: <b> (или <strong>), <i> (или <em>), <u>, <s> (или <strike>, <del>), <code>, <pre>, <a>. Другие теги запрещены.\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать теги абзацев <p>, переноса строки <br>, заголовков <h1>, <h2>, <h3>, блоков <div>, а также теги списков <ul>, <ol>, <li>. Вместо этого разделяй абзацы обычными переводами строк (\\n), а списки оформляй с помощью эмодзи или дефисов в начале строки.\n"
        "3. Категорически запрещено использовать Markdown (символы * или _).\n"
        "4. Добавляй смысловые эмодзи (📈 — рост цены, 📉 — падение, 🚨 — критические изменения или дефицит, 🏆 — лучшая цена).\n"
        + blocks_section +
        "6. Ограничивай свой анализ ТОЛЬКО препаратами компании «Материа Медика» (Анаферон Детский, Анаферон Детский капли, Эргоферон, Ренгалин, указанными в JSON).\n"
        "7. Пиши отчет лаконично, структурированно, профессионально и на русском языке."
    )
    
    user_prompt = (
        f"Проанализируй следующие данные о ценах на препараты:\n\n"
        f"{json.dumps(analysis_data, ensure_ascii=False, indent=2)}"
    )
    
    logger.info(f"Calling Gemini ({config.GEMINI_MODEL}) API...")
    loop = asyncio.get_running_loop()
    
    def _call_gemini():
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=system_instruction
        )
        response = model.generate_content(
            user_prompt,
            generation_config={"temperature": 0.2}
        )
        return response.text
        
    raw_report = await loop.run_in_executor(None, _call_gemini)
    return sanitize_telegram_html(raw_report)


async def classify_user_request(text: str) -> dict:
    """Определяет интент пользователя (анализ производителя, препарата, статус БД, графики, презентации или общий Q&A) с помощью Gemini."""
    text_low = text.lower()

    chart_keywords = ["график", "графики", "диаграмму", "диаграмма", "рисуй", "нарисуй", "построй", "визуализ", "chart"]
    pres_keywords = ["презентац", "презентацию", "слайд", "pptx", "powerpoint", "пауэрпоинт"]

    wants_chart = any(kw in text_low for kw in chart_keywords)
    wants_presentation = any(kw in text_low for kw in pres_keywords)

    # Быстрая детерминированная проверка для вопросов о продажах
    sales_keywords = [
        "отчет по продажам", "отчёт по продажам", "анализ продаж", "аналитика продаж",
        "сколько продали", "продажи по дистрибьюторам", "динамика продаж", "объем продаж",
        "продажи", "sales", "папка sales", "папке sales", "файлы sales", "отчеты продаж"
    ]
    if any(kw in text_low for kw in sales_keywords) or ((wants_chart or wants_presentation) and "цен" not in text_low):
        logger.info("Fast classification match: sales")
        return {
            "request_type": "sales",
            "target": None,
            "days": 30,
            "wants_chart": wants_chart,
            "wants_presentation": wants_presentation
        }

    # Быстрая детерминированная проверка для скачивания прайсов
    fetch_keywords = ["/fetch", "/download_prices", "скачай прайсы", "скачай последние прайсы", "загрузи прайсы", "скачать прайсы"]
    if any(kw in text_low for kw in fetch_keywords):
        logger.info("Fast classification match: fetch_prices")
        return {
            "request_type": "fetch_prices",
            "target": None,
            "days": 3,
            "wants_chart": False,
            "wants_presentation": False
        }

    # Быстрая детерминированная проверка для очистки памяти
    purge_keywords = ["/clean", "/purge", "очисти память", "очистить память", "удали прайсы за"]
    if any(kw in text_low for kw in purge_keywords):
        logger.info("Fast classification match: purge_memory")
        return {
            "request_type": "purge_memory",
            "target": None,
            "days": 3,
            "wants_chart": False,
            "wants_presentation": False
        }

    # Быстрая детерминированная проверка для вопросов о наличии файлов/прайсов/БД
    db_keywords = [
        "какие прайсы", "какие файлы", "доступны в бд", "доступны для анализа",
        "список файлов", "список прайсов", "что загружено", "состояние бд",
        "доступные прайсы", "файлы в базе", "прайсы в базе"
    ]
    if any(kw in text_low for kw in db_keywords):
        logger.info("Fast classification match: database_info")
        return {
            "request_type": "database_info",
            "target": None,
            "days": 3,
            "wants_chart": wants_chart,
            "wants_presentation": wants_presentation
        }

    system_instruction = (
        "Ты — аналитический классификатор запросов для фармацевтического бота.\n"
        "Определи, какой именно тип ответа или анализа запрашивает пользователь:\n"
        "1. Анализ по производителю (например, 'анализ цен КРКА', 'что изменилось у Материа Медика за 3 дня') -> request_type: 'manufacturer'\n"
        "2. Анализ по конкретному препарату (например, 'анализ цен по препарату Виферон 150', 'какие цены на Анаферон капли за последние 2 дня') -> request_type: 'drug'\n"
        "3. Вопрос о содержимом БД/файлов (например, 'какие сводные прайс листы доступны в БД', 'покажи список файлов', 'сколько прайсов загружено') -> request_type: 'database_info'\n"
        "4. Отчет по ПРОДАЖАМ (например, 'анализ продаж', 'отчет по продажам', 'сколько продали в упаковках') -> request_type: 'sales'\n"
        "5. Команда скачивания прайсов (например, 'скачай последние прайсы с ТГ каналов', '/fetch') -> request_type: 'fetch_prices'\n"
        "6. Команда очистки памяти (например, 'очисти память за май и июнь 2026', '/clean 05.2026') -> request_type: 'purge_memory'\n"
        "7. Общий вопрос / диалог / справка (например, 'привет', 'что ты умеешь', 'как пользоваться') -> request_type: 'general_qa'\n"
        "8. Общий отчет по сводному прайсу (например, 'сводный прайс собран', 'сделай общий анализ', 'покажи изменения') -> request_type: 'standard'\n\n"
        "Ответ должен быть СТРОГО в формате JSON с полями:\n"
        "- 'request_type': строка, одна из: 'manufacturer', 'drug', 'database_info', 'sales', 'fetch_prices', 'purge_memory', 'general_qa', 'standard'\n"
        "- 'target': строка с названием производителя или препарата или null, если не применимо.\n"
        "- 'days': целое число дней (если указано в запросе, например 'за 2 дня' -> 2; по умолчанию 3 если не указано).\n"
        "- 'date1': первая дата из запроса в формате 'ДД.ММ.ГГГГ' (например '29.06.2026') или null.\n"
        "- 'date2': вторая дата из запроса в формате 'ДД.ММ.ГГГГ' (например '25.07.2026') или null.\n"
        "Не добавляй никаких пояснений, только валидный JSON."
    )
    
    logger.info(f"Classifying user request via Gemini ({config.GEMINI_MODEL})...")
    loop = asyncio.get_running_loop()
    
    def _call_gemini():
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=system_instruction
        )
        response = model.generate_content(
            f"Запрос пользователя: '{text}'",
            generation_config={"temperature": 0.0, "response_mime_type": "application/json"}
        )
        return response.text

    try:
        raw_response = await loop.run_in_executor(None, _call_gemini)
        res = json.loads(raw_response)
        # Автодополнение дат через регулярное выражение, если не распаршено
        if not res.get("date1") or not res.get("date2"):
            dates = re.findall(r'\b\d{2}\.\d{2}\.\d{4}\b', text)
            if len(dates) >= 2:
                res["date1"] = dates[0]
                res["date2"] = dates[1]
        res["wants_chart"] = wants_chart
        res["wants_presentation"] = wants_presentation
        return res
    except Exception as e:
        logger.exception(f"Error during classification: {e}")
        dates = re.findall(r'\b\d{2}\.\d{2}\.\d{4}\b', text)
        date1 = dates[0] if len(dates) >= 1 else None
        date2 = dates[1] if len(dates) >= 2 else None
        return {"request_type": "standard", "target": None, "days": 3, "date1": date1, "date2": date2}


async def generate_manufacturer_report(analysis_data: dict, manufacturer: str, days: int) -> str:
    """Генерирует аналитический отчет по конкретному производителю за последние N дней."""
    system_instruction = (
        "Ты — опытный коммерческий директор и аналитик фармацевтического рынка Узбекистана.\n"
        f"Твоя задача — составить подробный и структурированный бизнес-отчет по изменению цен на препараты производителя «{manufacturer}» за последние {days} дня.\n\n"
        "Правила оформления отчета:\n"
        "1. Используй ТОЛЬКО разрешенные теги Telegram HTML: <b> (или <strong>), <i> (или <em>), <u>, <s> (или <strike>, <del>), <code>, <pre>, <a>. Другие теги запрещены.\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать теги абзацев <p>, переноса строки <br>, заголовков <h1>, <h2>, <h3>, блоков <div>, а также теги списков <ul>, <ol>, <li>. Вместо этого разделяй абзацы обычными переводами строк (\\n), а списки оформляй с помощью эмодзи или дефисов в начале строки.\n"
        "3. Категорически запрещено использовать Markdown (символы * или _).\n"
        "4. Добавляй смысловые эмодзи.\n"
        "5. Отчет должен быть строго разделен на три блока:\n"
        "   - 🏆 Лидеры по ценам: Для каждого препарата покажи дистрибьютора с минимальной текущей ценой.\n"
        "   - 📈 Изменение цен (Динамика): Опиши препараты, у которых изменились цены за эти дни (какой дистрибьютор поднял или опустил цену, на сколько процентов/сум).\n"
        "   - 🚨 Изменения в ассортименте (Новинки / Дефицит): Укажи, какие препараты появились (новинки) или пропали (дефицит) у конкретных дистрибьюторов.\n"
        "6. Пиши отчет лаконично, структурированно, профессионально и на русском языке."
    )
    
    user_prompt = (
        f"Проанализируй следующие исторические данные по ценам производителя {manufacturer} за {days} дня:\n\n"
        f"{json.dumps(analysis_data, ensure_ascii=False, indent=2)}"
    )
    
    logger.info(f"Calling Gemini ({config.GEMINI_MODEL}) for manufacturer report...")
    loop = asyncio.get_running_loop()
    
    def _call_gemini():
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=system_instruction
        )
        response = model.generate_content(
            user_prompt,
            generation_config={"temperature": 0.2}
        )
        return response.text
        
    raw_report = await loop.run_in_executor(None, _call_gemini)
    return sanitize_telegram_html(raw_report)


async def generate_drug_report(analysis_data: dict, drug: str, days: int) -> str:
    """Генерирует аналитический отчет по конкретному препарату за последние N дней."""
    system_instruction = (
        "Ты — опытный коммерческий директор и аналитик фармацевтического рынка Узбекистана.\n"
        f"Твоя задача — составить подробный и структурированный отчет по изменению цен на препарат(ы), соответствующие запросу «{drug}», за последние {days} дня.\n\n"
        "Правила оформления отчета:\n"
        "1. Используй ТОЛЬКО разрешенные теги Telegram HTML: <b> (или <strong>), <i> (или <em>), <u>, <s> (или <strike>, <del>), <code>, <pre>, <a>. Другие теги запрещены.\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать теги абзацев <p>, переноса строки <br>, заголовков <h1>, <h2>, <h3>, блоков <div>, а также теги списков <ul>, <ol>, <li>. Вместо этого разделяй абзацы обычными переводами строк (\\n), а списки оформляй с помощью эмодзи или дефисов в начале строки.\n"
        "3. Категорически запрещено использовать Markdown (символы * или _).\n"
        "4. Добавляй смысловые эмодзи.\n"
        "5. Отчет должен быть структурированным и содержать:\n"
        "   - Сводку по лучшим текущим ценам на рынке с указанием дистрибьюторов.\n"
        "   - Анализ динамики изменения цен у каждого дистрибьютора за последние 2-3 дня.\n"
        "   - Информация о наличии (появился ли препарат у кого-то из дистрибьюторов или, наоборот, пропал).\n"
        "6. Пиши отчет лаконично, структурированно, профессионально и на русском языке."
    )
    
    user_prompt = (
        f"Проанализируй следующие исторические данные по ценам для препарата {drug} за {days} дня:\n\n"
        f"{json.dumps(analysis_data, ensure_ascii=False, indent=2)}"
    )
    
    logger.info(f"Calling Gemini ({config.GEMINI_MODEL}) for drug report...")
    loop = asyncio.get_running_loop()
    
    def _call_gemini():
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=system_instruction
        )
        response = model.generate_content(
            user_prompt,
            generation_config={"temperature": 0.2}
        )
        return response.text
        
    raw_report = await loop.run_in_executor(None, _call_gemini)
    return sanitize_telegram_html(raw_report)


async def generate_general_qa_report(user_query: str, system_summary: Optional[dict] = None) -> str:
    """Генерирует ответ на свободный вопрос пользователя или вопрос о состоянии БД."""
    system_instruction = (
        "Ты — умный и вежливый ИИ-Ассистент и Аналитик фармацевтического агрегатора цен в Узбекистане.\n"
        "Твоя задача — отвечать на вопросы пользователя понятным, профессиональным и структурированным языком.\n"
        "Обрати внимание: отчеты по ПРОДАЖАМ в папке 'sales' (все 12 месяцев 2025 года) ДОСТУПНЫ в системе и готовы для анализа по первому запросу пользователя.\n\n"
        "Правила оформления отчета:\n"
        "1. Используй ТОЛЬКО разрешенные теги Telegram HTML: <b> (или <strong>), <i> (или <em>), <u>, <s>, <code>, <pre>, <a>.\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать теги абзацев <p>, переноса строки <br>, заголовков <h1>-<h6>, блоков <div>, списков <ul>, <ol>, <li>. Разделяй абзацы обычными переводами строк (\\n), а списки оформляй эмодзи или дефисами.\n"
        "3. Категорически запрещено использовать Markdown (символы * или _).\n"
        "4. Пиши вежливо, точно и лаконично."
    )
    
    summary_text = ""
    if system_summary:
        summary_text = f"\n\nТекущее состояние базы данных и файлов:\n{json.dumps(system_summary, ensure_ascii=False, indent=2)}"
        
    user_prompt = f"Вопрос пользователя: '{user_query}'{summary_text}"
    
    logger.info(f"Calling Gemini ({config.GEMINI_MODEL}) for general QA/DB info response...")
    loop = asyncio.get_running_loop()
    
    def _call_gemini():
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=system_instruction
        )
        response = model.generate_content(
            user_prompt,
            generation_config={"temperature": 0.3}
        )
        return response.text
        
    raw_report = await loop.run_in_executor(None, _call_gemini)
    return sanitize_telegram_html(raw_report)


async def generate_sales_report(analysis_data: dict, user_query: str = "") -> str:
    """Генерирует ответ или аналитический отчет по Реализации и Остаткам (упаковки) по региону г. Фергана."""
    city_name = analysis_data.get("meta", {}).get("city", "г. Фергана")
    system_instruction = (
        f"Ты — Коммерческий директор и Ведущий аналитик фармацевтической компании в Узбекистане.\n"
        f"У тебя есть полные помесячные агрегированные данные по **Реализации (проданным упаковкам)** "
        f"и **Остаткам** по каждому препарату в регионе <b>{city_name}</b> за 2025 год (поля `by_month` и `by_product`).\n\n"
        "ПРАВИЛА ОБРАБОТКИ ЗАПРОСОВ ПОЛЬЗОВАТЕЛЯ:\n"
        "1. **Запрос отчета за конкретный месяц** (например: 'отчёт продаж за декабрь 2025 по всем препаратам'):\n"
        "   -> Найди в данных соответствующий месяц в `by_month` (например, 'Декабрь 2025').\n"
        "   -> Выведи отчёт ПО КАЖДОМУ ПРЕПАРАТУ отдельно за этот месяц: Реализация (упаковок) и Остаток на конец месяца.\n"
        "   -> Выведи общий итог реализации и остатка за этот месяц.\n\n"
        "2. **Запрос сравнения двух периодов** (например: 'сравни продажи за ноябрь 2025 и декабрь 2025'):\n"
        "   -> Возьми данные по обоим месяцам из `by_month`.\n"
        "   -> Проведи детальное сравнение ПО КАЖДОМУ ПРЕПАРАТУ: покажи продажи за Месяц1, продажи за Месяц2, прирост/падение в упаковках (+/-) и в процентах (%), а также динамику остатков.\n"
        "   -> Сделай краткие аналитические выводы: какие препараты показали наибольший рост, а какие просели.\n\n"
        "3. **Конкретный точечный вопрос** (например: 'какие данные есть в папке sales?', 'сколько продали Анаферона детского в октябре?'):\n"
        "   -> Ответь ЧЕТКО, ТОЧНО И ЛАКОНИЧНО ИМЕННО НА ЭТОТ ВОПРОС. Не генерируй гигантский шаблонизированный отчет со всеми блоками.\n\n"
        "4. **Общий / развернутый отчет по продажам** (например: 'сделай полный отчет по продажам', 'аналитика за весь 2025 год'):\n"
        "   -> Выведи годовые сводные итоги по региону, топ препаратов, динамику и рейтинг поставщиков.\n\n"
        "Правила оформления отчета:\n"
        "1. Используй ТОЛЬКО разрешенные теги Telegram HTML: <b>, <i>, <u>, <s>, <code>, <pre>, <a>.\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать теги абзацев <p>, переноса строки <br>, заголовков <h1>-<h6>, блоков <div>, списков <ul>, <ol>, <li>. Разделяй абзацы обычными переводами строк (\\n), а списки оформляй эмодзи (например: 📊, 🏆, 💊, 📦, 📈, 📉).\n"
        "3. Категорически запрещено использовать Markdown (символы * или _).\n"
        "4. Опирайся СТРОГО на переданный JSON. Все данные по каждому месяцу и препарату находятся в объектах `by_month` и `by_product`. Не придумывай цифры!"
    )
    
    prompt_query_part = f"Запрос/Вопрос пользователя: '{user_query}'\n\n" if user_query else ""
    user_prompt = (
        f"{prompt_query_part}"
        f"Агрегированные данные по продажам в упаковках по региону {city_name}:\n\n"
        f"{json.dumps(analysis_data, ensure_ascii=False, indent=2)}"
    )
    
    logger.info(f"Calling Gemini ({config.GEMINI_MODEL}) for sales response (query: '{user_query[:50]}')...")
    loop = asyncio.get_running_loop()
    
    def _call_gemini():
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=system_instruction
        )
        response = model.generate_content(
            user_prompt,
            generation_config={"temperature": 0.2}
        )
        return response.text
        
    raw_report = await loop.run_in_executor(None, _call_gemini)
    return sanitize_telegram_html(raw_report)


async def generate_mcp_agentic_response(user_query: str) -> str:
    """
    Интеллектуальный агентский обработчик на базе Gemini Function Calling и MCP Tools.
    Gemini самостоятельно вызывает необходимые MCP-инструменты для получения актуальных данных.
    """
    try:
        from mcp_client import ANALYST_MCP_TOOLS
    except ImportError:
        from analyst_agent.mcp_client import ANALYST_MCP_TOOLS

    system_instruction = (
        "Ты — ведущий ИИ-Аналитик фармацевтического рынка Узбекистана. "
        "В твоём распоряжении есть набор инструментов MCP (Model Context Protocol) для получения данных о ценах, "
        "сравнении прайсов, истории препаратов, динамике производителей и отчетах о продажах.\n"
        "Когда пользователь задает вопрос, используй соответствующие инструменты (Tool Calling), чтобы получить "
        "точные факты и цифры, а затем дай структурированный и понятный ответ.\n\n"
        "Правила оформления ответа:\n"
        "1. Используй ТОЛЬКО разрешенные теги Telegram HTML: <b>, <i>, <u>, <s>, <code>, <pre>, <a>.\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать <p>, <br>, <h1>-<h6>, <div>, <ul>, <ol>, <li>.\n"
        "3. Категорически запрещено использовать Markdown (* или _).\n"
        "4. Форматируй списки с эмодзи или дефисами, разделяй абзацы обычным переносом строки (\\n)."
    )

    logger.info(f"Calling Gemini with MCP tools for query: '{user_query[:60]}'...")
    loop = asyncio.get_running_loop()

    def _call_gemini_with_tools():
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=system_instruction,
            tools=ANALYST_MCP_TOOLS
        )
        chat = model.start_chat(enable_automatic_function_calling=True)
        response = chat.send_message(user_query)
        return response.text

    raw_report = await loop.run_in_executor(None, _call_gemini_with_tools)
    return sanitize_telegram_html(raw_report)



