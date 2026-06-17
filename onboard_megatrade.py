"""Drive the full MEGATRADE onboarding flow against the local backend."""
import sys, time, json
import requests

BASE = "http://localhost:8000/api/v1"
TENANT_ID = "a480c09a-6cf4-463d-a052-53e01707a4b2"  # existing test-corp in 5433
ADMIN_EMAIL = "onboarder@testcorp.com"
ADMIN_PW = "Admin123!pass"
TH = {"X-Tenant-ID": TENANT_ID}  # tenant header needed even for login

def pp(label, r):
    try:
        body = r.json()
    except Exception:
        body = r.text
    print(f"[{r.status_code}] {label}: {json.dumps(body)[:400]}")
    return body

s = requests.Session()

# 1. Admin user (open bootstrap; ignore 409 if already created on a rerun)
r = s.post(f"{BASE}/tenants/{TENANT_ID}/users", headers=TH, json={
    "email": ADMIN_EMAIL, "full_name": "Onboarder", "password": ADMIN_PW,
    "role_names": ["platform_admin"],
})
pp("create admin user", r)

# 2. Login (X-Tenant-ID required)
r = s.post(f"{BASE}/auth/login", headers=TH, json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
b = pp("login", r)
if r.status_code != 200:
    print("LOGIN FAILED — aborting"); sys.exit(1)
token = b["data"]["access_token"] if "data" in b else b["access_token"]
H = {"Authorization": f"Bearer {token}", "X-Tenant-ID": TENANT_ID}
print("HEADERS:", {k: (v[:24]+'...' if k=='Authorization' else v) for k,v in H.items()})

# 4. Create connection — backend runs in Docker, so host = host.docker.internal
# Soft-deleted rows keep the name reserved, so use a unique name per run.
CONN_NAME = f"MEGATRADE Demo MSSQL {int(time.time())}"
r = s.post(f"{BASE}/connections", headers=H, json={
    "name": CONN_NAME, "db_type": "mssql",
    "host": "host.docker.internal", "port": 1433, "database_name": "MEGATRADE_DEMO",
    "username": "sa", "password": "YourPassword123!", "is_tls": False,
})
b = pp("create connection", r)
conn_id = b["data"]["id"]

# 5. Test connection
r = s.post(f"{BASE}/connections/{conn_id}/test", headers=H)
pp("test connection", r)

# 6. Trigger discovery
r = s.post(f"{BASE}/connections/{conn_id}/discover", headers=H, json={"mode": "full"})
b = pp("trigger discovery", r)
job_id = b["data"]["job_id"]

# 7. Poll status (job_id is a query param; fields are stage/pct; terminal=done/error)
print("--- polling discovery (max 5 min) ---")
for i in range(60):
    r = s.get(f"{BASE}/connections/{conn_id}/discover/status",
              headers=H, params={"job_id": job_id})
    b = (r.json() or {}).get("data", {}) or {}
    stage = b.get("stage"); pct = b.get("pct"); detail = b.get("detail", "")
    print(f"  t={i*5}s [{r.status_code}] stage={stage} pct={pct} {detail}")
    if stage in ("done", "error"):
        print("FINAL:", json.dumps(b)[:600]); break
    time.sleep(5)

# 8. Results
print("\n=== ENTITIES ===")
pp("entities", s.get(f"{BASE}/semantic/entities", headers=H))
print("\n=== KPIs ===")
pp("kpis", s.get(f"{BASE}/semantic/kpis", headers=H))
print("\n=== TOOLS ===")
pp("tools", s.get(f"{BASE}/tools", headers=H))
