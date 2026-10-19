
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from extractor import extract_academic_items

from parser import parse_whatsapp_text

app = FastAPI(title="SMART API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "project": "SMART",
        "message": "SMART backend is running",
    }


@app.post("/api/upload-chat")
async def upload_chat(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a WhatsApp .txt export.",
        )

    # Limit this demo to 5 MB per upload.
    content = await file.read(5 * 1024 * 1024 + 1)

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="File is too large. Maximum size is 5 MB.",
        )

    try:
        raw_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Could not decode this file as UTF-8 text.",
        )

    messages = parse_whatsapp_text(raw_text)

    if not messages:
        raise HTTPException(
            status_code=422,
            detail="No recognised WhatsApp messages were found.",
        )

    return {
        "filename": file.filename,
        "total_messages": len(messages),
        "messages": messages,
    }



@app.post("/api/extract-academic")
async def extract_academic(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a WhatsApp .txt export.",
        )

    content = await file.read(5 * 1024 * 1024 + 1)

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="File is too large. Maximum size is 5 MB.",
        )

    try:
        raw_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Could not decode this file as UTF-8 text.",
        )

    messages = parse_whatsapp_text(raw_text)

    if not messages:
        raise HTTPException(
            status_code=422,
            detail="No recognised WhatsApp messages were found.",
        )

    items = extract_academic_items(messages)

    return {
        "filename": file.filename,
        "total_messages": len(messages),
        "total_items": len(items),
        "items": items,
    }

