from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx, asyncio
from typing import Dict, Any, List
from ..main import LEADS
from ..services.verify import verify_phone_e164, verify_email
from ..services.sources import google_places_leads, yelp_leads

router = APIRouter(prefix="/prospect", tags=["prospecting"])

class VerifyIn(BaseModel):
    phone: str | None = None
    email: str | None = None

@router.post("/verify")
async def verify_contact(payload: VerifyIn):
    out = {}
    async with httpx.AsyncClient() as client:
        tasks = []
        if payload.phone:
            tasks.append(verify_phone_e164(client, payload.phone))
        if payload.email:
            tasks.append(verify_email(client, payload.email))
        results = await asyncio.gather(*tasks)
    if payload.phone and payload.email:
        phone_res, email_res = results
        out = {"phone": phone_res, "email": email_res}
    elif payload.phone:
        out = {"phone": results[0]}
    else:
        out = {"email": results[0]}
    return out

class LeadGenIn(BaseModel):
    vertical: str
    query: str
    location_text: str | None = None
    latlng: str | None = None
    limit: int = 30

@router.post("/generate")
async def generate_leads(inp: LeadGenIn):
    leads = []
    async with httpx.AsyncClient() as client:
        if inp.vertical == "local_business":
            g = await google_places_leads(client, inp.query, inp.latlng or "39.7589,-84.1916", radius_m=15000)
            y = await yelp_leads(client, inp.query, inp.location_text or "Dayton, OH", limit=inp.limit)
            leads = (g + y)[:inp.limit]
        elif inp.vertical == "real_estate":
            y = await yelp_leads(client, inp.query, inp.location_text or "Dayton, OH", limit=inp.limit)
            leads = y
        else:
            raise HTTPException(400, "Unknown vertical")

    uniq = {}
    for ld in leads:
        key = (ld.get("phone") or "") + (ld.get("company") or "")
        if key and key not in uniq:
            uniq[key] = ld

    created_ids = []
    for ld in uniq.values():
        lead_id = f"lead_{len(LEADS)+1}"
        LEADS[lead_id] = {
            "full_name": ld.get("full_name"),
            "email": ld.get("email"),
            "phone": ld.get("formatted_phone_number") or ld.get("phone"),
            "company": ld.get("company"),
            "tags": ld.get("tags", []),
            "source": ld.get("source"),
            "timezone": "America/New_York",
            "consent_sms": False, "consent_email": False, "consent_voice": False,
            "dnc": False
        }
        created_ids.append(lead_id)
    return {"count": len(created_ids), "lead_ids": created_ids}