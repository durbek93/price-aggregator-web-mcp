# -*- coding: utf-8 -*-
import io
import logging
from typing import Dict, Any, Optional

import matplotlib
matplotlib.use('Agg')  # Headless backend
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger("analyst_agent.chart_generator")

# Apply modern dark theme aesthetics
plt.style.use('dark_background')


def generate_sales_chart(sales_data: Dict[str, Any]) -> Optional[bytes]:
    """
    Генерирует дашборд продаж (динамика реализации по месяцам и доли дистрибьюторов) в формате PNG.
    """
    if not sales_data:
        return None

    try:
        monthly_trend = sales_data.get("monthly_trend", [])
        by_distributor = sales_data.get("by_distributor", {})

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), facecolor='#12131C')
        ax1.set_facecolor('#1E1F2E')
        ax2.set_facecolor('#1E1F2E')

        # 1. График динамики продаж по месяца (в упаковках)
        if monthly_trend:
            periods = [item.get("period", "").capitalize() for item in monthly_trend]
            realization = [item.get("realization_units", 0) for item in monthly_trend]

            bars = ax1.bar(periods, realization, color='#4E73DF', edgecolor='#6085EF', alpha=0.85, width=0.55)
            ax1.set_title("Динамика продаж по месяцам (упаковки)", fontsize=13, fontweight='bold', pad=12, color='#FFFFFF')
            ax1.set_ylabel("Количество упаковок", fontsize=10, color='#A0A5BA')
            ax1.tick_params(colors='#A0A5BA', axis='x', rotation=30)
            ax1.tick_params(colors='#A0A5BA', axis='y')
            ax1.grid(axis='y', linestyle='--', alpha=0.25, color='#4E73DF')

            # Подписи значений над столбцами
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax1.annotate(f'{height:,}'.replace(',', ' '),
                                 xy=(bar.get_x() + bar.get_width() / 2, height),
                                 xytext=(0, 4), textcoords="offset points",
                                 ha='center', va='bottom', fontsize=9, fontweight='bold', color='#6085EF')
        else:
            ax1.text(0.5, 0.5, "Данные по месяцам отсутствуют", ha='center', va='center', color='#A0A5BA')

        # 2. Доли дистрибьюторов (горизонтальная гистограмма)
        if by_distributor:
            # Сортируем топ-7 дистрибьюторов
            sorted_dists = sorted(by_distributor.items(), key=lambda x: x[1].get("realization_units", 0), reverse=True)[:7]
            d_names = [d[0] for d in reversed(sorted_dists)]
            d_units = [d[1].get("realization_units", 0) for d in reversed(sorted_dists)]

            y_pos = np.arange(len(d_names))
            bars2 = ax2.barh(y_pos, d_units, color='#1CC88A', edgecolor='#36E0A0', alpha=0.85, height=0.55)
            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(d_names, fontsize=10, color='#FFFFFF')
            ax2.set_title("Топ дистрибьюторов по реализации", fontsize=13, fontweight='bold', pad=12, color='#FFFFFF')
            ax2.set_xlabel("Объем реализации (уп.)", fontsize=10, color='#A0A5BA')
            ax2.tick_params(colors='#A0A5BA', axis='x')
            ax2.grid(axis='x', linestyle='--', alpha=0.25, color='#1CC88A')

            for bar in bars2:
                width = bar.get_width()
                if width > 0:
                    ax2.annotate(f'{width:,}'.replace(',', ' '),
                                 xy=(width, bar.get_y() + bar.get_height() / 2),
                                 xytext=(5, 0), textcoords="offset points",
                                 ha='left', va='center', fontsize=9, fontweight='bold', color='#36E0A0')
        else:
            ax2.text(0.5, 0.5, "Данные по дистрибьюторам отсутствуют", ha='center', va='center', color='#A0A5BA')

        plt.tight_layout(pad=2.5)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        logger.exception(f"Error generating sales chart: {e}")
        plt.close('all')
        return None


