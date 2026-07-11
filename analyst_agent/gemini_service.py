# -*- coding: utf-8 -*-
import json
import logging
import re
import asyncio
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
            "   - 🚨 Дефицит / Важные изменения: Позиции, которые исчезли (вымылись) из прайса какого-то поставщика.\n"
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
    
    logger.info("Calling Gemini 2.5 Flash API...")
    loop = asyncio.get_running_loop()
    
    def _call_gemini():
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
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
    """Определяет интент пользователя (анализ производителя, препарата или общий) с помощью Gemini 2.5 Flash."""
    system_instruction = (
        "Ты — аналитический классификатор запросов для фармацевтического бота.\n"
        "Определи, какой именно тип анализа запрашивает пользователь:\n"
        "1. Анализ по производителю (например, 'анализ цен КРКА', 'что изменилось у Материа Медика за 3 дня')\n"
        "2. Анализ по конкретному препарату (например, 'анализ цен по препарату Виферон 150', 'какие цены на Анаферон капли за последние 2 дня')\n"
        "3. Общий отчет по сводному прайсу (например, 'сводный прайс собран', 'сделай общий анализ', 'покажи изменения')\n\n"
        "Ответ должен быть СТРОГО в формате JSON с полями:\n"
        "- 'request_type': строка, одна из: 'manufacturer', 'drug', 'standard'\n"
        "- 'target': строка с названием производителя или препарата (например, 'KRKA' или 'Виферон 150000') или null, если не применимо.\n"
        "- 'days': целое число дней (если указано в запросе, например 'за 2 дня' -> 2; по умолчанию 3 если не указано).\n"
        "Не добавляй никаких пояснений, только валидный JSON."
    )
    
    logger.info("Classifying user request via Gemini...")
    loop = asyncio.get_running_loop()
    
    def _call_gemini():
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_instruction
        )
        response = model.generate_content(
            f"Запрос пользователя: '{text}'",
            generation_config={"temperature": 0.0, "response_mime_type": "application/json"}
        )
        return response.text

    try:
        raw_response = await loop.run_in_executor(None, _call_gemini)
        return json.loads(raw_response)
    except Exception as e:
        logger.exception(f"Error during classification: {e}")
        return {"request_type": "standard", "target": None, "days": 3}


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
    
    logger.info("Calling Gemini 2.5 Flash for manufacturer report...")
    loop = asyncio.get_running_loop()
    
    def _call_gemini():
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
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
    
    logger.info("Calling Gemini 2.5 Flash for drug report...")
    loop = asyncio.get_running_loop()
    
    def _call_gemini():
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_instruction
        )
        response = model.generate_content(
            user_prompt,
            generation_config={"temperature": 0.2}
        )
        return response.text
        
    raw_report = await loop.run_in_executor(None, _call_gemini)
    return sanitize_telegram_html(raw_report)
