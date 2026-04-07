import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='notifications', user='postgres', password='Myfirst@1605')
cur = conn.cursor()

# Check columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='tenants'")
print("Columns:", [r[0] for r in cur.fetchall()])

# Check tenant data
cur.execute("SELECT * FROM tenants LIMIT 5")
rows = cur.fetchall()
print("Tenants:", rows)

conn.close()
