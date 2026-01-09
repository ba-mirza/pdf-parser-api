"""
ГИБРИДНОЕ СРАВНЕНИЕ МАТЕРИАЛОВ
================================
Токенизация + Словарь синонимов

Преимущества:
- ✅ Быстро (без ML моделей)
- ✅ Понимает сокращения (GRAF = GRAPHITE)
- ✅ Различает важные цифры (A320 ≠ A350)
- ✅ Предсказуемо и надежно
"""

import re
from typing import Tuple

# ============================================================================
# СЛОВАРЬ СИНОНИМОВ
# ============================================================================

MATERIAL_SYNONYMS = {
    # Графит
    "GRAPHITE": ["GRAPHITE", "GRAF", "GR"],
    # Нержавеющая сталь
    "SS316": [
        "SS 316",
        "SS GR 316",
        "S316",
        "S316/L",
        "S316L",
        "STAINLESS STEEL GR 316",
        "F316",
        "F316L",
        "F316/L",
        "F316/F316L",
    ],
    "SS304": ["SS 304", "SS GR 304", "S304", "S304/L"],
    # LF2 группа
    "LF2": ["LF2", "LF2W62", "A350 LF2", "ASTM A350 LF2"],
    # L7M группа (болты)
    "L7M": ["L7M", "L7MHDG", "L7M+HDG", "L7M HDG", "A320 L7M", "ASTM A320 L7M"],
    # XM19 (S20910)
    "XM19": ["XM19", "XM19HR", "XM-19", "A479 XM19", "S20910", "A479 S20910"],
    # A182 F316
    "A182F316": ["A182 F316", "A182 F316L", "A182 F316/F316L", "ASTM A182 F316"],
    # PTFE композиты
    "SSBPTFE": ["SS GR 316 + PTFE", "SSBPTFE", "SS + PTFE", "SS GR316 + PTFE"],
    "SSGRAF": [
        "SS GR 316 + GRAPHITE",
        "SSGRAF",
        "SS + GRAPHITE",
        "SS GR316 + GRAPHITE",
    ],
    # SOFT IRON
    "SOFTIRON": ["SOFT IRON", "SOFTIRON"],
    # PEEK
    "PEEK": ["PEEK"],
    # ELGILOY
    "ELGILOY": ["ELGILOY"],
}


# ============================================================================
# НОРМАЛИЗАЦИЯ
# ============================================================================


def normalize(text: str) -> str:
    """
    Нормализует материал для сравнения

    Убирает:
    - Лишние пробелы
    - Точки после сокращений (GR., CL.)
    - Префиксы (ASTM, ASME)
    - Приводит к uppercase

    Args:
        text: Исходный текст

    Returns:
        Нормализованный текст
    """
    if not text:
        return ""

    text = str(text).upper().strip()

    # Заменяем слэши и дефисы на пробелы
    text = text.replace("/", " ").replace("-", " ")

    # Убираем точки после сокращений
    text = text.replace("GR.", "GR").replace("CL.", "CL")

    # Убираем стандартные префиксы
    text = text.replace("ASTM ", "").replace("ASME ", "")

    # Убираем лишние пробелы
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ============================================================================
# ПРОВЕРКА ПО СЛОВАРЮ
# ============================================================================


def check_synonyms(mat1: str, mat2: str) -> bool:
    """
    Проверяет материалы по словарю синонимов

    Args:
        mat1: Первый материал
        mat2: Второй материал

    Returns:
        True если оба материала в одной группе синонимов
    """
    norm1 = normalize(mat1)
    norm2 = normalize(mat2)

    # Проверяем каждую группу синонимов
    for base_name, synonyms in MATERIAL_SYNONYMS.items():
        # Нормализуем все синонимы
        normalized_synonyms = [normalize(s) for s in synonyms]

        # Если оба материала в этой группе → совпадают
        if norm1 in normalized_synonyms and norm2 in normalized_synonyms:
            return True

    return False


# ============================================================================
# ТОКЕНИЗАЦИЯ
# ============================================================================


def extract_tokens(text: str) -> set:
    """
    Извлекает значимые токены из материала

    Значимые токены:
    - Длина >= 2 И содержит цифру (A350, F316, L7M)
    - Длина >= 3 (LF2, HDG, PEEK)

    Args:
        text: Исходный текст

    Returns:
        Множество токенов
    """
    if not text:
        return set()

    # Нормализация
    text = normalize(text)

    # Извлекаем буквенно-цифровые токены
    tokens = re.findall(r"[A-Z0-9]+", text)

    # Фильтруем значимые
    result = set()
    for token in tokens:
        has_digit = any(c.isdigit() for c in token)

        # Токен значимый если:
        # 1. Содержит цифру И длина >= 2
        # 2. Длина >= 3
        if (has_digit and len(token) >= 2) or len(token) >= 3:
            result.add(token)

    return result


def check_tokens(mat1: str, mat2: str) -> bool:
    """
    Проверяет совпадение токенов

    Args:
        mat1: Первый материал
        mat2: Второй материал

    Returns:
        True если есть общие токены
    """
    tokens1 = extract_tokens(mat1)
    tokens2 = extract_tokens(mat2)

    # Есть ли пересечение?
    common = tokens1 & tokens2

    return len(common) > 0


# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================================


def smart_material_match(material1: str, material2: str) -> Tuple[bool, str]:
    """
    Умное сравнение материалов (гибридный подход)

    Порядок проверок:
    1. Пустые значения → False
    2. Точное совпадение → True
    3. Словарь синонимов → True
    4. Токенизация → True
    5. Иначе → False

    Args:
        material1: Материал из PDF
        material2: Материал из BOM/Order

    Returns:
        (is_equal, method) где:
        - is_equal: True если материалы равны
        - method: способ определения ("exact", "synonym", "token", "none")

    Examples:
        >>> smart_material_match("GRAPHITE", "GRAF")
        (True, "synonym")

        >>> smart_material_match("ASTM A350 LF2", "LF2W62")
        (True, "synonym")

        >>> smart_material_match("ASTM A320 L7M", "ASTM A350 L7M")
        (False, "none")  # A320 ≠ A350
    """
    # 1. Проверка на пустые
    if not material1 or not material2:
        return (False, "empty")

    # 2. Нормализация
    norm1 = normalize(material1)
    norm2 = normalize(material2)

    # 3. Точное совпадение после нормализации
    if norm1 == norm2:
        return (True, "exact")

    # 4. Проверка по словарю синонимов
    if check_synonyms(material1, material2):
        return (True, "synonym")

    # 5. Проверка токенов
    if check_tokens(material1, material2):
        return (True, "token")

    # 6. Не совпало
    return (False, "none")


# Для обратной совместимости (без метода)
def compare_materials(material1: str, material2: str) -> bool:
    """
    Простая функция сравнения (обратная совместимость)

    Args:
        material1: Первый материал
        material2: Второй материал

    Returns:
        True если материалы равны
    """
    is_equal, _ = smart_material_match(material1, material2)
    return is_equal


# ============================================================================
# ТЕСТЫ
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 100)
    print("🧪 ТЕСТ ГИБРИДНОГО СРАВНЕНИЯ МАТЕРИАЛОВ")
    print("=" * 100)

    # Реальные тест-кейсы из проекта
    test_cases = [
        # (material1, material2, expected, description)
        ("GRAPHITE", "GRAF", True, "Синоним графита"),
        ("ASTM A350 LF2 CL1", "A350 LF2", True, "Токены A350, LF2"),
        ("ASTM A350 LF2", "LF2W62", True, "Синоним LF2"),
        ("ASTM A350 LF2 CL1", "LF2", True, "Синоним LF2"),
        ("ASTM A182 F316/F316L", "A182 F316", True, "Токены A182, F316"),
        ("ASTM A182 F316/F316L", "F316/L", True, "Синоним F316"),
        ("ASTM A479 S20910", "A479 XM19", True, "Синоним XM19 = S20910"),
        ("ASTM A479 S20910", "XM19HR", True, "Синоним XM19"),
        ("ASTM A320 L7M", "ASTM A350 L7M", False, "A320 ≠ A350 (разные стандарты!)"),
        ("ASTM A320 L7M", "L7MHDG", True, "Синоним L7M"),
        ("CARBON STEEL", "C45", False, "Разные материалы"),
        ("SS Gr.316 + GRAPHITE", "SSGRAF", True, "Синоним SSGRAF"),
        ("SS Gr.316 + PTFE", "SSBPTFE", True, "Синоним SSBPTFE"),
        ("STAINLESS STEEL Gr.316", "SS Gr.316", True, "Синоним SS316"),
        ("SOFT IRON", "SOFTIRON", True, "Синоним (пробел)"),
        ("SOFT IRON", "API 6A", False, "Разные стандарты"),
        ("CAST IRON", "CARBON STEEL", False, "Разные типы стали"),
        ("PEEK", "PEEK", True, "Точное совпадение"),
        ("ELGILOY", "ELGILOY", True, "Точное совпадение"),
        ("ASTM A194 Gr.7M", "ASTM A194 Gr7M", True, "С точкой и без"),
    ]

    print("\n📊 Результаты:")
    print(
        f"{'Material 1':<35} | {'Material 2':<20} | Result | Method    | Expected | Description"
    )
    print("-" * 140)

    correct = 0
    total = len(test_cases)

    for mat1, mat2, expected, description in test_cases:
        is_equal, method = smart_material_match(mat1, mat2)

        status = "✅" if is_equal == expected else "❌"
        result_str = "YES" if is_equal else "NO"
        expected_str = "YES" if expected else "NO"

        if is_equal == expected:
            correct += 1

        print(
            f"{status} {mat1:<33} | {mat2:<18} | {result_str:<6} | {method:<9} | {expected_str:<8} | {description}"
        )

    print("-" * 140)
    accuracy = correct / total * 100
    print(f"\n📈 ТОЧНОСТЬ: {correct}/{total} ({accuracy:.1f}%)")

    if accuracy == 100:
        print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ! ГОТОВО К ИНТЕГРАЦИИ!")
    else:
        print(f"\n⚠️  Не прошло {total - correct} тестов")

    print("=" * 100 + "\n")
