import base64
import json
import os
import re
from io import BytesIO

import anthropic
from pdf2image import convert_from_path


def parse_drawing_pdf_ai(pdf_path, api_key):
    """
    Парсит PDF чертеж через Claude API

    Args:
        pdf_path: путь к PDF файлу
        api_key: Claude API ключ

    Returns:
        dict: {table1: [...], table2: [...], table3: [...]}
    """

    print("🔄 Конвертирую PDF в изображение...")
    images = convert_from_path(pdf_path, dpi=300)
    page1_image = images[0]

    print("🔄 Конвертирую изображение в base64...")
    buffered = BytesIO()
    page1_image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    prompt = """Extract data from this engineering drawing and return ONLY a valid JSON object.

CRITICAL: Your ENTIRE response must be ONLY valid JSON. No explanations, no markdown, no text before or after.

Extract these three tables:

**Table 1** (top-right dimensions table):
- Headers: SIZE(inch), ASME, ENDS, L, Ød, ØF, H, WEIGHT
- Extract the VALUES from the row below the headers

**Table 2** (right-side Bill of Materials):
- Headers: Pos, Description, Material, Note
- Extract ALL rows from this table (usually 30-50 rows)
- If "Note" column is empty, use empty string ""

**Table 3** (bottom-right information block):
- Extract: CUSTOMER, PROJECT/LOCATION, EPC/END USER, P.O. No, TAG No, ECV JOB No, ITEM, VALVE D.S., DOC No

Return JSON in this EXACT structure:

{
  "table1": [
    {"SIZE(inch)": "value"},
    {"ASME": "value"},
    {"ENDS": "value"},
    {"L": "value"},
    {"Ød": "value"},
    {"ØF": "value"},
    {"H": "value"},
    {"WEIGHT": "value"}
  ],
  "table2": [
    {"pos": "1", "description": "Body", "material": "ASTM A350 LF2 CL1", "note": ""},
    {"pos": "2", "description": "Body End", "material": "...", "note": "..."},
    ... (all other rows)
  ],
  "table3": [
    {"CUSTOMER": "value"},
    {"PROJECT/LOCATION": "value"},
    {"EPC/END USER": "value"},
    {"P.O. No": "value"},
    {"TAG No": "value"},
    {"ECV JOB No": "value"},
    {"ITEM": "value"},
    {"VALVE D.S.": "value"},
    {"DOC No": "value"}
  ]
}

IMPORTANT:
- Keep exact values including special characters (~, ", etc.)
- Preserve all text exactly as shown
- If a field is not found, use empty string ""
- DO NOT add any text outside the JSON object
"""

    print("🔄 Отправляю запрос в Claude API...")
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_base64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    print("🔄 Обработка ответа...")
    response_text = response.content[0].text

    response_text = re.sub(r"```json\s*", "", response_text)
    response_text = re.sub(r"```\s*", "", response_text)
    response_text = response_text.strip()

    result = json.loads(response_text)
    result = fix_encoding(result)

    print("✅ Парсинг завершён!")
    return result


def fix_encoding(result):
    """Исправляет ТОЛЬКО технические проблемы кодировки UTF-8"""

    # Фикс символа Ø (это баг кодировки, не данные)
    for item in result.get("table1", []):
        for key in list(item.keys()):
            if "Ã˜" in key or "Ã" in key:
                # Заменяем битые UTF-8 символы
                new_key = key.replace("Ã˜", "Ø").replace("Ã", "")
                item[new_key] = item.pop(key)

    return result


if __name__ == "__main__":
    API_KEY = os.getenv("ANTHROPIC_API_KEY")

    PDF_PATH = "./test.pdf"

    try:
        result = parse_drawing_pdf_ai(PDF_PATH, API_KEY)

        print("\n" + "=" * 60)
        print("📊 РЕЗУЛЬТАТ ПАРСИНГА:")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))

        with open("parsed_result_ai.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print("\n💾 Результат сохранён в parsed_result_ai.json")

        print("\n📈 СТАТИСТИКА:")
        print(f"  ✅ Table 1: {len(result.get('table1', []))} полей")
        print(f"  ✅ Table 2: {len(result.get('table2', []))} строк")
        print(f"  ✅ Table 3: {len(result.get('table3', []))} полей")

        if result.get("table2"):
            print(f"\n📋 Table 2 (первые 5 строк):")
            for item in result["table2"][:5]:
                print(
                    f"  Pos {item['pos']}: {item['description']} - {item['material']}"
                )

    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        print(f"Ответ Claude:\n{response_text}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