def generate_price_trend_chart(price_data: Dict[str, Any], target_name: str) -> Optional[bytes]:
    """
    Генерирует график сравнения цен дистрибьюторов по препарату или производителю.
    """
    if not price_data or not price_data.get("drugs"):
        return None

    try:
        drugs = price_data.get("drugs", [])
        fig, ax = plt.subplots(figsize=(10, 5.5), facecolor='#12131C')
        ax.set_facecolor('#1E1F2E')

        # Берём первые 5 препаратов для понятной визуализации
        top_drugs = drugs[:5]
        drug_names = [d.get("name", "Препарат")[:25] for d in top_drugs]
        min_prices = [d.get("min_price", 0) for d in top_drugs]
        avg_prices = [d.get("avg_price", 0) for d in top_drugs]

        x = np.arange(len(drug_names))
        width = 0.35

        rects1 = ax.bar(x - width/2, min_prices, width, label='Мин. цена', color='#1CC88A', alpha=0.85)
        rects2 = ax.bar(x + width/2, avg_prices, width, label='Сем. средняя цена', color='#4E73DF', alpha=0.85)

        ax.set_title(f"Сравнение цен: {target_name}", fontsize=13, fontweight='bold', pad=12, color='#FFFFFF')
        ax.set_ylabel("Цена (сум)", fontsize=10, color='#A0A5BA')
        ax.set_xticks(x)
        ax.set_xticklabels(drug_names, rotation=25, ha='right', fontsize=9, color='#FFFFFF')
        ax.tick_params(colors='#A0A5BA', axis='y')
        ax.legend(facecolor='#1E1F2E', edgecolor='#4E73DF', labelcolor='#FFFFFF')
        ax.grid(axis='y', linestyle='--', alpha=0.25, color='#4E73DF')

        for rect in rects1:
            h = rect.get_height()
            if h > 0:
                ax.annotate(f'{h:,.0f}'.replace(',', ' '), xy=(rect.get_x() + rect.get_width()/2, h),
                            xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8, color='#36E0A0')

        for rect in rects2:
            h = rect.get_height()
            if h > 0:
                ax.annotate(f'{h:,.0f}'.replace(',', ' '), xy=(rect.get_x() + rect.get_width()/2, h),
                            xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8, color='#6085EF')

        plt.tight_layout(pad=2.0)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        logger.exception(f"Error generating price trend chart: {e}")
        plt.close('all')
        return None


def generate_product_monthly_chart(product_name: str, monthly_realization: Dict[str, int], monthly_stock: Dict[str, int]) -> Optional[bytes]:
    """
    Генерирует график помесячной динамики продаж и остатков для одного конкретного препарата.
    """
    if not monthly_realization:
        return None

    try:
        months = list(monthly_realization.keys())
        realization = list(monthly_realization.values())
        stocks = [monthly_stock.get(m, 0) for m in months]

        fig, ax = plt.subplots(figsize=(10, 4.2), facecolor='#12131C')
        ax.set_facecolor('#1E1F2E')

        x = np.arange(len(months))
        width = 0.45

        bars = ax.bar(x, realization, width, label='Реализация (уп.)', color='#4E73DF', alpha=0.85)
        ax.plot(x, stocks, color='#1CC88A', marker='o', linewidth=2.5, label='Остаток (уп.)')

        ax.set_title(f"Динамика продаж и остатков: {product_name}", fontsize=12, fontweight='bold', pad=10, color='#FFFFFF')
        ax.set_xticks(x)
        ax.set_xticklabels([m.capitalize() for m in months], rotation=25, ha='right', fontsize=9, color='#FFFFFF')
        ax.tick_params(colors='#A0A5BA', axis='y')
        ax.legend(facecolor='#1E1F2E', edgecolor='#4E73DF', labelcolor='#FFFFFF')
        ax.grid(axis='y', linestyle='--', alpha=0.25, color='#4E73DF')

        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.annotate(f'{h:,}'.replace(',', ' '), xy=(bar.get_x() + bar.get_width()/2, h),
                            xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8, color='#6085EF')

        plt.tight_layout(pad=1.8)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        logger.exception(f"Error generating product monthly chart: {e}")
        plt.close('all')
        return None

