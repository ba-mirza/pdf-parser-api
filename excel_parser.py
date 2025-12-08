import openpyxl
from fuzzywuzzy import fuzz


def parse_bom_sheet(filepath, sheet_index):
    """
    Парсит конкретный лист BOM.xlsx
    Извлекает classe, dimensione, estremità для валидации
    И компоненты с quantity

    Returns:
        {
            "size": "12\"",
            "asme": "ASME 600",
            "ends": "RTJ",
            "components": {
                "Body": {"quantity": 1},
                "Ball": {"quantity": 1},
                ...
            }
        }
    """

    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.worksheets[sheet_index]

    # Извлекаем поля для валидации из строки 28
    size = ws.cell(28, 4).value  # D28 - Dimensione
    asme = ws.cell(28, 15).value  # O28 - Classe
    ends = ws.cell(28, 25).value  # Y28 - Estremità

    components = {}

    # Парсим компоненты (строки 31+)
    for row in ws.iter_rows(min_row=31, max_row=100, values_only=True):
        if len(row) <= 42:
            continue

        component_name = row[28]  # AC - Descrizione componente
        quantity = row[42]  # AQ - Q.tà

        # Пропускаем пустые строки или строки со смещением
        if not component_name or str(component_name).strip() == "":
            continue

        name = str(component_name).strip()

        # Пропускаем заголовок
        if name == "Descrizione componente":
            continue

        try:
            qty = int(quantity) if quantity else 1
        except (ValueError, TypeError):
            qty = 1

        components[name] = {"quantity": qty}

    return {
        "size": str(size).strip() if size else None,
        "asme": str(asme).strip() if asme else None,
        "ends": str(ends).strip() if ends else None,
        "components": components,
    }


def validate_bom_with_pdf(bom_data, pdf_size, pdf_asme, pdf_ends):
    """
    Валидирует что BOM соответствует PDF

    Returns:
        {
            "valid": True/False,
            "errors": [...]
        }
    """

    errors = []

    # Нормализуем для сравнения
    bom_size = (
        bom_data["size"].replace('"', "").replace("'", "").strip()
        if bom_data["size"]
        else ""
    )
    pdf_size_clean = (
        pdf_size.replace('"', "").replace("'", "").strip() if pdf_size else ""
    )

    bom_asme = bom_data["asme"].strip() if bom_data["asme"] else ""
    pdf_asme_clean = pdf_asme.strip() if pdf_asme else ""

    bom_ends = bom_data["ends"].strip() if bom_data["ends"] else ""
    pdf_ends_clean = pdf_ends.strip() if pdf_ends else ""

    # Проверяем совпадение
    if bom_size not in pdf_size_clean and pdf_size_clean not in bom_size:
        errors.append(f"SIZE не совпадает: BOM={bom_data['size']}, PDF={pdf_size}")

    if bom_asme not in pdf_asme_clean and pdf_asme_clean not in bom_asme:
        errors.append(f"ASME не совпадает: BOM={bom_data['asme']}, PDF={pdf_asme}")

    if bom_ends not in pdf_ends_clean and pdf_ends_clean not in bom_ends:
        errors.append(f"ENDS не совпадает: BOM={bom_data['ends']}, PDF={pdf_ends}")

    return {"valid": len(errors) == 0, "errors": errors}


