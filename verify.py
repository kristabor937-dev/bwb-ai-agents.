import os, re, socket
from typing import Tuple, Dict, Any
import httpx
import dns.resolver

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")

EMAIL_REGEX = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)
DISPOSABLE_DOMAINS = {"mailinator.com","guerrillamail.com","10minutemail.com"}

async def verify_phone_e164(client: httpx.AsyncClient, phone: str) -> Dict[str,Any]:
    try:
        url = f"https://lookups.twilio.com/v2/PhoneNumbers/{phone}?type=carrier,caller-name"
        r = await client.get(url, auth=(TWILIO_SID, TWILIO_TOKEN), timeout=20)
        data = r.json() if r.status_code < 400 else {"error": r.text}
        status = "valid" if r.status_code < 400 else "invalid"
        line_type = data.get("carrier",{}).get("type")
        confidence = 0.9 if status=="valid" else 0.2
        if line_type == "voip": confidence = min(confidence, 0.6)
        return {"status": status, "reason": f"line_type={line_type}", "confidence": confidence, "raw": data}
    except Exception as e:
        return {"status":"unknown","reason":f"lookup_err:{type(e).__name__}","confidence":0.4,"raw":{}}

def mx_records(domain: str) -> bool:
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        return len(answers) > 0
    except Exception:
        return False

async def smtp_probe(domain: str, email: str) -> Tuple[str,str]:
    try:
        answers = dns.resolver.resolve(domain, 'MX')
        host = str(sorted(answers, key=lambda r: int(r.preference))[0].exchange)
        s = socket.create_connection((host, 25), 8)
        s.recv(512)
        s.send(b"HELO bwbexpress.com\r\n"); s.recv(512)
        s.send(b"MAIL FROM:<verify@bwbexpress.com>\r\n"); s.recv(512)
        s.send(f"RCPT TO:<{email}>\r\n".encode()); resp = s.recv(512)
        s.send(b"QUIT\r\n"); s.close()
        code = resp[:3].decode(errors="ignore")
        if code.startswith("250"): return "valid","smtp_ok"
        if code.startswith("550"): return "invalid","smtp_no_mailbox"
        return "risky","smtp_uncertain"
    except Exception as e:
        return "unknown", f"smtp_err:{type(e).__name__}"

async def verify_email(client: httpx.AsyncClient, email: str) -> Dict[str,Any]:
    if not EMAIL_REGEX.match(email):
        return {"status":"invalid","reason":"bad_format","confidence":0.0,"raw":{}}
    domain = email.split("@")[-1].lower()
    if domain in DISPOSABLE_DOMAINS:
        return {"status":"invalid","reason":"disposable","confidence":0.1,"raw":{}}
    if not mx_records(domain):
        return {"status":"invalid","reason":"no_mx","confidence":0.1,"raw":{}}
    status, why = await smtp_probe(domain, email)
    conf = {"valid":0.9,"risky":0.6,"unknown":0.4,"invalid":0.1}[status]
    return {"status":status,"reason":why,"confidence":conf,"raw":{}}