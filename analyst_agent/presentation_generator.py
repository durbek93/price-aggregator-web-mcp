# -*- coding: utf-8 -*-
import io
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

import chart_generator

logger = logging.getLogger("analyst_agent.presentation_generator")

DARK_BG = RGBColor(18, 19, 28)        # #12131C
ACCENT_BLUE = RGBColor(78, 115, 223)   # #4E73DF
ACCENT_GREEN = RGBColor(28, 200, 138)  # #1CC88A
TEXT_WHITE = RGBColor(255, 255, 255)
TEXT_MUTED = RGBColor(160, 165, 186)   # #A0A5BA
CARD_BG = RGBColor(30, 31, 46)        # #1E1F2E

TARGET_DRUG_SLIDES = [
    {"display_name": "Анаферон детский (таблетки)", "keywords": ["детский 20", "детский таб", "детский"]},
    {"display_name": "Анаферон детский (капли)", "keywords": ["детский капли", "анаферон капли"]},
    {"display_name": "Анаферон взрослый", "keywords": ["анаферон взрослый", "анаферон 20", "анаферон таб"]},
    {"display_name": "Эргоферон", "keywords": ["эргоферон"]},
    {"display_name": "Ренгалин (таблетки)", "keywords": ["ренгалин 20", "ренгалин таб", "ренгалин"]},
    {"display_name": "Ренгалин (раствор)", "keywords": ["ренгалин раствор", "ренгалин фл", "ренгалин сироп"]},
    {"display_name": "Тенотен детский", "keywords": ["тенотен детский"]},
    {"display_name": "Тенотен взрослый", "keywords": ["тенотен взрослый", "тенотен"]},
]


def set_slide_background(slide):
    """Устанавливает темный фон для слайда."""
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = DARK_BG


def find_matching_product(by_product: Dict[str, Any], keywords: list) -> tuple:
    """Ищет препарат в словаре по ключевым словам."""
    for prod_name, prod_info in by_product.items():
        p_low = prod_name.lower()
        for kw in keywords:
            if kw in p_low:
                return prod_name, prod_info
    return None, None


