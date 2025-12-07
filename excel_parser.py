import openpyxl
from fuzzywuzzy import fuzz


def parse_bom_sheet(filepath, sheet_index):
    """
    Парсит конкретный лист BOM.xlsx

    Args:
        filepath: путь к BOM.xlsx
        sheet_index: индекс листа (0-13)

    Returns:
        {
            "size": "12\"",
            "asme": "ASME 600",
            "components": {
                "Body": {"quantity": 1, "material": "ASTM A350 LF2"},
                "Ball": {"quantity": 1, "material": "ASTM A182 F316/316L"},
                ...
            }
        }
    """

    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.worksheets[sheet_index]

    # Извлекаем SIZE и ASME из строки 28
    size = ws.cell(28, 4).value  # D28 - Dimensione
    asme = ws.cell(28, 15).value  # O28 - Classe

    components = {}

    # Парсим компоненты (строки 31+)
    for row in ws.iter_rows(min_row=31, max_row=100, values_only=True):
        if len(row) <= 42:
            continue

        component_name = row[28]  # AC - Descrizione componente
        quantity = row[42]  # AQ - Q.tà
        material = row[2]  # C - Material (если есть)

        if component_name and str(component_name).strip():
            name = str(component_name).strip()

            # Пропускаем заголовок
            if name == "Descrizione componente":
                continue

            try:
                qty = int(quantity) if quantity else 1
            except (ValueError, TypeError):
                qty = 1

            components[name] = {
                "quantity": qty,
                "material": str(material).strip() if material else None,
            }

    return {
        "size": str(size).strip() if size else None,
        "asme": str(asme).strip() if asme else None,
        "components": components,
    }


def parse_manager_sheet(filepath, target_size, target_asme):
    """
    Парсит order-manager.xlsx (только первый лист)
    Ищет строку где Size = target_size И Class = target_asme

    Args:
        filepath: путь к order-manager.xlsx
        target_size: размер для поиска (например "12")
        target_asme: класс для поиска (например "ASME 600")

    Returns:
        {
            "found": True,
            "row": 15,
            "components": {
                "Body": {"material": "A350 LF2"},
                "Ball": {"material": "A182 F316/F316L"},
                ...
            }
        }
    """

    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active  # Первый лист

    # Маппинг колонок на компоненты (Col 18-30)
    component_columns = {
        18: "Body",
        19: "Closures",
        20: "Gland",
        21: "Trunnion",
        22: "Weld overlay",
        23: "Ball",
        24: "Seat rings",
        25: "Seat inserts",
        26: "Stem",
        27: "Dynamic seals",
        28: "Static seals",
        29: "Fire Safe gaskets",
        30: "Springs",
    }

    # Нормализуем target для сравнения
    target_size_clean = (
        target_size.replace('"', "").replace("'", "").strip() if target_size else ""
    )
    target_asme_clean = target_asme.strip() if target_asme else ""

    # Ищем строку с нужными Size и Class
    for row_idx in range(15, 100):  # Строки с данными начинаются с 15
        row = list(ws.iter_rows(min_row=row_idx, max_row=row_idx, values_only=True))[0]

        if len(row) < 30:
            continue

        size_value = row[8]  # Col 9 - Size (Inch)
        class_value = row[9]  # Col 10 - Class (lbs)

        if not size_value or not class_value:
            continue

        # Нормализуем значения
        size_str = str(size_value).replace('"', "").replace("'", "").strip()
        class_str = str(class_value).strip()

        # Проверяем совпадение
        if target_size_clean in size_str and target_asme_clean in class_str:
            # Нашли нужную строку! Извлекаем материалы
            components = {}

            for col_idx, component_name in component_columns.items():
                material = row[col_idx - 1]  # -1 потому что row с индекса 0

                if material and str(material).strip():
                    components[component_name] = {"material": str(material).strip()}

            return {
                "found": True,
                "row": row_idx,
                "size": size_str,
                "asme": class_str,
                "components": components,
            }

    return {
        "found": False,
        "error": f"Не найдена строка с Size={target_size} и Class={target_asme}",
    }


def compare_components(bom_components, manager_components):
    """
    Сравнивает компоненты из BOM и Manager

    Returns:
        {
            "Body": {
                "bom": {"quantity": 1, "material": "ASTM A350 LF2"},
                "manager": {"material": "A350 LF2"},
                "quantity_match": True,
                "material_match": False,
                "diff": {...}
            }
        }
    """

    comparison = {}

    # Собираем все уникальные имена компонентов
    all_components = set(bom_components.keys()) | set(manager_components.keys())

    for component in all_components:
        bom_data = bom_components.get(component, {})
        manager_data = manager_components.get(component, {})

        bom_qty = bom_data.get("quantity")
        bom_mat = bom_data.get("material")

        manager_mat = manager_data.get("material")

        # Сравниваем материалы (fuzzy match)
        material_match = None
        if bom_mat and manager_mat:
            similarity = fuzz.token_sort_ratio(
                str(bom_mat).lower(), str(manager_mat).lower()
            )
            material_match = similarity >= 75

        comparison[component] = {
            "bom": bom_data if bom_data else None,
            "manager": manager_data if manager_data else None,
            "material_match": material_match,
        }

    return comparison


def merge_with_pdf(pdf_data, comparison):
    """
    Объединяет данные PDF с результатами сравнения BOM и Manager

    Args:
        pdf_data: результат парсинга PDF
        comparison: результат compare_components

    Returns:
        pdf_data с дополненным table2
    """

    for item in pdf_data.get("table2", []):
        description = item.get("description", "").strip()

        if not description:
            continue

        # Ищем совпадение в comparison
        matched_component = None

        # Точное совпадение
        if description in comparison:
            matched_component = description
        else:
            # Fuzzy match
            best_match = None
            best_score = 0

            for comp_name in comparison.keys():
                score = fuzz.token_sort_ratio(description.lower(), comp_name.lower())

                if score > best_score and score >= 70:
                    best_score = score
                    best_match = comp_name

            if best_match:
                matched_component = best_match

        # Добавляем данные из сравнения
        if matched_component:
            comp_data = comparison[matched_component]

            item["excel_data"] = {
                "bom": comp_data.get("bom"),
                "manager": comp_data.get("manager"),
                "material_match": comp_data.get("material_match"),
            }

    return pdf_data
