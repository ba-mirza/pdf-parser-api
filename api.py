import os
import tempfile

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from parser import fix_encoding, parse_drawing_pdf_ai

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/parse-pdf")
async def parse_pdf(file: UploadFile = File(...)):
    """
    Парсит PDF чертеж и возвращает JSON с 3 таблицами
    """

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        result = parse_drawing_pdf_ai(tmp_path, api_key)
        result = fix_encoding(result)

        return JSONResponse(
            content={"success": True, "data": result},
            media_type="application/json; charset=utf-8",
        )

    except Exception as e:
        return {"success": False, "error": str(e)}

    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
