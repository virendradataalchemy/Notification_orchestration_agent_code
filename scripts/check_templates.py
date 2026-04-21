import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='notifications', user='postgres', password='Myfirst@1605')
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='templates'")
print('Columns:', [r[0] for r in cur.fetchall()])
cur.execute('SELECT * FROM templates LIMIT 10')
print('Templates:', cur.fetchall())
conn.close()
