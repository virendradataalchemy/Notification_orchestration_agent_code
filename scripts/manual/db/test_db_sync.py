import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL').replace('postgresql+asyncpg', 'postgresql')

conn = psycopg2.connect(db_url)
cur = conn.cursor()

cur.execute("SELECT id, tenant_id, email, username, is_active FROM tenant_users")
print("Users:", cur.fetchall())

cur.execute("SELECT * FROM tenant_invitations")
print("Invitations:", cur.fetchall())

cur.execute("SELECT * FROM tenant_invitations LIMIT 1")
print("All Invitations:", cur.fetchall())
