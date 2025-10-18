from fastapi import APIRouter, UploadFile, File

router = APIRouter()

@router.post("/import_csv")
async def import_csv(file: UploadFile = File(...)):
    contents = await file.read()
    # Placeholder logic: you can parse CSV here later
    return {"filename": file.filename, "size": len(contents)}
