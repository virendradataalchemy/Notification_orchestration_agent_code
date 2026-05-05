import asyncio
import asyncpg

async def create_db():
    try:
        # Connect to the default 'postgres' database
        conn = await asyncpg.connect(
            user='postgres',
            password='postgres',
            database='postgres',
            host='127.0.0.1'
        )
        try:
            # Check if database exists
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'notification_db'")
            if not exists:
                # CREATE DATABASE cannot be run inside a transaction block
                await conn.execute('CREATE DATABASE notification_db')
                print("Database 'notification_db' created successfully.")
            else:
                print("Database 'notification_db' already exists.")
        finally:
            await conn.close()
    except Exception as e:
        print(f"Error creating database: {e}")

if __name__ == "__main__":
    asyncio.run(create_db())
