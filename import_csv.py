from fastapi import APIRouter, UploadFile, File, HTTPException
import csv, io
from ..main import LEADS

router = APIRouter(prefix="/import", tags=["import"])

@router.post("/csv")
async def import_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a CSV file")
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="ignore")))
    count = 0
    for row in reader:
        if not (row.get("phone") or row.get("email")):
            continue
        lead_id = f"lead_{len(LEADS)+1}"
        LEADS[lead_id] = {
            "full_name": row.get("name") or row.get("full_name"),
            "email": row.get("email"),
            "phone": row.get("phone"),
            "company": row.get("company") or row.get("business") or "",
            "timezone": row.get("timezone") or "America/New_York",
            "consent_sms": False, "consent_email": False, "consent_voice": False,
            "dnc": False,
            "source": row.get("source") or "csv_import",
            "tags": [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()]
        }
        count += 1
    return {"imported": count}