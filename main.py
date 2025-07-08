from fastapi import FastAPI, Request
import json

app = FastAPI()

# Known user profiles
USER_PROFILE = {
    "finance@bahrainrfc.com": {
        "name": "Johann",
        "role": "admin"
    },
    "generalmanager@bahrainrfc.com": {
        "name": "Paul",
        "role": "admin"
    },
    # Example of non-admin user
    "someoneelse@bahrainrfc.com": {
        "name": "Jane",
        "role": "user",
        "department": "Marketing"
    }
}

ALL_DEPARTMENTS = [
    "Clubhouse", "Facilities", "Finance", "Front Office",
    "Human Capital", "Management", "Marketing", "Sponsorship", "Sports"
]

@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender = body.get("message", {}).get("sender", {})
    email = sender.get("email", "")
    name = sender.get("displayName", "there")
    message_text = body.get("message", {}).get("text", "").lower().strip()

    user = USER_PROFILE.get(email)

    if not user:
        return {"text": f"Hi {name}, I don’t recognize your account. Please contact admin."}

    is_admin = user.get("role") == "admin"

    if message_text in ["hi", "hello", "hey", "howzit", "salam"]:
        if is_admin:
            return {"text": f"Hi {user['name']},\nWhat department would you like to raise a PO for?"}
        else:
            dept = user.get("department")
            return {"text": f"Hi {user['name']},\nAre we getting the PO details for the {dept} department?"}

    elif message_text in ["yes", "yes we are"]:
        if is_admin:
            return {"text": "Great — just let me know which department you'd like to proceed with."}
        else:
            return {"text": f"Great, let’s continue with the PO request for the {user['department']} department."}

    elif message_text in ["no", "not finance", "no we're not"]:
        return {"text": "To which department does this PO belong?"}

    # Match valid department if given
    elif message_text.title() in ALL_DEPARTMENTS:
        return {"text": f"Got it. Proceeding with the PO request for the {message_text.title()} department."}

    # Catch-all
    else:
        return {"text": f"Thanks {user['name']}, I’ve noted: '{message_text}'. Let me know if that’s the department or if you need help."}