def build_analytics_presentation(sales_data: Dict[str, Any], title: str = "Фармацевтический аналитический отчет") -> Optional[bytes]:
    """
    Генерирует расширенную PowerPoint (.pptx) презентацию с дашбордами, графиками,
    таблицами и отдельными слайдами по каждому целевому препарату.
    """
    try:
        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank_slide_layout = prs.slide_layouts[6]

        by_product = sales_data.get("by_product", {})

        # =========================================================================
        # 1. ТИТУЛЬНЫЙ СЛАЙД
        # =========================================================================
        slide1 = prs.slides.add_slide(blank_slide_layout)
        set_slide_background(slide1)

        txBox = slide1.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.333), Inches(2.5))
        tf = txBox.text_frame
        tf.word_wrap = True

        p = tf.paragraphs[0]
        p.text = "💊 Price Aggregator Analytics"
        p.font.size = Pt(22)
        p.font.bold = True
        p.font.color.rgb = ACCENT_GREEN

        p2 = tf.add_paragraph()
        p2.text = title
        p2.font.size = Pt(36)
        p2.font.bold = True
        p2.font.color.rgb = TEXT_WHITE

        p3 = tf.add_paragraph()
        city_name = sales_data.get("meta", {}).get("city", "Регион Узбекистан")
        total_files = sales_data.get("meta", {}).get("total_files", 0)
        p3.text = f"Детальный разбор препаратов | {city_name} | Загружено отчетов: {total_files}"
        p3.font.size = Pt(16)
        p3.font.color.rgb = TEXT_MUTED

        # =========================================================================
        # 2. СЛАЙД 2: КЛЮЧЕВЫЕ МЕТРИКИ РЫНКА (EXECUTIVE SUMMARY)
        # =========================================================================
        slide2 = prs.slides.add_slide(blank_slide_layout)
        set_slide_background(slide2)

        txBox2 = slide2.shapes.add_textbox(Inches(0.8), Inches(0.6), Inches(11.7), Inches(0.8))
        tf2 = txBox2.text_frame
        p = tf2.paragraphs[0]
        p.text = "📊 Ключевые показатели фармацевтического рынка"
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE

        summary = sales_data.get("summary", {})
        total_realization = summary.get("total_realization", 0)
        total_stock = summary.get("total_stock_latest", 0)
        dist_count = len(sales_data.get("by_distributor", {}))
        product_count = len(by_product)

        metrics = [
            ("Общая реализация (уп.)", f"{total_realization:,}".replace(',', ' '), ACCENT_BLUE),
            ("Текущие остатки (уп.)", f"{total_stock:,}".replace(',', ' '), ACCENT_GREEN),
            ("Активные дистрибьюторы", str(dist_count), RGBColor(54, 185, 204)),
            ("Всего позиций/препаратов", str(product_count), RGBColor(246, 194, 62)),
        ]

        card_width = Inches(2.7)
        card_height = Inches(2.2)
        top_pos = Inches(1.8)

        for idx, (label, val, color) in enumerate(metrics):
            left_pos = Inches(0.8 + idx * 3.0)
            shape = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left_pos, top_pos, card_width, card_height)
            shape.fill.solid()
            shape.fill.fore_color.rgb = CARD_BG
            shape.line.color.rgb = color
            shape.line.width = Pt(1.5)

            tf_card = shape.text_frame
            tf_card.word_wrap = True
            tf_card.margin_top = Inches(0.3)
            tf_card.margin_left = Inches(0.2)

            p_val = tf_card.paragraphs[0]
            p_val.text = val
            p_val.font.size = Pt(28)
            p_val.font.bold = True
            p_val.font.color.rgb = color

            p_lbl = tf_card.add_paragraph()
            p_lbl.text = label
            p_lbl.font.size = Pt(13)
            p_lbl.font.color.rgb = TEXT_MUTED

        # =========================================================================
        # 3. СЛАЙД 3: ОБЩИЕ ГРАФИКИ РЕАЛИЗАЦИИ И ДОЛЕЙ ПОСТАВЩИКОВ
        # =========================================================================
        slide3 = prs.slides.add_slide(blank_slide_layout)
        set_slide_background(slide3)

        txBox3 = slide3.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(0.8))
        tf3 = txBox3.text_frame
        p = tf3.paragraphs[0]
        p.text = "📈 Общая динамика реализации и доли поставщиков"
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE

        chart_bytes = chart_generator.generate_sales_chart(sales_data)
        if chart_bytes:
            image_stream = io.BytesIO(chart_bytes)
            slide3.shapes.add_picture(image_stream, Inches(0.8), Inches(1.5), width=Inches(11.7))

        # =========================================================================
        # 4-11. ИНДИВИДУАЛЬНЫЕ СЛАЙДЫ ПО КАЖДОМУ ЦЕЛЕВОМУ ПРЕПАРАТУ
        # =========================================================================
        for target_item in TARGET_DRUG_SLIDES:
            disp_name = target_item["display_name"]
            keywords = target_item["keywords"]

            prod_name, prod_info = find_matching_product(by_product, keywords)

            slide_p = prs.slides.add_slide(blank_slide_layout)
            set_slide_background(slide_p)

            # Slide Header
            txBox_p = slide_p.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.8))
            tf_p = txBox_p.text_frame
            p = tf_p.paragraphs[0]
            p.text = f"💊 Препарат: {disp_name}"
            p.font.size = Pt(24)
            p.font.bold = True
            p.font.color.rgb = TEXT_WHITE

            if prod_info:
                real_total = prod_info.get("realization_units_total_2025", 0)
                latest_stk = prod_info.get("latest_stock_units", 0)
                share_pct = prod_info.get("share_percent", 0)
                monthly_real = prod_info.get("monthly_realization", {})
                monthly_stk = prod_info.get("monthly_stock", {})

                # Metrics Row
                p_metrics = [
                    ("Реализация за 2025 (уп.)", f"{real_total:,}".replace(',', ' '), ACCENT_BLUE),
                    ("Текущий остаток (уп.)", f"{latest_stk:,}".replace(',', ' '), ACCENT_GREEN),
                    ("Доля рынка (%)", f"{share_pct} %", RGBColor(246, 194, 62)),
                ]

                for m_i, (lbl, val, col) in enumerate(p_metrics):
                    l_pos = Inches(0.8 + m_i * 3.9)
                    shape = slide_p.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, l_pos, Inches(1.3), Inches(3.6), Inches(1.1))
                    shape.fill.solid()
                    shape.fill.fore_color.rgb = CARD_BG
                    shape.line.color.rgb = col
                    shape.line.width = Pt(1.2)

                    tf_m = shape.text_frame
                    tf_m.margin_top = Inches(0.15)
                    tf_m.margin_left = Inches(0.2)

                    pv = tf_m.paragraphs[0]
                    pv.text = val
                    pv.font.size = Pt(20)
                    pv.font.bold = True
                    pv.font.color.rgb = col

                    pl = tf_m.add_paragraph()
                    pl.text = lbl
                    pl.font.size = Pt(11)
                    pl.font.color.rgb = TEXT_MUTED

                # Render Product Chart
                p_chart_bytes = chart_generator.generate_product_monthly_chart(disp_name, monthly_real, monthly_stk)
                if p_chart_bytes:
                    img_strm = io.BytesIO(p_chart_bytes)
                    slide_p.shapes.add_picture(img_strm, Inches(0.8), Inches(2.6), width=Inches(11.7))
            else:
                # Placeholder slide if drug not yet in input excel
                shape = slide_p.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.8), Inches(11.7), Inches(4.5))
                shape.fill.solid()
                shape.fill.fore_color.rgb = CARD_BG
                shape.line.color.rgb = ACCENT_BLUE

                tf_info = shape.text_frame
                tf_info.margin_top = Inches(1.5)
                p_msg = tf_info.paragraphs[0]
                p_msg.text = f"ℹ️ Данные по препарату «{disp_name}» обрабатываются..."
                p_msg.font.size = Pt(20)
                p_msg.font.bold = True
                p_msg.font.color.rgb = TEXT_WHITE
                p_msg.alignment = PP_ALIGN.CENTER

                p_sub = tf_info.add_paragraph()
                p_sub.text = "Позиция будет автоматически дозаполнена при поступлении отчетов продаж."
                p_sub.font.size = Pt(14)
                p_sub.font.color.rgb = TEXT_MUTED
                p_sub.alignment = PP_ALIGN.CENTER

        # =========================================================================
        # 12. СЛАЙД СВОДНОЙ ТАБЛИЦЫ ВСЕХ ПРЕПАРАТОВ
        # =========================================================================
        if by_product:
            slide_t = prs.slides.add_slide(blank_slide_layout)
            set_slide_background(slide_t)

            txBox_t = slide_t.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(0.8))
            tf_t = txBox_t.text_frame
            p = tf_t.paragraphs[0]
            p.text = "📋 Сводная таблица реализации всех препаратов"
            p.font.size = Pt(26)
            p.font.bold = True
            p.font.color.rgb = TEXT_WHITE

            top_products = list(by_product.items())[:8]
            rows = len(top_products) + 1
            cols = 4

            table_shape = slide_t.shapes.add_table(rows, cols, Inches(0.8), Inches(1.6), Inches(11.7), Inches(5.2))
            table = table_shape.table

            headers = ["Наименование препарата", "Всего продано (уп.)", "Текущий остаток (уп.)", "Доля рынка (%)"]
            for c_idx, h_text in enumerate(headers):
                cell = table.cell(0, c_idx)
                cell.text = h_text
                cell.fill.solid()
                cell.fill.fore_color.rgb = ACCENT_BLUE
                for p in cell.text_frame.paragraphs:
                    p.font.bold = True
                    p.font.size = Pt(13)
                    p.font.color.rgb = TEXT_WHITE

            for r_idx, (p_name, p_info) in enumerate(top_products, start=1):
                table.cell(r_idx, 0).text = str(p_name)[:45]
                table.cell(r_idx, 1).text = f"{p_info.get('realization_units_total_2025', 0):,}".replace(',', ' ')
                table.cell(r_idx, 2).text = f"{p_info.get('latest_stock_units', 0):,}".replace(',', ' ')
                table.cell(r_idx, 3).text = f"{p_info.get('share_percent', 0)} %"

                for c_i in range(4):
                    cell = table.cell(r_idx, c_i)
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = CARD_BG
                    for p in cell.text_frame.paragraphs:
                        p.font.size = Pt(11)
                        p.font.color.rgb = TEXT_WHITE

        # Save presentation to memory buffer
        out_buf = io.BytesIO()
        prs.save(out_buf)
        out_buf.seek(0)
        return out_buf.getvalue()

    except Exception as e:
        logger.exception(f"Error generating PPTX presentation: {e}")
        return None
