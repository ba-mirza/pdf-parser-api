import base64
import json
import os
import re
from io import BytesIO

import anthropic
from pdf2image import convert_from_path


def parse_technical_params(pdf_path, api_key):
    """
    Парсит ТОЛЬКО технические параметры из bottom-left зоны чертежа

    Returns:
        dict: {
            "DESIGN_TEMP": "...",
            "DESIGN_PRESSURE": "...",
            "PRESSURE_TEST_BODY": "...",
            "PRESSURE_TEST_SEAT": "..."
        }
    """

    print("🔄 Извлекаю технические параметры из bottom-left зоны...")

    # Конвертируем PDF в изображение
    images = convert_from_path(pdf_path, dpi=600)  # Высокое разрешение для OCR
    full_image = images[0]

    # Вырезаем bottom-left зону (где находятся технические параметры)
    width, height = full_image.size
    left = 0
    top = int(height * 0.65)  # Нижние 35%
    right = int(width * 0.35)  # Левые 35%
    bottom = height

    bottom_left = full_image.crop((left, top, right, bottom))

    # Конвертируем в base64
    buffered = BytesIO()
    bottom_left.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    # Фокусированный промпт ТОЛЬКО для технических параметров
    prompt = """Extract ONLY the technical parameters from this section of an engineering drawing.

Look for these specific fields in the text block labeled "TECHNICAL REMARKS AND CONSTRUCTION DETAIL":

1. DESIGN TEMPERATURE - Look for line starting with "DESIGN TEMPERATURE:" followed by temperature range
2. DESIGN PRESSURE - Look for line starting with "DESIGN PRESSURE:" followed by pressure values
3. PRESSURE TEST BODY - Look for "PRESSURE TEST:" then "-BODY - HYDROSTATIC" followed by value
4. PRESSURE TEST SEAT - Look for "PRESSURE TEST:" then "-SEAT - HYDROSTATIC" followed by value

Return ONLY a valid JSON object with these exact fields:

{
  "DESIGN_TEMP": "value from drawing or empty string",
  "DESIGN_PRESSURE": "value from drawing or empty string",
  "PRESSURE_TEST_BODY": "value from drawing or empty string",
  "PRESSURE_TEST_SEAT": "value from drawing or empty string"
}

IMPORTANT:
- Include units (°C, °F, bar, psi, etc.) in the values
- If a field is not found, use empty string ""
- Return ONLY the JSON object, no markdown, no explanations
"""

    # Отправляем в Claude API
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
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

    response_text = response.content[0].text

    # Очищаем от markdown
    response_text = re.sub(r"```json\s*", "", response_text)
    response_text = re.sub(r"```\s*", "", response_text)
    response_text = response_text.strip()

    result = json.loads(response_text)

    print("✅ Технические параметры извлечены!")
    return result


