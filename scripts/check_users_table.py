import os
from dotenv import load_dotenv
load_dotenv('.env')
import psycopg2

url = os.getenv('DATABASE_URL') or os.getenv('SUPABASE_DB_URL')
conn = psycopg2.connect(url)
cur = conn.cursor()

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position")
print("=== COLUMNS ===")
for row in cur.fetchall():
    print(row)

cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename='users'")
print("\n=== INDEXES ===")
for row in cur.fetchall():
    print(row)

cur.execute("SELECT conname, contype, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='users'::regclass")
print("\n=== CONSTRAINTS ===")
for row in cur.fetchall():
    print(row)

conn.close()
