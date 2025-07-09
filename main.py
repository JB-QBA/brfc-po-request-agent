from fastapi import FastAPI, Request, UploadFile
import json
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.message import EmailMessage

app = FastAPI()
user_states = {}

# CONFIG
SERVICE_ACCOUNT_FILE = "/etc/secrets/winged-pen-413708-e9544129b499.json"
SPREADSHEET_KEY = "1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8"
SHEET_TAB_NAME = "FY2025Budget"
XERO_TAB_NAME = "Xero"

special_users = {
    "finance@bahrainrfc.com": "Johann",
    "generalmanager@bahrainrfc.com": "Paul"
}

manager_departments = {
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

# AUTH

def get_gsheet():
    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc

# HELPERS

def get_cost_items_for_department(department: str):
    sheet = get_gsheet().open_by_key(SPREADSHEET_KEY).worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    return list(set(row[3] for row in rows if len(row) > 3 and row[1].strip().lower() == department.lower() and row[3].strip()))

def get_account_and_tracking(cost_item: str, department: str):
    sheet = get_gsheet().open_by_key(SPREADSHEET_KEY).worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    for row in rows:
        if len(row) >= 6 and row[3].strip().lower() == cost_item.lower() and row[1].strip().lower() == department.lower():
            account = row[0].strip()
            tracking = row[4].strip()
            total_budget = row[17].replace(",", "") if len(row) > 17 else "0"
            return account, tracking, total_budget
    return None, None, "0"

def get_total_budget_for_account(account: str, department: str):
    sheet = get_gsheet().open_by_key(SPREADSHEET_KEY).worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    total = 0.0
    for row in rows:
        if len(row) >= 18 and row[0].strip().lower() == account.lower() and row[1].strip().lower() == department.lower():
            try:
                val = float(row[17].replace(",", "").strip())
                total += val
            except:
                pass
    return total

def get_actuals_for_account(account: str, department: str):
    sheet = get_gsheet().open_by_key(SPREADSHEET_KEY).worksheet(XERO_TAB_NAME)
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

def get_finance_reference(cost_item: str, department: str):
    sheet = get_gsheet().open_by_key(SPREADSHEET_KEY).worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    for row in rows:
        if len(row) >= 6 and row[3].strip().lower() == cost_item.lower() and row[1].strip().lower() == department.lower():
            return row[4].strip()
    return "-"

# EMAIL (simulated)
def send_email(recipient, subject, body):
    print(f"\n--- Sending email to {recipient} ---\")
    print(f"Subject: {subject}")
    print(f"{body}\n")

# MAIN HANDLER

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

    # Handle greetings
    if any(message_text.lower().startswith(greet) for greet in greeting_triggers):
        if sender_email in special_users:
            user_states[sender_email] = "awaiting_department_selection"
            return {"text": f"Hi {first_name},\nWhat department would you like to raise a PO for?\nOptions: {', '.join(all_departments)}"}
        elif sender_email in manager_departments:
            department = manager_departments[sender_email]
            user_states[sender_email] = "awaiting_cost_item"
            user_states[f"{sender_email}_department"] = department
            items = get_cost_items_for_department(department)
            return {"text": f"Hi {first_name},\nHere are the available cost items for {department}:\n" + "\n".join(f"- {item}" for item in items)}
        else:
            user_states[sender_email] = "awaiting_cost_item"
            user_states[f"{sender_email}_department"] = "Finance"
            items = get_cost_items_for_department("Finance")
            return {"text": f"Hi {first_name},\nHere are the available cost items for Finance:\n" + "\n".join(f"- {item}" for item in items)}

    # Handle department confirmation from special users
    if user_state == "awaiting_department_selection":
        if message_text.title() in all_departments:
            department = message_text.title()
            user_states[sender_email] = "awaiting_cost_item"
            user_states[f"{sender_email}_department"] = department
            items = get_cost_items_for_department(department)
            return {"text": f"Thanks {first_name}. Here are the cost items for {department}:\n" + "\n".join(f"- {item}" for item in items)}
        else:
            return {"text": f"Department not recognized. Choose from: {', '.join(all_departments)}"}

    # Handle cost item selection
    if user_state == "awaiting_cost_item":
        department = user_states.get(f"{sender_email}_department", "Finance")
        account, tracking, cost_item_total = get_account_and_tracking(message_text, department)
        if account:
            account_total = get_total_budget_for_account(account, department)
            ytd_actuals = get_actuals_for_account(account, department)
            user_states[sender_email] = "awaiting_quote"
            user_states[f"{sender_email}_cost_item"] = message_text.title()
            user_states[f"{sender_email}_account"] = account
            return {
                "text": (
                    f"✅ Great, you've selected: {message_text.title()} under {department}\n\n"
                    f"📊 Budgeted for item: {int(float(cost_item_total)):,}\n"
                    f"📊 Budgeted total for account '{account}': {int(account_total):,}\n"
                    f"📊 YTD actuals for '{account}': {int(ytd_actuals):,}\n\n"
                    "You can now upload the quote here to continue - Just a few more questions and we're done."
                )
            }
        else:
            return {"text": f"That cost item wasn't recognized for {department}. Try again."}

    # Handle file uploads
    if body.get("message", {}).get("attachment", []):
        user_states[sender_email] = "awaiting_finance_questions"
        cost_item = user_states.get(f"{sender_email}_cost_item")
        department = user_states.get(f"{sender_email}_department")
        account = user_states.get(f"{sender_email}_account")
        reference = get_finance_reference(cost_item, department)

        # Send to Procurement
        send_email(
            "stores@bahrainrfc.com",
            f"New PO Request: {cost_item}",
            f"Cost Item: {cost_item}\nAccount: {account}\nDepartment: {department}\nBudget Ref: {reference}"
        )

        # Simulate file forwarding to ApprovalMax
        send_email(
            "bahrain-rugby-football-club-po@mail.approvalmax.com",
            f"PO Quote: {cost_item}",
            f"Forwarded uploaded file for cost item {cost_item}."
        )

        return {
            "text": (
                f"📎 Thanks, your quote has been received.\n"
                f"📤 The Procurement Officer (Gilmart) has been notified.\n\n"
                "🧾 Final two questions for Finance:\n"
                "1️⃣ Does this quote require any upfront payments?\n"
                "2️⃣ Is this a foreign payment requiring GSA approval?\n\n"
                "Please respond with both answers so we can complete the request."
            )
        }

    # Awaiting finance questions answers
    if user_state == "awaiting_finance_questions":
        send_email(
            "finance@bahrainrfc.com",
            f"Finance Response for PO Request ({user_states.get(f'{sender_email}_cost_item')})",
            f"User: {sender_email}\nResponse: {message_text}"
        )
        send_email(
            "accounts@bahrainrfc.com",
            f"Finance Response for PO Request ({user_states.get(f'{sender_email}_cost_item')})",
            f"User: {sender_email}\nResponse: {message_text}"
        )
        return {"text": "✅ Thanks, your responses have been recorded and sent to Finance."}

    return {"text": "I'm not sure how to help with that. Start by saying 'Hi'."}
