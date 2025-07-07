from fastapi import FastAPI, Request
from pydantic import BaseModel
import json

app = FastAPI()

# Hardcoded user and department for now
USER_PROFILE = {
    "finance@bahrainrfc.com": {
        "name": "Johann",
        "department": "Finance"
    }
}

@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender_info = body.get("message", {}).get("sender", {})
    user_email = sender_info.get("email", "")
    user_name = sender_info.get("displayName", "there")
    message_text = body.get("message", {}).get("text", "").lower().strip()

    # Get department from known users
    user_data = USER_PROFILE.get(user_email)
    if not user_data:
        return {"text": f"Hi {user_name}, I don't recognize your account yet. Please contact admin."}

    name = user_data["name"]
    department = user_data["department"]

    # Store basic conversational state in message_text
    if message_text in ["hi", "hello"]:
        return {"text": f"Hi {name},\nAre we getting the PO details for the {department} department?"}
    elif message_text in ["yes", "yes we are"]:
        return {"text": f"Great, let’s continue with the PO request for the {department} department."}
    elif message_text in ["no", "not finance", "no we're not"]:
        return {"text": "To which department does this PO belong?"}
    else:
        # Catch-all for now
        return {"text": f"Thanks {name}, I’ve noted: '{message_text}'. Let me know if that’s the department or if you need help."}