def parse_manager_sheet(filepath, target_size, target_asme):
    """
    Парсит order-manager.xlsx (только первый лист)
    Ищет строку где Size = target_size И Class = target_asme

    Returns:
        {
            "found": True,
            "row": 15,
            "materials": {
                "Body": "A350 LF2",
                "Closures": "A350 LF2",
                "Ball": "A182 F316/F316L",
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
    for row_idx in range(15, 100):
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
            materials = {}

            for col_idx, component_name in component_columns.items():
                material = row[col_idx - 1]  # -1 потому что row с индекса 0

                if material and str(material).strip():
                    materials[component_name] = str(material).strip()

            return {
                "found": True,
                "row": row_idx,
                "size": size_str,
                "asme": class_str,
                "materials": materials,
            }

    return {
        "found": False,
        "error": f"Не найдена строка с Size={target_size} и Class={target_asme}",
    }


def find_matching_manager_column(pdf_description, manager_materials):
    """
    Находит соответствующую колонку Manager для компонента PDF

    Args:
        pdf_description: "Body", "Ball", "Seat Spring", etc.
        manager_materials: {"Body": "A350 LF2", "Ball": "A182 F316", ...}

    Returns:
        ("Body", "A350 LF2") или (None, None)
    """

    pdf_lower = pdf_description.lower().strip()

    # Точное совпадение
    for manager_key, manager_value in manager_materials.items():
        if pdf_lower == manager_key.lower():
            return (manager_key, manager_value)

    # Частичное совпадение
    for manager_key, manager_value in manager_materials.items():
        manager_lower = manager_key.lower()

        # Проверяем вхождение
        if pdf_lower in manager_lower or manager_lower in pdf_lower:
            return (manager_key, manager_value)

    # Fuzzy match
    best_match = None
    best_score = 0

    for manager_key, manager_value in manager_materials.items():
        score = fuzz.token_sort_ratio(pdf_lower, manager_key.lower())

        if score > best_score and score >= 70:
            best_score = score
            best_match = (manager_key, manager_value)

    return best_match if best_match else (None, None)


def merge_all_data(pdf_data, bom_components, manager_materials):
    """
    Объединяет данные из PDF, BOM и Manager

    Правила:
    1. Для каждого компонента PDF → ищем соответствующую колонку Manager → сравниваем
    2. Для колонок Manager которых нет в PDF → создаём новые объекты

    Структура:
    {
        "material": {
            "value": "из PDF",
            "isEqual": true/false/null,
            "from_manager_data": "из Manager",
            "new_item": false
        }
    }
    """

    # Отслеживаем какие колонки Manager мы уже использовали
    used_manager_columns = set()

    # Обрабатываем компоненты из PDF
    for item in pdf_data.get("table2", []):
        description = item.get("description", "").strip()

        if not description:
            continue

        # 1. Добавляем quantity из BOM
        matched_bom = None
        for bom_name, bom_data in bom_components.items():
            if fuzz.token_sort_ratio(description.lower(), bom_name.lower()) >= 70:
                matched_bom = bom_data
                break

        if matched_bom:
            item["quantity"] = {"value": matched_bom["quantity"], "from_bom": True}

        # 2. Находим соответствующую колонку в Manager
        manager_column, manager_value = find_matching_manager_column(
            description, manager_materials
        )

        if manager_column:
            used_manager_columns.add(manager_column)

        # 3. Обрабатываем material из PDF
        pdf_material = item.get("material", "")

        if pdf_material:
            # Сравниваем с Manager
            is_equal = None
            if manager_value:
                similarity = fuzz.token_sort_ratio(
                    str(pdf_material).lower(), str(manager_value).lower()
                )
                is_equal = similarity >= 75

            item["material"] = {
                "value": pdf_material,
                "isEqual": is_equal,
                "from_manager_data": manager_value if manager_value else None,
                "new_item": False,
            }
        elif manager_value:
            # Нет в PDF, но есть в Manager
            item["material"] = {
                "value": None,
                "isEqual": None,
                "from_manager_data": manager_value,
                "new_item": False,
            }

    # 4. Добавляем компоненты которых НЕТ в PDF, но ЕСТЬ в Manager
    for manager_column, manager_value in manager_materials.items():
        if manager_column not in used_manager_columns:
            # Создаём новый объект
            new_item = {
                "description": manager_column,
                "material": {"value": manager_value, "isEqual": None, "new_item": True},
            }

            pdf_data.get("table2", []).append(new_item)

    return pdf_data
