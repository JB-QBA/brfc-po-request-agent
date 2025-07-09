from fastapi import FastAPI, Request
import json
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

app = FastAPI()
user_states = {}

# CONFIGURATION
SERVICE_ACCOUNT_FILE = "/etc/secrets/winged-pen-413708-e9544129b499.json"
SPREADSHEET_NAME = "FY2025 Budget for Analysis"
SHEET_TAB_NAME = "FY2025Budget"
XERO_TAB_NAME = "Xero"
CHAT_SPACE_ID = "spaces/AAQAs4dLeAY"

special_users = {
    "finance@bahrainrfc.com": "Johann",
    "generalmanager@bahrainrfc.com": "Paul"
}

dept_users = {
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

# GOOGLE AUTH

def get_gsheet():
    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc

# HELPERS

def get_cost_items_for_department(department: str) -> list:
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    return list(set(row[3] for row in rows if len(row) > 3 and row[1].strip().lower() == department.lower()))

def get_account_and_tracking(cost_item: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    for row in rows:
        if len(row) >= 6 and row[3].strip().lower() == cost_item.lower() and row[1].strip().lower() == department.lower():
            account = row[0].strip()
            tracking = row[4].strip()
            total_budget = row[17].replace(",", "") if len(row) > 17 else "0"
            finance_ref = row[4] if len(row) > 4 else ""
            return account, tracking, total_budget, finance_ref
    return None, None, "0", ""

def get_total_budget_for_account(account: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    total = 0.0
    for row in rows:
        if len(row) >= 18 and row[0].strip().lower() == account.lower() and row[1].strip().lower() == department.lower():
            try:
                value = float(row[17].replace(",", "").strip())
                total += value
            except:
                pass
    return total

def get_actuals_for_account(account: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(XERO_TAB_NAME)
    rows = sheet.get_all_values()[3:]
    total = 0.0
    for row in rows:
        if len(row) >= 15 and row[1].strip().lower() == account.lower() and row[14].strip().lower() == department.lower():
            try:
                val = float(row[10].replace(",", "").strip())
                total += val
            except:
                pass
    return total

# MAIN BOT HANDLER

@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender = body.get("message", {}).get("sender", {})
    sender_email = sender.get("email", "").lower()
    full_name = sender.get("displayName", "there")
    first_name = full_name.split()[0]
    message_text = body.get("message", {}).get("text", "").strip().lower()
    user_state = user_states.get(sender_email)

    # Greeting flow
    if any(message_text.startswith(greet) for greet in greeting_triggers):
        if sender_email in special_users:
            user_states[sender_email] = "awaiting_department_selection"
            return {
                "text": f"Hi {first_name},\nWhat department would you like to raise a PO for?\nOptions: {', '.join(all_departments)}"
            }
        elif sender_email in dept_users:
            department = dept_users[sender_email]
            user_states[sender_email] = "awaiting_cost_item"
            user_states[f"{sender_email}_department"] = department
            items = get_cost_items_for_department(department)
            item_list = "\n- ".join(items)
            return {
                "text": f"Hi {first_name},\nHere are the available cost items for {department}:\n- {item_list}"
            }

    # Department selection
    if user_state == "awaiting_department_selection":
        if message_text.title() in all_departments:
            department = message_text.title()
            user_states[sender_email] = "awaiting_cost_item"
            user_states[f"{sender_email}_department"] = department
            items = get_cost_items_for_department(department)
            item_list = "\n- ".join(items)
            return {
                "text": f"Thanks {first_name}. Here are the cost items for {department}:\n- {item_list}"
            }
        else:
            return {"text": f"Department not recognized. Choose from: {', '.join(all_departments)}"}

    # Cost item selection
    if user_state == "awaiting_cost_item":
        department = user_states.get(f"{sender_email}_department", "Finance")
        cost_item = message_text.title()
        account, tracking, cost_item_total, finance_ref = get_account_and_tracking(cost_item, department)
        if account:
            account_total = get_total_budget_for_account(account, department)
            ytd_actuals = get_actuals_for_account(account, department)

            user_states[sender_email] = "awaiting_quote"
            user_states[f"{sender_email}_cost_item"] = cost_item
            user_states[f"{sender_email}_account"] = account
            user_states[f"{sender_email}_tracking"] = tracking
            user_states[f"{sender_email}_finance_ref"] = finance_ref
            return {
                "text": (
                    f"✅ Great, you've selected: {cost_item} under {department}\n\n"
                    f"📊 Budgeted for item: {int(float(cost_item_total)):,}\n"
                    f"📊 Budgeted total for account '{account}': {int(account_total):,}\n"
                    f"📊 YTD actuals for '{account}': {int(ytd_actuals):,}\n\n"
                    "You can now upload the quote here to continue - Just a few more questions and we're done."
                )
            }
        else:
            return {"text": f"That cost item wasn't recognized for {department}. Try again."}

    # Default fallback
    return {"text": "I'm not sure how to help with that. Start with 'Hi' or type a cost item."}
