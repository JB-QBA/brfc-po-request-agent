from fastapi import FastAPI, Request
import json
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()
user_states = {}

# Hardcoded config
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
greeting_triggers = ["hi", "hello", "hey", "howzit", "salam"]

def get_first_name(full_name: str) -> str:
    return full_name.split()[0]

def get_sheet():
    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_TAB_NAME)

def get_cost_items_for_department(department: str) -> list:
    sheet = get_sheet()
    rows = sheet.get_all_values()[1:]  # Starting at row 2 (after header)
    return list(set([
        row[3] for row in rows if len(row) > 3 and row[1].strip().lower() == department.lower()
    ]))

def get_budget_total_for_cost_item(department: str, cost_item: str) -> str:
    sheet = get_sheet()
    rows = sheet.get_all_values()[1:]  # Starting at row 2 (after header)
    for row in rows:
        if (
            len(row) > 17 and
            row[1].strip().lower() == department.lower() and
            row[3].strip().lower() == cost_item.lower()
        ):
            return row[17]
    return None

@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender = body.get("message", {}).get("sender", {})
    sender_name = sender.get("displayName", "there")
    sender_email = sender.get("email", "").lower()
    message_text = body.get("message", {}).get("text", "").strip().lower()
    user_state = user_states.get(sender_email)

    first_name = get_first_name(sender_name)

    if any(message_text.startswith(greet) for greet in greeting_triggers):
        if sender_email in special_users:
            user_states[sender_email] = "awaiting_department_selection"
            return {
                "text": f"Hi {first_name},\nWhat department would you like to raise a PO for?\nOptions: {', '.join(all_departments)}"
            }
        else:
            user_states[sender_email] = "awaiting_department_confirmation"
            return {
                "text": f"Hi {first_name},\nAre we getting the PO details for the Finance department?"
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
            return {
                "text": f"Here are the available cost items for {department}:\n- " + "\n- ".join(cost_items[:10])
            }

    if user_state == "awaiting_cost_item_name":
        department = user_states.get(f"{sender_email}_department", "Finance")
        cost_items = get_cost_items_for_department(department)
        matched_items = [item for item in cost_items if message_text in item.lower()]
        if matched_items:
            selected_item = matched_items[0]
            user_states[sender_email] = "awaiting_quote_upload"
            user_states[f"{sender_email}_cost_item"] = selected_item
            total_budget = get_budget_total_for_cost_item(department, selected_item)
            return {
                "text": f"Cost item '{selected_item}' confirmed for {department}.\nBudgeted total: {total_budget or 'not found'}\n\nPlease upload or paste the quote for this PO."
            }
        else:
            return {
                "text": f"That cost item wasn't recognized for {department}.\nHere are a few options you can choose from:\n- " + "\n- ".join(cost_items[:10])
            }

    return {
        "text": "I'm not sure how to help with that. Start again with 'Hi' or choose a department."
    }
