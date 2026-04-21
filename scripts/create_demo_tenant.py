"""Create demo_corp tenant in the database."""
import psycopg2
import hashlib
import json
from datetime import datetime

conn = psycopg2.connect(host='localhost', port=5432, dbname='notifications', user='postgres', password='Myfirst@1605')
cur = conn.cursor()

api_key = "sk_live_demo_corp_m1UxVyIM67QKaSxTTGYqg244DObbChfZ78Te09o7Wy0"
api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
api_key_prefix = api_key[:16]

config = json.dumps({
    "tier": "enterprise",
    "monthly_quota": None  # unlimited
})

now = datetime.utcnow()

cur.execute("""
    INSERT INTO tenants (id, name, admin_email, admin_name, status, api_key_hash, api_key_prefix, config, created_at, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET status='active', config=%s, updated_at=%s
""", (
    'demo_corp', 'Demo Corporation', 'admin@democorp.com', 'Demo Admin',
    'active', api_key_hash, api_key_prefix, config, now, now,
    config, now
))

conn.commit()
print("Tenant demo_corp created/updated successfully.")
print(f"  Tier: enterprise (unlimited quota)")
print(f"  API Key: {api_key}")

cur.execute("SELECT id, name, status, config FROM tenants")
for row in cur.fetchall():
    print("DB row:", row)

conn.close()
