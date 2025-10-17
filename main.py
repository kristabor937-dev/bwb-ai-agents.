import os, json, datetime
from typing import Dict, Any, List
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from zoneinfo import ZoneInfo
import httpx
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="BWB AI Agents")
templates = Jinja2Templates(directory="app/templates")

TWILIO_FROM = os.getenv("TWILIO_FROM", "+15555555555")
TWILIO_SID  = os.getenv("TWILIO_SID", "ACxxxx")
TWILIO_TOKEN= os.getenv("TWILIO_TOKEN", "twxxxx")
SENDGRID_KEY= os.getenv("SENDGRID_KEY", "SG.xxxx")
CALENDAR_LINK = os.getenv("CALENDAR_LINK", "https://cal.com/yourname/intro")
QUIET_START_HOUR = int(os.getenv("QUIET_START_HOUR","8"))
QUIET_END_HOUR = int(os.getenv("QUIET_END_HOUR","21"))
DEFAULT_TZ = os.getenv("DEFAULT_TIMEZONE","America/New_York")

try:
    BRANDING = json.load(open("app/templates/branding.json","r"))
except:
    BRANDING = {"platform_name":"BWB AI Agents","company_name":"BWB Express","company_phone":"+1-937-303-1701"}

LEADS: Dict[str, Dict[str, Any]] = {}
MESSAGES: List[Dict[str, Any]] = []

def local_now(tz: str) -> datetime.datetime:
    try:
        return datetime.datetime.now(ZoneInfo(tz))
    except Exception:
        return datetime.datetime.now()

def is_quiet_hours(tz: str) -> bool:
    hour = local_now(tz).hour
    return not (QUIET_START_HOUR <= hour < QUIET_END_HOUR)

def contains_optout(text: str) -> bool:
    if not text: return False
    t = text.lower()
    return any(k in t for k in ["stop","stopall","unsubscribe","cancel","end","quit"])

async def send_sms(to: str, body: str):
    MESSAGES.append({"channel":"sms","to":to,"body":body,"ts":datetime.datetime.utcnow().isoformat()})
    # Real Twilio (uncomment):
    # async with httpx.AsyncClient(auth=(TWILIO_SID, TWILIO_TOKEN)) as c:
    #   await c.post(f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
    #                data={"From": TWILIO_FROM, "To": to, "Body": body})

async def send_email(to: str, subject: str, body: str):
    MESSAGES.append({"channel":"email","to":to,"subject":subject,"body":body,"ts":datetime.datetime.utcnow().isoformat()})
    # Real SendGrid (uncomment):
    # async with httpx.AsyncClient() as c:
    #   await c.post("https://api.sendgrid.com/v3/mail/send",
    #                headers={"Authorization": f"Bearer {SENDGRID_KEY}"},
    #                json={"personalizations":[{"to":[{"email":to}]}],
    #                      "from":{"email":BRANDING.get("company_email","noreply@example.com")},
    #                      "subject":subject,"content":[{"type":"text/plain","value":body}]})

async def compliance_guard(lead: dict, channel: str, content: str) -> tuple[bool,str]:
    if lead.get("dnc"): return False, "DNC"
    if channel == "sms" and not lead.get("consent_sms"): return False, "No SMS consent"
    if channel == "email" and not lead.get("consent_email"): return False, "No email consent"
    if channel == "voice" and not lead.get("consent_voice"): return False, "No voice consent"
    if is_quiet_hours(lead.get("timezone", DEFAULT_TZ)) and channel in ("sms","voice"):
        return False, "Quiet hours"
    return True, "OK"

async def nurturer_sms(lead: dict) -> str:
    first = (lead.get("full_name") or "there").split()[0].title()
    return (f"Hey {first}, it’s Kris from {BRANDING.get('company_name','our team')}. "
            f"Quick idea to boost your local visibility—5 on-brand posts today to spark leads. "
            f"Okay to text details? Reply YES. (Reply STOP to opt out.)")

async def closer_sms(lead: dict) -> str:
    first = (lead.get("full_name") or "there").split()[0].title()
    return (f"{first}, 15-min strategy call to map your next 7 days of leads? "
            f"Grab a slot: {CALENDAR_LINK} (Reply STOP to opt out.)")

async def analyst_next_best_action(lead: dict) -> dict:
    return {"nba":"sms","template":"nurture"}

