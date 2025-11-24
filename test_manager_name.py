#!/usr/bin/env python
"""
Тестовый скрипт для проверки извлечения ФИО Менеджера из ячейки C5
"""
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'insurance_project.settings')
django.setup()

from openpyxl import load_workbook
import pandas as pd

def test_excel_file(file_path):
    """Тестирует извлечение ФИО Менеджера из Excel файла"""
    print(f"\n{'='*60}")
    print(f"Тестирование файла: {file_path}")
    print(f"{'='*60}\n")
    
    if not os.path.exists(file_path):
        print(f"❌ Файл не найден: {file_path}")
        return
    
    # Тест 1: openpyxl
    print("📊 Тест 1: Чтение с помощью openpyxl")
    print("-" * 60)
    try:
        workbook = load_workbook(file_path, data_only=True)
        sheet = workbook.active
        
        # Читаем ячейку C5
        c5_value = sheet['C5'].value
        print(f"Ячейка C5 (raw): {repr(c5_value)}")
        print(f"Ячейка C5 (str): '{c5_value}'")
        print(f"Тип данных: {type(c5_value)}")
        print(f"Пустая: {c5_value is None or str(c5_value).strip() == ''}")
        
        # Читаем соседние ячейки для контекста
        print(f"\nКонтекст (соседние ячейки):")
        for row in range(3, 8):
            for col in ['B', 'C', 'D', 'E']:
                cell_addr = f"{col}{row}"
                cell_val = sheet[cell_addr].value
                if cell_val:
                    print(f"  {cell_addr}: '{cell_val}'")
        
        print("✅ openpyxl: Успешно")
    except Exception as e:
        print(f"❌ openpyxl: Ошибка - {e}")
    
    # Тест 2: pandas
    print(f"\n{'='*60}")
    print("📊 Тест 2: Чтение с помощью pandas")
    print("-" * 60)
    try:
        df = pd.read_excel(file_path, sheet_name=0, header=None)
        
        # Читаем ячейку C5 (row=4, col=2 в pandas, т.к. 0-based)
        c5_value = df.iloc[4, 2] if len(df) > 4 and len(df.columns) > 2 else None
        print(f"Ячейка C5 (row=4, col=2): {repr(c5_value)}")
        print(f"Ячейка C5 (str): '{c5_value}'")
        print(f"Тип данных: {type(c5_value)}")
        print(f"Пустая: {pd.isna(c5_value) or str(c5_value).strip() == ''}")
        
        # Показываем первые несколько строк для контекста
        print(f"\nПервые 8 строк (столбцы B-E):")
        if len(df) >= 8 and len(df.columns) >= 5:
            print(df.iloc[0:8, 1:5].to_string())
        
        print("✅ pandas: Успешно")
    except Exception as e:
        print(f"❌ pandas: Ошибка - {e}")
    
    print(f"\n{'='*60}\n")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Использование: python test_manager_name.py <путь_к_excel_файлу>")
        print("\nПример:")
        print("  python test_manager_name.py /path/to/application.xlsx")
        sys.exit(1)
    
    file_path = sys.argv[1]
    test_excel_file(file_path)
