# -*- coding: utf-8 -*-
"""
Сводный прайс: Фасад-обертка для обратной совместимости.
Вся бизнес-логика разделена на модули:
- excel_reader: логика разбора и чтения Excel-таблиц.
- grouping: нормализация названий препаратов и сопоставление по каталогу.
- matrix_builder: извлечение данных и сборка сводных матриц.
- report_formatter: визуальное форматирование выходного отчета Excel.
"""
from __future__ import annotations

import argparse
import ctypes
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import openpyxl
import pandas as pd
import yaml

from app.core.price_utils import (
    to_number,
    round_price,
    normalize_name,
)

# Импорт констант и функций из excel_reader
from app.core.excel_reader import (
    DEFAULT_KEY_CANDIDATES,
    DEFAULT_NAME_CANDIDATES,
    DEFAULT_PRICE_CANDIDATES,
    DEFAULT_STOCK_CANDIDATES,
    DEFAULT_PRODUCER_CANDIDATES,
    DEFAULT_EXPIRY_CANDIDATES,
    _normalize_col_for_match,
    _clean_col,
    pick_column,
    pick_price_column,
    resolve_price_column_for_sheet,
    _excel_engine_for,
    _grand_farm_header_row,
    read_price_table
)

# Импорт функций из grouping
from app.core.grouping import (
    normalize_product_for_grouping,
    fuzzy_merge_canonicals,
    is_materia_producer_norm,
    friendly_source_label,
    build_catalog_materia_medica,
    match_canonical,
    is_excluded_product
)

# Импорт функций из matrix_builder
from app.core.matrix_builder import (
    extract_by_producer,
    extract_materia_any,
    build_matrix_from_extracted
)

# Импорт форматирования
from app.core.report_formatter import (
    format_summary_sheet
)


