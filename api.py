import os
import tempfile
from typing import Optional

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from excel_export import generate_excel_from_api_response
from excel_parser import (
    merge_all_data,
    parse_bom_sheet,
    parse_manager_sheet,
    validate_bom_with_pdf,
)
from parser import parse_drawing_pdf_ai

load_dotenv()

app = FastAPI(title="PDF Parser API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "PDF Parser API v2",
        "endpoints": {
            "POST /api/parse-pdf": "Parse PDF + Excel BOM + Excel Manager with validation",
            "POST /api/export-excel": "Export parsing results to Excel file",
        },
    }


@app.post("/api/export-excel")
async def export_excel(data: dict = Body(...)):
    """
    Экспортирует результаты парсинга в Excel файл с цветовой индикацией

    Args:
        data: результат от /api/parse-pdf (JSON body)

    Returns:
        Excel файл для скачивания
    """

    try:
        # Генерируем Excel
        excel_path = generate_excel_from_api_response(data)

        # Возвращаем файл
        return FileResponse(
            excel_path,
            filename=f"parsing_result_{os.path.basename(excel_path).split('_', 2)[-1]}",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        return {"success": False, "error": f"Excel generation failed: {str(e)}"}


@app.post("/api/parse-pdf")
async def parse_pdf(
    pdf_file: UploadFile = File(..., description="PDF drawing file"),
    excel_bom: Optional[UploadFile] = File(
        None, description="BOM Excel file (optional)"
    ),
    excel_manager: Optional[UploadFile] = File(
        None, description="Manager Excel file (optional)"
    ),
    bom_sheet_index: int = Form(0, description="BOM sheet index (0-13 for Foglio1-14)"),
):
    """
    Полный workflow с валидацией:

    1. Парсит PDF → SIZE + ASME + ENDS + компоненты
    2. Парсит BOM.xlsx (sheet_index)
    3. ВАЛИДАЦИЯ: BOM.size == PDF.SIZE && BOM.asme == PDF.ASME && BOM.ends == PDF.ENDS
    4. Если валидация FAILED → возвращаем ошибку (сотрудник указал неверный sheet)
    5. Если ОК → берём quantity из BOM
    6. Парсит order-manager.xlsx (автопоиск по SIZE+ASME)
    7. Сравнивает всё и возвращает результат

    Returns:
        {
            "success": true,
            "data": {
                "table2": [
                    {
                        "pos": "3",
                        "description": "Ball",
                        "material": {
                            "value": "ASTM A182 F316/316L",
                            "isEqual": true,
                            "from_manager_data": "A182 F316/F316L"
                        },
                        "quantity": {
                            "value": 2,
                            "from_bom": true
                        },
                        "Closures": {
                            "from_manager_data": "A350 LF2"
                        }
                    }
                ]
            },
            "validation": {
                "bom_valid": true,
                "manager_found": true
            }
        }
    """

    # Сохраняем PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_tmp:
        pdf_content = await pdf_file.read()
        pdf_tmp.write(pdf_content)
        pdf_path = pdf_tmp.name

    bom_path = None
    manager_path = None

    # Сохраняем Excel файлы если предоставлены
    if excel_bom:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as bom_tmp:
            bom_content = await excel_bom.read()
            bom_tmp.write(bom_content)
            bom_path = bom_tmp.name

    if excel_manager:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as manager_tmp:
            manager_content = await excel_manager.read()
            manager_tmp.write(manager_content)
            manager_path = manager_tmp.name

    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")

        if not api_key:
            return {"success": False, "error": "API ключ не найден"}

        # ШАГ 1: Парсим PDF
        pdf_data = parse_drawing_pdf_ai(pdf_path, api_key)

        # Извлекаем SIZE, ASME, ENDS из table1
        table1 = pdf_data.get("table1", [])
        pdf_size = None
        pdf_asme = None
        pdf_ends = None

        for item in table1:
            if item.get("field") == "SIZE":
                pdf_size = item.get("value")
            elif item.get("field") == "ASME":
                pdf_asme = item.get("value")
            elif item.get("field") == "ENDS":
                pdf_ends = item.get("value")

        validation_info = {}

        # ШАГ 2-7: Если есть Excel файлы - обрабатываем
        if bom_path and manager_path:
            try:
                # ШАГ 2: Парсим BOM
                bom_data = parse_bom_sheet(bom_path, bom_sheet_index)

                # ШАГ 3: КРИТИЧЕСКАЯ ВАЛИДАЦИЯ
                validation = validate_bom_with_pdf(
                    bom_data, pdf_size, pdf_asme, pdf_ends
                )

                validation_info["bom_validation"] = validation

                # ШАГ 4: Если валидация провалилась - ОСТАНАВЛИВАЕМСЯ
                if not validation["valid"]:
                    return {
                        "success": False,
                        "error": "BOM validation failed - неверный sheet_index",
                        "validation_errors": validation["errors"],
                        "bom_data": {
                            "size": bom_data["size"],
                            "asme": bom_data["asme"],
                            "ends": bom_data["ends"],
                        },
                        "pdf_data": {
                            "size": pdf_size,
                            "asme": pdf_asme,
                            "ends": pdf_ends,
                        },
                        "message": "Сотрудник указал неверный bom_sheet_index. Данные не совпадают с PDF.",
                    }

                # ШАГ 5: Валидация ОК - продолжаем
                validation_info["bom_valid"] = True
                validation_info["bom_sheet"] = bom_sheet_index
                validation_info["bom_components"] = len(bom_data["components"])

                # ШАГ 6: Парсим Manager
                manager_data = parse_manager_sheet(
                    manager_path, bom_data["size"], bom_data["asme"]
                )

                if manager_data["found"]:
                    validation_info["manager_found"] = True
                    validation_info["manager_row"] = manager_data["row"]
                    validation_info["manager_materials"] = len(
                        manager_data["materials"]
                    )

                    # ШАГ 7: Объединяем всё
                    pdf_data = merge_all_data(
                        pdf_data, bom_data["components"], manager_data["materials"]
                    )
                else:
                    validation_info["manager_found"] = False
                    validation_info["manager_error"] = manager_data.get("error")

            except Exception as excel_error:
                return {
                    "success": False,
                    "error": f"Ошибка обработки Excel: {str(excel_error)}",
                }

        response = {"success": True, "data": pdf_data}

        if validation_info:
            response["validation"] = validation_info

        return response

    except Exception as e:
        return {"success": False, "error": str(e)}

    finally:
        # Удаляем временные файлы
        os.unlink(pdf_path)
        if bom_path:
            os.unlink(bom_path)
        if manager_path:
            os.unlink(manager_path)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
