from fastapi import APIRouter

router = APIRouter()

@router.get("/verify")
async def verify():
    return {"status": "success", "message": "Verification endpoint is active."}

@router.post("/prospect")
async def create_prospect(data: dict):
    # Placeholder logic – replace with real prospect processing later
    return {"status": "received", "data": data}
