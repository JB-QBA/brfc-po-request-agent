from fastapi import FastAPI, Request
import json

app = FastAPI()

user_department_mapping = {
    "finance@bahrainrfc.com": "Finance",
    # Add others here later
}

@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender_info = body.get("message", {}).get("sender", {})
    sender_name = sender_info.get("displayName", "there").split()[0]
    sender_email = sender_info.get("email", "").lower()

    # Determine department
    department = user_department_mapping.get(sender_email, "your department")

    # Reply
    return {
        "text": f"Hi {sender_name},\nAre we getting the PO details for the {department} department?"
    }