async def orchestrate_outbound(lead_id: str):
    lead = LEADS.get(lead_id)
    if not lead: return
    nba = await analyst_next_best_action(lead)
    if nba["nba"] == "sms":
        msg = await (closer_sms(lead) if nba.get("template")=="closer" else nurturer_sms(lead))
        ok, why = await compliance_guard(lead, "sms", msg)
        if ok:
            await send_sms(lead["phone"], msg)

class LeadIn(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    timezone: str | None = None
    consent_sms: bool = False
    consent_email: bool = False
    consent_voice: bool = False
    dnc: bool = False

@app.post("/leads")
async def create_lead(lead: LeadIn, tasks: BackgroundTasks):
    if not lead.phone and not lead.email:
        raise HTTPException(400, "Need phone or email")
    lead_id = f"lead_{len(LEADS)+1}"
    LEADS[lead_id] = lead.dict()
    if not LEADS[lead_id].get("timezone"):
        LEADS[lead_id]["timezone"] = DEFAULT_TZ
    tasks.add_task(orchestrate_outbound, lead_id)
    return {"id": lead_id, "lead": LEADS[lead_id]}

@app.post("/webhooks/twilio/sms")
async def receive_sms(request: Request):
    form = dict(await request.form())
    from_num = form.get("From")
    body = (form.get("Body") or "").strip()
    lead_id = next((k for k,v in LEADS.items() if v.get("phone")==from_num), None)
    if not lead_id: return "OK"
    lead = LEADS[lead_id]

    if contains_optout(body):
        lead["consent_sms"] = False
        lead["dnc"] = True
        return "OK"

    if body.lower() in ("yes","y","ok"):
        msg = await closer_sms(lead)
        ok, _ = await compliance_guard(lead, "sms", msg)
        if ok: await send_sms(lead["phone"], msg)
    else:
        ack = ("Thanks! What’s your #1 growth focus (calls, foot traffic, or online leads)? "
               "Reply STOP to opt out.")
        ok, _ = await compliance_guard(lead, "sms", ack)
        if ok: await send_sms(lead["phone"], ack)
    return "OK"

@app.post("/webhooks/sendgrid/inbound")
async def receive_email(request: Request):
    data = await request.json()
    email_from = data.get("from")
    subject = data.get("subject","")
    body = data.get("text","")
    lead_id = next((k for k,v in LEADS.items() if v.get("email")==email_from), None)
    if not lead_id: return "OK"

    if "unsubscribe" in (body or "").lower():
        LEADS[lead_id]["consent_email"] = False
        LEADS[lead_id]["dnc"] = True
        return "OK"

    reply_subject = f"Re: {subject or 'Your quick plan'}"
    reply_body = ("Appreciate the reply—here’s a 7-day promo plan tailored for quick wins. "
                  "Want me to implement it this week?")
    await send_email(email_from, reply_subject, reply_body)
    return "OK"

from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("ui.html", {"request": request, "branding": BRANDING})

@app.get("/ui", response_class=HTMLResponse)
async def ui(request: Request):
    return templates.TemplateResponse("ui.html", {"request": request, "branding": BRANDING})

@app.get("/ui/leads", response_class=HTMLResponse)
async def ui_leads(request: Request):
    rows = []
    for k,v in list(LEADS.items())[::-1][:200]:
        rows.append(f"<tr><td>{v.get('full_name') or ''}</td><td>{v.get('company') or ''}</td><td>{v.get('phone') or ''}</td><td>{v.get('email') or ''}</td><td>{'Yes' if v.get('consent_sms') else 'No'}</td></tr>")
    html = "<table><thead><tr><th>Name</th><th>Company</th><th>Phone</th><th>Email</th><th>SMS Consent</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    return HTMLResponse(html)

@app.post("/ui/generate", response_class=HTMLResponse)
async def ui_generate(request: Request):
    data = await request.form()
    query = data.get("query") or "pharmacy"
    location_text = data.get("location_text") or "Wapakoneta, OH"
    latlng = data.get("latlng") or "40.5670,-84.1936"
    limit = int(data.get("limit") or 20)

    from .routers.verify_and_prospect import generate_leads, LeadGenIn
    payload = LeadGenIn(vertical="local_business", query=query, location_text=location_text, latlng=latlng, limit=limit)
    res = await generate_leads(payload)
    return HTMLResponse(f"Created {res['count']} leads. Refreshing list…")

@app.get("/healthz")
async def healthz():
    return {"ok": True, "time": datetime.datetime.utcnow().isoformat()}

from .routers.verify_and_prospect import router as prospect_router
from .routers.import_csv import router as import_router
app.include_router(prospect_router)
app.include_router(import_router)