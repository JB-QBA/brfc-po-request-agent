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

department_managers = {
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

# CHAT API SERVICE
def get_chat_service():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/chat.bot"]
    )
    return build("chat", "v1", credentials=creds)

# GET COST ITEMS BY DEPARTMENT
def get_cost_items_for_department(department: str) -> list:
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    return list(set(row[3] for row in rows if len(row) > 3 and row[1].strip().lower() == department.lower() and row[3].strip()))

# GET ACCOUNT, TRACKING, AND FINANCE REF FOR A COST ITEM
def get_account_tracking_reference(cost_item: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()
    headers = rows[0]
    data_rows = rows[1:]

    account_idx = headers.index("Account") if "Account" in headers else 0
    dept_idx = headers.index("Department") if "Department" in headers else 1
    item_idx = headers.index("Cost Item") if "Cost Item" in headers else 3
    tracking_idx = headers.index("Tracking") if "Tracking" in headers else 4
    ref_idx = headers.index("Finance Reference") if "Finance Reference" in headers else 5
    total_idx = headers.index("Total") if "Total" in headers else 17

    for row in data_rows:
        if len(row) > max(account_idx, dept_idx, item_idx, tracking_idx, ref_idx, total_idx):
            if row[item_idx].strip().lower() == cost_item.lower() and row[dept_idx].strip().lower() == department.lower():
                account = row[account_idx].strip()
                tracking = row[tracking_idx].strip()
                reference = row[ref_idx].strip()
                total_str = row[total_idx].replace(",", "") if row[total_idx] else "0"
                try:
                    total_budget = float(total_str)
                except:
                    total_budget = 0
                return account, tracking, reference, total_budget

    return None, None, None, 0

# GET ACCOUNT TOTAL BUDGET
def get_total_budget_for_account(account: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    total = 0.0
    for row in rows:
        if len(row) >= 18 and row[0].strip().lower() == account.lower() and row[1].strip().lower() == department.lower():
            try:
                value = float(row[17].replace(",", ""))
                total += value
            except:
                pass
    return total

# GET XERO YTD ACTUALS
def get_actuals_for_account(account: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(XERO_TAB_NAME)
    rows = sheet.get_all_values()[3:]
    total = 0.0
    for row in rows:
        if len(row) >= 15 and row[1].strip().lower() == account.strip().lower() and row[14].strip().lower() == department.lower():
            try:
                val = row[10].strip()
                val = val.replace("−", "-").replace("–", "-").replace("₩", "").replace("$", "").replace(",", "")
                val = val.replace(" ", "")
                total += float(val)
            except Exception as e:
                print(f"Skipping value '{row[10]}' due to error: {e}")
    return total

# POST TO SHARED CHAT SPACE
def post_to_shared_space(summary_text):
    chat_service = get_chat_service()
    message = {"text": summary_text}
    chat_service.spaces().messages().create(parent=CHAT_SPACE_ID, body=message).execute()

# MAIN BOT LOGIC
@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender = body.get("message", {}).get("sender", {})
    sender_email = sender.get("email", "").lower()
    full_name = sender.get("displayName", "there")
    first_name = full_name.split()[0]
    message_text = body.get("message", {}).get("text", "").strip()

    user_state = user_states.get(sender_email)

    if user_state == "awaiting_cost_item":
        department = user_states.get(f"{sender_email}_department")
        account, tracking, reference, item_total = get_account_tracking_reference(message_text, department)
        if account:
            account_total = get_total_budget_for_account(account, department)
            actuals = get_actuals_for_account(account, department)
            user_states[sender_email] = "awaiting_file"
            user_states[f"{sender_email}_cost_item"] = message_text.title()
            user_states[f"{sender_email}_account"] = account
            user_states[f"{sender_email}_reference"] = reference
            return {
                "text": (
                    f"✅ Great, you've selected: {message_text.title()} under {department}\n\n"
                    f"📊 Budgeted for item: {int(item_total):,}\n"
                    f"📊 Budgeted total for account '{account}': {int(account_total):,}\n"
                    f"📊 YTD actuals for '{account}': {int(actuals):,}\n\n"
                    "Please email your quote/document for processing:\n"
                    "bahrain-rugby-football-club-po@mail.approvalmax.com\n\n"
                    "And confirm reply \"done\" once sent for the final couple of Finance questions."
                )
            }
        else:
            return {"text": f"That cost item wasn't recognized for {department}. Try again."}

    if any(message_text.lower().startswith(greet) for greet in greeting_triggers):
        if sender_email in special_users:
            user_states[sender_email] = "awaiting_department"
            return {"text": f"Hi {first_name},\nWhat department would you like to raise a PO for?\nOptions: {', '.join(all_departments)}"}
        elif sender_email in department_managers:
            department = department_managers[sender_email]
            items = get_cost_items_for_department(department)
            user_states[sender_email] = "awaiting_cost_item"
            user_states[f"{sender_email}_department"] = department
            return {"text": f"Hi {first_name},\nHere are the cost items for {department}:\n- " + "\n- ".join(item for item in items if item.strip())}

    if user_state == "awaiting_department":
        if message_text.title() in all_departments:
            department = message_text.title()
            items = get_cost_items_for_department(department)
            user_states[sender_email] = "awaiting_cost_item"
            user_states[f"{sender_email}_department"] = department
            return {"text": f"Thanks {first_name}. Here are the cost items for {department}:\n- " + "\n- ".join(item for item in items if item.strip())}
        else:
            return {"text": f"Department not recognized. Choose from: {', '.join(all_departments)}"}

    return {"text": "I'm not sure how to help with that. Start with 'Hi' or type a cost item."}
