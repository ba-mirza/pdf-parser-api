import os
import tempfile
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from excel_parser import (
    compare_components,
    merge_with_pdf,
    parse_bom_sheet,
    parse_manager_sheet,
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
        "endpoints": {"POST /api/parse-pdf": "Parse PDF + Excel BOM + Excel Manager"},
    }


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
    Полный workflow парсинга:

    1. Парсит PDF → SIZE + ASME + компоненты
    2. Парсит BOM.xlsx (sheet_index) → компоненты с quantity
    3. Парсит order-manager.xlsx (автопоиск по SIZE+ASME) → материалы
    4. Сравнивает BOM vs Manager
    5. Объединяет всё с PDF данными

    Returns:
        {
            "success": true,
            "data": {
                "table1": [...],
                "table2": [
                    {
                        "pos": "1",
                        "description": "Body",
                        "material": "...",
                        "note": "...",
                        "excel_data": {
                            "bom": {
                                "quantity": 1,
                                "material": "ASTM A350 LF2"
                            },
                            "manager": {
                                "material": "A350 LF2"
                            },
                            "material_match": false
                        }
                    }
                ],
                "table3": [...]
            },
            "excel_stats": {
                "bom_sheet": 0,
                "bom_size": "12\"",
                "bom_asme": "ASME 600",
                "manager_found": true,
                "manager_row": 15,
                "components_compared": 42
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

        excel_stats = {}

        # ШАГ 2-5: Если есть Excel файлы - обрабатываем их
        if bom_path and manager_path:
            try:
                # ШАГ 2: Парсим BOM
                bom_data = parse_bom_sheet(bom_path, bom_sheet_index)

                excel_stats["bom_sheet"] = bom_sheet_index
                excel_stats["bom_size"] = bom_data["size"]
                excel_stats["bom_asme"] = bom_data["asme"]
                excel_stats["bom_components"] = len(bom_data["components"])

                # ШАГ 3: Парсим Manager (ищем по SIZE и ASME из BOM)
                manager_data = parse_manager_sheet(
                    manager_path, bom_data["size"], bom_data["asme"]
                )

                if manager_data["found"]:
                    excel_stats["manager_found"] = True
                    excel_stats["manager_row"] = manager_data["row"]
                    excel_stats["manager_size"] = manager_data["size"]
                    excel_stats["manager_asme"] = manager_data["asme"]
                    excel_stats["manager_components"] = len(manager_data["components"])

                    # ШАГ 4: Сравниваем BOM vs Manager
                    comparison = compare_components(
                        bom_data["components"], manager_data["components"]
                    )

                    excel_stats["components_compared"] = len(comparison)

                    # ШАГ 5: Merge с PDF
                    pdf_data = merge_with_pdf(pdf_data, comparison)

                else:
                    excel_stats["manager_found"] = False
                    excel_stats["manager_error"] = manager_data.get("error")

            except Exception as excel_error:
                excel_stats["error"] = f"Ошибка обработки Excel: {str(excel_error)}"

        elif bom_path:
            # Только BOM без Manager
            try:
                bom_data = parse_bom_sheet(bom_path, bom_sheet_index)
                excel_stats["bom_only"] = True
                excel_stats["bom_size"] = bom_data["size"]
                excel_stats["bom_asme"] = bom_data["asme"]
                excel_stats["bom_components"] = len(bom_data["components"])
            except Exception as e:
                excel_stats["error"] = f"Ошибка BOM: {str(e)}"

        response = {"success": True, "data": pdf_data}

        if excel_stats:
            response["excel_stats"] = excel_stats

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
