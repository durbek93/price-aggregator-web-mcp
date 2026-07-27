# -*- coding: utf-8 -*-
import sys
from pathlib import Path

# Add current dir to python path
sys.path.insert(0, str(Path(__file__).parent))

import chart_generator
import presentation_generator

mock_sales_data = {
    "meta": {"city": "г. Фергана", "total_files": 12, "periods": ["январь", "февраль", "март"]},
    "summary": {"total_realization": 45200, "total_stock_latest": 12400},
    "monthly_trend": [
        {"period": "Январь", "realization_units": 12000, "stock_units": 4500},
        {"period": "Февраль", "realization_units": 15400, "stock_units": 4100},
        {"period": "Март", "realization_units": 17800, "stock_units": 3800},
    ],
    "by_distributor": {
        "Гранд Фарм": {"realization_units": 20000, "stock_units": 5000, "share_percent": 44.2},
        "Мерос": {"realization_units": 14000, "stock_units": 4000, "share_percent": 31.0},
        "Асклепий": {"realization_units": 11200, "stock_units": 3400, "share_percent": 24.8},
    },
    "by_product": {
        "Анаферон детский 20 таб": {"realization_units_total_2025": 25000, "latest_stock_units": 5400, "share_percent": 55.3},
        "Эргоферон 20 таб": {"realization_units_total_2025": 14200, "latest_stock_units": 4200, "share_percent": 31.4},
        "Ренгалин 20 таб": {"realization_units_total_2025": 6000, "latest_stock_units": 2800, "share_percent": 13.3},
    }
}

mock_price_data = {
    "drugs": [
        {"name": "Анаферон детский 20 таб", "min_price": 42000, "avg_price": 45500},
        {"name": "Эргоферон 20 таб", "min_price": 58000, "avg_price": 61200},
        {"name": "Ренгалин 20 таб", "min_price": 49000, "avg_price": 52000},
    ]
}

def test_visualization_modules():
    print("--- 🧪 Testing Chart Generator ---")
    sales_chart = chart_generator.generate_sales_chart(mock_sales_data)
    assert sales_chart is not None and len(sales_chart) > 1000, "Failed to generate sales PNG chart!"
    print(f"✅ Sales Chart PNG successfully generated: {len(sales_chart)} bytes")

    price_chart = chart_generator.generate_price_trend_chart(mock_price_data, "Материа Медика")
    assert price_chart is not None and len(price_chart) > 1000, "Failed to generate price trend PNG chart!"
    print(f"✅ Price Trend PNG successfully generated: {len(price_chart)} bytes")

    print("\n--- 🧪 Testing Presentation Generator ---")
    pptx_data = presentation_generator.build_analytics_presentation(mock_sales_data, title="Тестовая Презентация")
    assert pptx_data is not None and len(pptx_data) > 5000, "Failed to generate PPTX presentation!"
    print(f"✅ Presentation PPTX successfully generated: {len(pptx_data)} bytes")

    print("\n🎉 ALL VISUALIZATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_visualization_modules()
