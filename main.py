from fastapi import FastAPI, Request
import json
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

app = FastAPI()
user_states = {}

# CONFIGURATION
SERVICE_ACCOUNT_FILE = "/etc/secrets/winged-pen-413708-e9544129b499.json"
SPREADSHEET_NAME = "FY2025 Budget for Analysis"
SHEET_TAB_NAME = "FY2025Budget"
XERO_TAB_NAME = "Xero"
PO_REQUEST_SPACE = "spaces/AAQAs4dLeAY"  # Replace with your actual Chat space ID

special_users = {
    "finance@bahrainrfc.com": "Johann",
    "generalmanager@bahrainrfc.com": "Paul"
}

managed_users = {
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

def get_chat_service():
    scopes = ["https://www.googleapis.com/auth/chat.bot"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    return build("chat", "v1", credentials=creds)

# GET COST ITEMS BY DEPARTMENT
def get_cost_items_for_department(department: str) -> list:
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]  # From row 2
    return sorted(list(set(row[3] for row in rows if len(row) > 3 and row[1].strip().lower() == department.lower())))

# GET ACCOUNT & TRACKING FOR A COST ITEM
def get_account_and_tracking(cost_item: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    for row in rows:
        if len(row) >= 6 and row[3].strip().lower() == cost_item.lower() and row[1].strip().lower() == department.lower():
            account = row[0].strip()
            tracking = row[4].strip()
            total_budget = row[17].replace(",", "") if len(row) > 17 else "0"
            finance_reference = row[5].strip() if len(row) > 5 else ""
            return account, tracking, total_budget, finance_reference
    return None, None, "0", ""

# GET BUDGET TOTAL FOR ACCOUNT IN DEPARTMENT
def get_total_budget_for_account(account: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(SHEET_TAB_NAME)
    rows = sheet.get_all_values()[1:]
    total = 0.0
    for row in rows:
        if len(row) >= 18 and row[0].strip().lower() == account.lower() and row[1].strip().lower() == department.lower():
            try:
                val = row[17].replace(",", "")
                total += float(val) if val not in ["", "-", "-"] else 0
            except:
                pass
    return total

# GET XERO YTD ACTUALS
def get_actuals_for_account(account: str, department: str):
    sheet = get_gsheet().open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(XERO_TAB_NAME)
    rows = sheet.get_all_values()[3:]  # Start from row 4
    total = 0.0
    for row in rows:
        if len(row) >= 15 and row[1].strip().lower() == account.lower() and row[14].strip().lower() == department.lower():
            try:
                total += float(row[10])
            except:
                pass
    return total

# SEND MESSAGE TO SHARED CHAT

def send_to_procurement_chat(cost_item, account, department, finance_ref):
    chat_service = get_chat_service()
    try:
        chat_service.spaces().messages().create(
            parent=PO_REQUEST_SPACE,
            body={
                "text": (
                    f"📩 *New PO Request Received!*\n"
                    f"• *Description:* {cost_item}\n"
                    f"• *Account:* {account}\n"
                    f"• *Department:* {department}\n"
                    f"• *Projects/Events/Budgets:* {finance_ref}\n\n"
                    f"📎 The requester has uploaded the quote file."
                )
            }
        ).execute()
    except HttpError as error:
        print(f"Error sending chat message: {error}")

# MAIN CHATBOT HANDLER
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

    if any(message_text.startswith(greet) for greet in greeting_triggers):
        if sender_email in special_users:
            user_states[sender_email] = "awaiting_department_selection"
            return {
                "text": f"Hi {first_name},\nWhat department would you like to raise a PO for?\nOptions: {', '.join(all_departments)}"
            }
        elif sender_email in managed_users:
            department = managed_users[sender_email]
            user_states[sender_email] = "awaiting_cost_item"
            user_states[f"{sender_email}_department"] = department
            items = get_cost_items_for_department(department)
            return {
                "text": f"Hi {first_name},\nHere are the available cost items for {department}:\n" + "\n".join([f"- {item}" for item in items])
            }

    if user_state == "awaiting_department_selection":
        if message_text.title() in all_departments:
            user_states[sender_email] = "awaiting_cost_item"
            user_states[f"{sender_email}_department"] = message_text.title()
            items = get_cost_items_for_department(message_text.title())
            return {
                "text": f"Thanks {first_name}. Here are the cost items for {message_text.title()}:\n" + "\n".join([f"- {item}" for item in items])
            }
        else:
            return {"text": f"Department not recognized. Choose from: {', '.join(all_departments)}"}

    if user_state == "awaiting_cost_item":
        department = user_states.get(f"{sender_email}_department", "Finance")
        account, tracking, cost_item_total, finance_ref = get_account_and_tracking(message_text, department)
        if account:
            account_total = get_total_budget_for_account(account, department)
            ytd_actuals = get_actuals_for_account(account, department)
            user_states[sender_email] = "awaiting_quote"
            user_states[f"{sender_email}_cost_item"] = message_text.title()
            user_states[f"{sender_email}_account"] = account
            user_states[f"{sender_email}_finance_ref"] = finance_ref
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

    # FILE UPLOAD HANDLER
    if user_state == "awaiting_quote" and "attachment" in body.get("message", {}):
        department = user_states.get(f"{sender_email}_department", "Finance")
        cost_item = user_states.get(f"{sender_email}_cost_item", "")
        account = user_states.get(f"{sender_email}_account", "")
        finance_ref = user_states.get(f"{sender_email}_finance_ref", "")

        send_to_procurement_chat(cost_item, account, department, finance_ref)

        user_states[sender_email] = "awaiting_finance_questions"

        return {
            "text": (
                f"✅ Thank you, {first_name}. The file has been received and shared with the Procurement team.\n\n"
                "Now, just a couple more questions:\n"
                "1️⃣ Does this quote require any upfront payments?\n"
                "2️⃣ Is this a foreign payment that requires GSA approval?"
            )
        }

    # DEFAULT RESPONSE
    return {
        "text": "I'm not sure how to help with that. Start with 'Hi' or type a cost item."
    }
