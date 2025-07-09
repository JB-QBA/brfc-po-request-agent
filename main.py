
from fastapi import FastAPI, Request
import json
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()
user_states = {}
uploaded_quotes = {}

SERVICE_ACCOUNT_FILE = "/etc/secrets/winged-pen-413708-e9544129b499.json"
SPREADSHEET_NAME = "FY2025 Budget for Analysis"
SHEET_TAB_NAME = "FY2025Budget"
XERO_TAB_NAME = "Xero"

special_users = {
    "finance@bahrainrfc.com": "Johann",
    "generalmanager@bahrainrfc.com": "Paul"
}

other_managers = {
    "hr@bahrainrfc.com": "Human Capital",
    "facilities@bahrainrfc.com": "Facilities",
    "clubhouse@bahrainrfc.com": "Clubhouse",
    "sports@bahrainrfc.com": "Sports",
    "marketing@bahrainrfc.com": "Marketing",
    "sponsorship@bahrainrfc.com": "Sponsorship"
}

all_departments = [
    "Clubhouse", "Facilities", "Finance", "Front Office",
    "Human Capital", "Management", "Marketing", "Sponsorship", "Sports"
]

greeting_triggers = ["hi", "hello", "hey", "howzit", "salam"]

def get_gsheet():
    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc

def get_cost_items_for_department(department: str) -> list:
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    return list(set(row[3] for row in rows if len(row) > 3 and row[1].strip().lower() == department.lower() and row[3].strip()))

def get_account_tracking_and_total(cost_item: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    for row in rows:
        if len(row) >= 6 and row[1].strip().lower() == department.lower() and row[3].strip().lower() == cost_item.lower():
            account = row[0].strip()
            tracking = row[4].strip()
            total = row[17].replace(",", "").strip()
            return account, tracking, total
    return None, None, "0"

def get_account_total(account: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    total = 0.0
    for row in rows:
        if len(row) > 17 and row[0].strip().lower() == account.lower() and row[1].strip().lower() == department.lower():
            try:
                val = float(row[17].replace(",", "").strip())
                total += val
            except:
                continue
    return total

def get_ytd_actuals(account: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(XERO_TAB_NAME)
    rows = sheet.get_all_values()[3:]
    total = 0.0
    for row in rows:
        if len(row) > 14 and row[1].strip().lower() == account.lower() and row[14].strip().lower() == department.lower():
            try:
                val = float(row[10].replace(",", "").strip())
                total += val
            except:
                continue
    return total

@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    message = body.get("message", {})
    sender = message.get("sender", {})
    email = sender.get("email", "").lower()
    full_name = sender.get("displayName", "there")
    first_name = full_name.split()[0]
    text = message.get("text", "").strip().lower()
    state = user_states.get(email)

    if any(text.startswith(trigger) for trigger in greeting_triggers):
        if email in special_users:
            user_states[email] = "awaiting_department"
            return {"text": f"Hi {first_name},\nWhat department would you like to raise a PO for?\nOptions: {', '.join(all_departments)}"}
        elif email in other_managers:
            department = other_managers[email]
            user_states[email] = "awaiting_cost_item"
            user_states[f"{email}_department"] = department
            items = get_cost_items_for_department(department)
            return {"text": f"Hi {first_name},\nHere are the available cost items for {department}:\n" + "\n".join([f"• {item}" for item in items])}

    if state == "awaiting_department":
        if text.title() in all_departments:
            department = text.title()
            user_states[email] = "awaiting_cost_item"
            user_states[f"{email}_department"] = department
            items = get_cost_items_for_department(department)
            return {"text": f"Thanks {first_name}. Here are the cost items for {department}:\n" + "\n".join([f"• {item}" for item in items])}
        return {"text": f"Department not recognized. Choose from: {', '.join(all_departments)}"}

    if state == "awaiting_cost_item":
        department = user_states.get(f"{email}_department")
        account, tracking, item_total = get_account_tracking_and_total(text, department)
        if account:
            account_total = get_account_total(account, department)
            actuals = get_ytd_actuals(account, department)
            user_states[email] = "awaiting_quote_upload"
            user_states[f"{email}_cost_item"] = text.title()
            user_states[f"{email}_account"] = account
            user_states[f"{email}_tracking"] = tracking
            return {
                "text": (
                    f"✅ Great, you've selected: {text.title()} under {department}\n\n"
                    f"📊 Budgeted for item: {int(float(item_total)):,}\n"
                    f"📊 Budgeted total for account '{account}': {int(account_total):,}\n"
                    f"📊 YTD actuals for '{account}': {int(actuals):,}\n\n"
                    "You can now upload the quote here to continue – Just a few more questions and we're done."
                )
            }

    return {"text": "I'm not sure how to help with that. Start with 'Hi' or choose a department."}
