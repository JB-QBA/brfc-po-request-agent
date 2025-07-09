from fastapi import FastAPI, Request
import json
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()
user_states = {}

# --- Config ---
SERVICE_ACCOUNT_FILE = "/etc/secrets/winged-pen-413708-e9544129b499.json"
SPREADSHEET_ID = "1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8"
SHEET_TAB_NAME = "FY2025Budget"

special_users = {
    "finance@bahrainrfc.com": "Johann",
    "generalmanager@bahrainrfc.com": "Paul"
}

all_departments = [
    "Clubhouse", "Facilities", "Finance", "Front Office",
    "Human Capital", "Management", "Marketing", "Sponsorship", "Sports"
]

# --- Triggers ---
greeting_triggers = ["hi", "hello", "hey", "howzit", "salam"]

# --- Helper: Get cost items for department ---
def get_cost_items_for_department(department: str) -> list:
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/spreadsheets"
        ]
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]  # Start from row 2
    cost_items = [row[3] for row in rows if len(row) > 3 and row[1].strip().lower() == department.lower()]
    return list(set(filter(None, cost_items)))

# --- Helper: Get budget total for cost item ---
def get_budget_total_for_item(department: str, cost_item: str) -> str:
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/spreadsheets"
        ]
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    for row in rows:
        if (
            len(row) >= 18
            and row[1].strip().lower() == department.lower()
            and row[3].strip().lower() == cost_item.lower()
        ):
            return row[17]  # Column R = index 17
    return "Not found"

# --- Route ---
@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender = body.get("message", {}).get("sender", {})
    sender_name = sender.get("displayName", "there").split()[0]  # First name only
    sender_email = sender.get("email", "").lower()
    message_text = body.get("message", {}).get("text", "").strip().lower()
    user_state = user_states.get(sender_email)

    # Greet and initiate
    if any(message_text.startswith(greet) for greet in greeting_triggers):
        if sender_email in special_users:
            user_states[sender_email] = "awaiting_department_selection"
            return {
                "text": f"Hi {sender_name},\nWhat department would you like to raise a PO for?\nOptions: {', '.join(all_departments)}"
            }
        else:
            # For non-special users, infer department and show cost items directly
            default_dept = "Finance"  # Optionally adjust per user
            user_states[sender_email] = "awaiting_cost_item_selection"
            user_states[f"{sender_email}_department"] = default_dept
            cost_items = get_cost_items_for_department(default_dept)
            reply = f"Hi {sender_name}, here are the available cost items for {default_dept}:\n- " + "\n- ".join(cost_items)
            return {"text": reply}

    # Special users choosing department
    if user_state == "awaiting_department_selection":
        if message_text.title() in all_departments:
            user_states[sender_email] = "awaiting_cost_item_selection"
            user_states[f"{sender_email}_department"] = message_text.title()
            cost_items = get_cost_items_for_department(message_text.title())
            reply = f"Thanks! Here are the cost items for {message_text.title()}:\n- " + "\n- ".join(cost_items)
            return {"text": reply}
        else:
            return {"text": f"That department isn't recognized. Choose from:\n{', '.join(all_departments)}"}

    # Receiving cost item selection
    if user_state == "awaiting_cost_item_selection":
        department = user_states.get(f"{sender_email}_department", "Finance")
        cost_items = get_cost_items_for_department(department)
        match = next((item for item in cost_items if item.lower() == message_text), None)
        if match:
            user_states[sender_email] = "awaiting_quote"
            total = get_budget_total_for_item(department, match)
            return {
                "text": f"✅ Cost item confirmed: {match}\n📊 Budgeted Total: {total}\n\n📎 Please upload the quote for this PO request."
            }
        else:
            return {
                "text": f"Sorry, that doesn’t match any cost items in {department}.\nTry again or pick from:\n- " + "\n- ".join(cost_items)
            }

    # Fallback
    return {"text": "I'm not sure how to help with that. Please start with 'Hi' or pick a department."}
