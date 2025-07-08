from fastapi import FastAPI, Request
import json
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()
user_states = {}

# Hardcoded config
SERVICE_ACCOUNT_FILE = "/etc/secrets/winged-pen-413708-e9544129b499.json"
SPREADSHEET_NAME = "FY2025 Budget for Analysis"
SHEET_TAB_NAME = "FY2025Budget"
special_users = {
    "finance@bahrainrfc.com": "Johann",
    "generalmanager@bahrainrfc.com": "Paul"
}
all_departments = [
    "Clubhouse", "Facilities", "Finance", "Front Office",
    "Human Capital", "Management", "Marketing", "Sponsorship", "Sports"
]
greeting_triggers = ["hi", "hello", "hey", "howzit", "salam"]

def get_cost_items_for_department(department: str) -> list:
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    gc = gspread.authorize(creds)
    sheet = gc.open(SPREADSHEET_NAME).worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[90:]
    cost_items = [row[3] for row in rows if len(row) > 3 and row[1].strip().lower() == department.lower()]
    return list(set(filter(None, cost_items)))

def get_budget_for_cost_item(department: str, item: str) -> str:
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    gc = gspread.authorize(creds)
    sheet = gc.open(SPREADSHEET_NAME).worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[90:]
    for row in rows:
        if len(row) > 17 and row[1].strip().lower() == department.lower() and row[3].strip().lower() == item.lower():
            return row[17]  # Column R = index 17
    return "not found"

@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender = body.get("message", {}).get("sender", {})
    full_name = sender.get("displayName", "there")
    sender_first_name = full_name.split()[0]
    sender_email = sender.get("email", "").lower()
    message_text = body.get("message", {}).get("text", "").strip().lower()
    user_state = user_states.get(sender_email)

    if any(message_text.startswith(greet) for greet in greeting_triggers):
        if sender_email in special_users:
            user_states[sender_email] = "awaiting_department_selection"
            return {
                "text": f"Hi {sender_first_name},\nWhat department would you like to raise a PO for?\nOptions: {', '.join(all_departments)}"
            }
        else:
            user_states[sender_email] = "awaiting_department_confirmation"
            return {
                "text": f"Hi {sender_first_name},\nAre we getting the PO details for the Finance department?"
            }

    if user_state == "awaiting_department_confirmation":
        if message_text in ["yes", "correct"]:
            user_states[sender_email] = "awaiting_cost_item_choice"
            user_states[f"{sender_email}_department"] = "Finance"
            return {
                "text": "Thanks for confirming.\nDo you know the cost item or would you like to choose from the list?\nOptions:\n- Yes, I know it\n- I’ll choose from list"
            }
        else:
            user_states[sender_email] = "awaiting_manual_department"
            return {"text": "To which department does this PO belong?"}

    if user_state == "awaiting_department_selection":
        if message_text.title() in all_departments:
            user_states[sender_email] = "awaiting_cost_item_choice"
            user_states[f"{sender_email}_department"] = message_text.title()
            return {
                "text": f"Thanks for confirming the department: {message_text.title()}.\nDo you know the cost item or would you like to choose from the list?\nOptions:\n- Yes, I know it\n- I’ll choose from list"
            }
        else:
            return {"text": f"That department isn't recognized. Please choose from:\n{', '.join(all_departments)}"}

    if user_state == "awaiting_manual_department":
        if message_text.title() in all_departments:
            user_states[sender_email] = "awaiting_cost_item_choice"
            user_states[f"{sender_email}_department"] = message_text.title()
            return {
                "text": f"Got it. Working with the {message_text.title()} department.\nDo you know the cost item or would you like to choose from the list?"
            }
        else:
            return {"text": f"Please reply with a valid department name.\nOptions: {', '.join(all_departments)}"}

    if user_state == "awaiting_cost_item_choice":
        if message_text in ["yes", "i know it", "i'll type it"]:
            user_states[sender_email] = "awaiting_cost_item_name"
            return {"text": "Great, please type the cost item you'd like this PO to be allocated against."}
        else:
            department = user_states.get(f"{sender_email}_department", "Finance")
            cost_items = get_cost_items_for_department(department)
            reply = f"Here are the available cost items for {department}:\n- " + "\n- ".join(cost_items[:10])
            return {"text": reply}

    if user_state == "awaiting_cost_item_name":
        department = user_states.get(f"{sender_email}_department", "Finance")
        cost_item = message_text.strip()
        user_states[f"{sender_email}_cost_item"] = cost_item
        budget = get_budget_for_cost_item(department, cost_item)
        user_states[sender_email] = "awaiting_quote"
        return {
            "text": f"The total budgeted amount for '{cost_item}' under {department} is: {budget}.\nPlease upload or paste the quote details to continue."
        }

    return {
        "text": "I'm not sure how to help with that. Start again with 'Hi' or choose a department."
    }
