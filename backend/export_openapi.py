import json
from app.main import app

def export_openapi():
    openapi_schema = app.openapi()
    with open("openapi.json", "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2)
    print("OpenAPI schema exported to openapi.json")

if __name__ == "__main__":
    export_openapi()