def format_elapsed_seconds(sec: float) -> str:
    """Человекочитаемая строка для вывода в консоль."""
    if sec >= 60:
        minutes = int(sec // 60)
        rest = sec - minutes * 60
        return f"Время работы: {minutes} мин {rest:.1f} с"
    return f"Время работы: {sec:.1f} с"


def _live_timer_caption(sec: float) -> str:
    """Короткая подпись для заголовка окна (обновляется в реальном времени)."""
    if sec >= 3600:
        h = int(sec // 3600)
        sec -= h * 3600
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{h}ч {m:02d}:{s:02d}"
    if sec >= 60:
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{m}:{s:02d}"
    return f"{sec:.1f} с"


def _set_console_window_title(title: str) -> None:
    """Заголовок окна консоли (сверху): не смешивается с текстом в области вывода."""
    try:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        else:
            sys.stdout.write(f"\033]0;{title}\007")
            sys.stdout.flush()
    except Exception:
        pass


def _run_live_timer(stop: threading.Event, elapsed_fn: Callable[[], float], title_prefix: str) -> None:
    while not stop.wait(0.2):
        elapsed = elapsed_fn()
        _set_console_window_title(f"{title_prefix} — {_live_timer_caption(elapsed)}")


def start_live_console_timer(
    started: float,
    title_prefix: str = "Сводный прайс",
) -> Tuple[threading.Event, threading.Thread]:
    """Фоновый таймер в заголовке окна CMD/терминала."""
    stop = threading.Event()

    def elapsed() -> float:
        return time.perf_counter() - started

    t = threading.Thread(
        target=_run_live_timer,
        args=(stop, elapsed, title_prefix),
        daemon=True,
    )
    t.start()
    return stop, t


def finalize_live_console_timer_title(title_prefix: str, total_sec: float) -> None:
    """Заголовок после остановки таймера (строка «готово»)."""
    _set_console_window_title(f"{title_prefix} — готово, {_live_timer_caption(total_sec)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Сводный прайс из нескольких Excel")
    parser.add_argument("--config", type=Path, default=None, help="Путь к config.yml")
    parser.add_argument("--inputs", type=str, default="prices", help="Папка или файл(ы) с прайсами")
    parser.add_argument("--output", type=Path, default=None, help="Выходной Excel (по умолчанию: output/Сводный прайс + ДД.ММ.ГГГГ.xlsx)")
    parser.add_argument("--products", nargs="*", help="Список препаратов для извлечения")
    parser.add_argument("--producers", nargs="*", default=[], help="Список подстрок производителя")
    parser.add_argument("--producer-matrix", action="store_true", help="Матрица по производителю Materia Medica")
    args = parser.parse_args()
    if args.output is None:
        today = datetime.now().strftime("%d.%m.%Y")
        args.output = Path("output") / f"Сводный прайс {today}.xlsx"

    key_candidates = DEFAULT_KEY_CANDIDATES
    name_candidates = DEFAULT_NAME_CANDIDATES
    price_candidates = DEFAULT_PRICE_CANDIDATES
    stock_candidates = DEFAULT_STOCK_CANDIDATES
    producer_candidates = DEFAULT_PRODUCER_CANDIDATES

    if args.config and args.config.exists():
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        cols = cfg.get("columns", {})
        key_candidates = cols.get("key_candidates", key_candidates)
        name_candidates = cols.get("name_candidates", name_candidates)
        price_candidates = cols.get("price_candidates", price_candidates)
        stock_candidates = cols.get("stock_candidates", stock_candidates)
        producer_candidates = cols.get("producer_candidates", producer_candidates)

    inputs_path = Path(args.inputs)
    if inputs_path.is_dir():
        files = list(inputs_path.glob("*.xlsx")) + list(inputs_path.glob("*.xls"))
    else:
        files = [Path(args.inputs)]

    if not files:
        print("Нет файлов для обработки.", file=sys.stderr)
        sys.exit(1)

    all_source_labels = [friendly_source_label(p.stem) for p in files]
    all_source_labels = sorted(dict.fromkeys(all_source_labels))

    catalog = build_catalog_materia_medica()

    if args.producer_matrix:
        extracted = []
        total = len(files)
        for i, path in enumerate(files, 1):
            try:
                print(f"[{i}/{total}] {path.name}", flush=True)
                df = read_price_table(
                    path,
                    key_candidates,
                    name_candidates,
                    price_candidates,
                    stock_candidates,
                    use_key=True,
                    use_name=True,
                    read_preset=None,
                )
                extracted += extract_materia_any(
                    df,
                    path,
                    key_candidates,
                    name_candidates,
                    price_candidates,
                    stock_candidates,
                    producer_candidates,
                    catalog,
                )
            except Exception as e:
                print(f"Ошибка при чтении {path}: {e}", file=sys.stderr)
        matrix = build_matrix_from_extracted(extracted, catalog, all_source_labels)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        matrix.to_excel(args.output, index=False, engine="openpyxl")
        wb = openpyxl.load_workbook(args.output)
        for sheet in wb.worksheets:
            format_summary_sheet(sheet)
        wb.save(args.output)
        print(f"Сохранено: {args.output}")
        return

    all_rows = []
    for path in files:
        try:
            df = read_price_table(
                path,
                key_candidates,
                name_candidates,
                price_candidates,
                stock_candidates,
                use_key=True,
                use_name=True,
                read_preset=None,
            )
            if args.producers:
                all_rows += extract_by_producer(
                    df, path, [p.lower() for p in args.producers],
                    key_candidates, name_candidates, price_candidates, stock_candidates, producer_candidates,
                )
            else:
                for _, r in df.iterrows():
                    name_val = r.get(pick_column(list(df.columns), name_candidates))
                    price_val = r.get(pick_price_column(list(df.columns), price_candidates))
                    price_num = to_number(price_val)
                    rounded_price = round_price(price_num) if price_num is not None else None
                    if name_val is not None and rounded_price is not None:
                        if is_excluded_product(str(name_val)):
                            continue
                        all_rows.append({"name": name_val, "price": rounded_price, "source": path.stem})
        except Exception as e:
            print(f"Ошибка при чтении {path}: {e}", file=sys.stderr)
    if not all_rows:
        print("Нет данных для записи.", file=sys.stderr)
        sys.exit(1)
    out_df = pd.DataFrame(all_rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_excel(args.output, index=False, engine="openpyxl")
    wb = openpyxl.load_workbook(args.output)
    for sheet in wb.worksheets:
        format_summary_sheet(sheet)
    wb.save(args.output)
    print(f"Сохранено: {args.output}")


if __name__ == "__main__":
    _timer_prefix = "Сводный прайс"
    _t0 = time.perf_counter()
    _stop_live, _live_thread = start_live_console_timer(_t0, title_prefix=_timer_prefix)
    try:
        main()
    finally:
        _stop_live.set()
        _live_thread.join(timeout=2.0)
        _total = time.perf_counter() - _t0
        finalize_live_console_timer_title(_timer_prefix, _total)
        print(format_elapsed_seconds(_total), flush=True)
