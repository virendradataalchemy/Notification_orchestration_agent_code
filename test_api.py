from fastapi.testclient import TestClient
from src.main import app
import json

client = TestClient(app)

def test_endpoint():
    response = client.get("/api/tenant-dashboard/tenant/demo_corp/marketing-threaded-activity?limit=12", headers={
        "X-Admin-Key": "your-secret-key-change-this-in-production"
    })
    print("STATUS", response.status_code)
    try:
        print(json.dumps(response.json(), indent=2))
    except:
        print(response.text)

    response2 = client.get("/api/tenant-dashboard/tenant/demo_corp/marketing-activity?limit=12", headers={
        "X-Admin-Key": "your-secret-key-change-this-in-production"
    })
    print("STATUS", response2.status_code)

if __name__ == "__main__":
    test_endpoint()