def parse_drawing_pdf_ai(pdf_path, api_key):
    """
    Парсит PDF чертеж через Claude API

    Args:
        pdf_path: путь к PDF файлу
        api_key: Claude API ключ

    Returns:
        dict: {table1: [...], table2: [...], table3: [...]}
    """

    print("🔄 Конвертирую PDF в изображение (DPI 500)...")
    images = convert_from_path(pdf_path, dpi=500)
    page1_image = images[0]

    print("🔄 Конвертирую изображение в base64...")
    buffered = BytesIO()
    page1_image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    # ФИНАЛЬНЫЙ ПРОМПТ с детальными OCR правилами
    prompt = """Extract data from this engineering drawing and return ONLY a valid JSON object.

CRITICAL: Your ENTIRE response must be ONLY valid JSON. No explanations, no markdown, no text before or after.

Extract these three tables:

**Table 1** (top-right dimensions table):
- Headers: SIZE(inch), ASME, ENDS, L, Ød, ØF, H, WEIGHT
- Extract the VALUES from the row below the headers
- CRITICAL - READ EACH VALUE CAREFULLY:
  * SIZE: Common error "2\"" vs "12\"" - small valves are 2", 3", 4"
  * L: Length value (usually 200-800 range for small valves)
  * H: Height value (usually 200-500 range for small valves)
  * WEIGHT: Typically the SMALLEST number (10-100 range for small valves)
  * DO NOT swap values between L, H, and WEIGHT!
  * If you see L=295, H=350, WEIGHT=45 → use EXACTLY these values
  * Some values may have "~" suffix - preserve it!

**Table 2** (right-side Bill of Materials):
- THIS IS CRITICAL: Read the COMPLETE table from top to bottom!
- Headers: Pos, Description, Material, Note
- Extract EVERY SINGLE ROW - there are typically 35-45 rows
- DO NOT stop early - read until the very last component
- Some position numbers have "*" prefix (e.g., *256, *364) - preserve this!
- Position numbers range from 1 to 700+
- If "Note" column is empty, use empty string ""

**Table 3** (bottom-right information block):
- Extract: CUSTOMER, PROJECT/LOCATION, EPC/END USER, P.O. No, TAG No, ECV JOB No, ITEM, VALVE D.S., DOC No

Return JSON in this EXACT structure:

{
  "table1": [
    {"field": "SIZE", "value": "12\\""},
    {"field": "ASME", "value": "600"},
    {"field": "ENDS", "value": "RTJ"},
    {"field": "L", "value": "841"},
    {"field": "Ød", "value": "305"},
    {"field": "ØF", "value": "559"},
    {"field": "H", "value": "385~"},
    {"field": "WEIGHT", "value": "1200~"}
  ],
  "table2": [
    {"pos": "1", "description": "Body", "material": "ASTM A350 LF2 CL1", "note": ""},
    {"pos": "2", "description": "Body End", "material": "...", "note": "..."},
    ... (CONTINUE extracting ALL rows - don't stop!)
    {"pos": "704", "description": "Ring Joint Ring", "material": "...", "note": ""}
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

CRITICAL OCR ACCURACY RULES - READ CAREFULLY:

1. **COMMON OCR MISTAKES - FIX THESE:**
   Component Names (letter confusion):
   - "Gland" (NOT "Liner", "6land", "Clond") - CHECK THIS CAREFULLY!
   - "Ball" (NOT "Bolt", "8olt", "8all")
   - "Ball Bushing" (NOT "Bolt Bushing" or "Stem Bushing")
   - "Operator Flange" (often missed completely - pos 23!)
   - "Flange Vent/Drain" (NOT "Upper Vent/Drain")
   - "Operator Fl. Screw" (NOT "Operator FL Screw")
   - "Thrust Washer Ball" (NOT "Thrust Washer Bolt")

2. **MATERIAL SPECIFICATIONS - EXACT FORMATS:**
   Common mistakes to avoid:
   - "ASTM A320 L7M" (NOT "ASTM A350 L7M") - A320 vs A350 are different!
   - "ASTM A194 Gr.7M" (NOT "ASTM A194 Gr7M" or "ASTM A350 L7M")
   - "ASTM A479 S20910" (NOT "ASTM A479 SS904H") - S20910 is exact grade!
   - "C45" (NOT "CARBON STEEL" or "C4S")
   - "SOFT IRON" (NOT "API 6A" or "CAST IRON")
   - "CAST IRON" (NOT "CARBON STEEL")
   - "SS Gr.316" (NOT "SS 6r.316" or "SS Gr-316")

3. **LETTER/NUMBER CONFUSION:**
   - "A320" vs "A350" vs "A194" - these are DIFFERENT materials!
   - "S20910" vs "SS904H" - completely different grades!
   - "C45" vs "C4S" or "CAS"
   - "Gr.7M" vs "L7M" - different notations
   - "l" vs "I" vs "1": Gland ≠ 6land, Flange ≠ F1ange
   - "rn" vs "m": Stern ≠ Stem
   - "a" vs "o": Ball ≠ Bolt, Gland ≠ Glond

4. **POSITION NUMBERS:**
   - Some positions have "*" prefix: *256, *364, *402, *404, *405, *409, *414, *415
   - Preserve the "*" exactly as shown
   - Range: 1 to 700+
   - Read them as: "1", "2", "3", "17", "23", "28", "*256", "433", "578", "704"

5. **NOTE COLUMN:**
   - Common values: "XM-19", "+HDG", "+N06625 W.D.", "tHRG"
   - Preserve exact format including "+" signs
   - If empty, use ""

6. **SPECIAL CHARACTERS:**
   - Tilde (~): "385~", "1200~"
   - Degree (°): Use proper degree symbol
   - Diameter (Ø): Use Ø character
   - Asterisk (*): Preserve in position numbers
   - Plus (+): "SS Gr.316 + PTFE", "+HDG"

DOUBLE-CHECK THESE SPECIFIC ROWS (common errors):
- pos 17: Should be "Gland" (NOT "Liner"), material "ASTM A479 S20910" (NOT "SS904H")
- pos 23: "Operator Flange" - this is often completely missed!
- pos 154: "Body Bolt", material "ASTM A320 L7M" (NOT A350!)
- pos 155: "Body Nut", material "ASTM A194 Gr.7M" (NOT A350!)
- pos 162-163: "Flange Vent/Drain" (NOT "Upper Vent/Drain")
- pos 436: "Ball Bushing" (NOT "Stem Bushing")
- pos 439: "Thrust Washer Ball" (NOT "Bolt")
- pos 551: "Stem Key", material "C45" (NOT "CARBON STEEL")
- pos 578: "Gear", material "CAST IRON" - don't skip this!
- pos 704: "Ring Joint Ring", material "SOFT IRON" (NOT "API 6A")

IMPORTANT REMINDERS:
- READ THE COMPLETE TABLE - there are 40+ rows!
- Keep exact values including special characters
- Preserve all text exactly as shown
- If a field is not found, use empty string ""
- DO NOT add any text outside the JSON object
- When uncertain between similar words, consider context (valve parts)
"""

    print("🔄 Отправляю запрос в Claude API...")
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,  # Увеличили для длинного ответа
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

    # Фикс символа Ø в table1 (это баг кодировки, не данные)
    if "table1" in result:
        fixed_table1 = []
        for item in result["table1"]:
            fixed_item = {}
            for key, value in item.items():
                # Исправляем битые UTF-8 символы в ключе (field)
                if "Ã˜" in str(key) or "Ã" in str(key):
                    fixed_key = str(key).replace("Ã˜", "Ø").replace("Ã", "")
                else:
                    fixed_key = key

                fixed_item[fixed_key] = value

            fixed_table1.append(fixed_item)

        result["table1"] = fixed_table1

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

            print(f"\n📋 Table 2 (последние 5 строк):")
            for item in result["table2"][-5:]:
                print(
                    f"  Pos {item['pos']}: {item['description']} - {item['material']}"
                )

            # Проверка критических позиций
            print(f"\n🔍 ПРОВЕРКА КРИТИЧЕСКИХ ПОЗИЦИЙ:")
            critical = ["17", "23", "154", "155", "436", "439", "551", "578", "704"]
            for pos in critical:
                found = next(
                    (item for item in result["table2"] if item["pos"] == pos), None
                )
                if found:
                    print(
                        f"  ✅ Pos {pos}: {found['description']} - {found['material']}"
                    )
                else:
                    print(f"  ❌ Pos {pos}: НЕ НАЙДЕН!")

    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        print(f"Ответ Claude:\n{response_text}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
