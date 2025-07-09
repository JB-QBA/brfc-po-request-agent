from fastapi import FastAPI, Request
import json
import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()
user_states = {}

# Config
SERVICE_ACCOUNT_FILE = "/etc/secrets/winged-pen-413708-e9544129b499.json"
SPREADSHEET_NAME = "FY2025 Budget for Analysis"
BUDGET_SHEET_TAB = "FY2025Budget"
XERO_SHEET_TAB = "Xero"

# Roles and config
special_users = {
    "finance@bahrainrfc.com": "Johann",
    "generalmanager@bahrainrfc.com": "Paul"
}
all_departments = [
    "Clubhouse", "Facilities", "Finance", "Front Office",
    "Human Capital", "Management", "Marketing", "Sponsorship", "Sports"
]
greeting_triggers = ["hi", "hello", "hey", "howzit", "salam"]

# Set up Google Sheets API
def get_gsheet_client():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

# Budget & actuals logic
def get_cost_items_for_department(dept):
    gc = get_gsheet_client()
    sheet = gc.open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(BUDGET_SHEET_TAB)
    rows = sheet.get_all_values()[1:]
    return list({row[3] for row in rows if len(row) > 3 and row[1].strip().lower() == dept.lower() and row[3].strip()})

def get_budget_for_cost_item_and_account(dept, item):
    gc = get_gsheet_client()
    sheet = gc.open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(BUDGET_SHEET_TAB)
    rows = sheet.get_all_values()[1:]
    total_item_budget = 0.0
    account_name = ""
    account_total_budget = 0.0

    for row in rows:
        if len(row) < 18:
            continue
        row_dept = row[1].strip().lower()
        row_item = row[3].strip().lower()
        row_account = row[0].strip()
        monthly_values = row[5:17]

        if row_dept == dept.lower() and row_item == item.lower():
            account_name = row_account
            total_item_budget = sum(float(v.replace(",", "")) if v else 0 for v in monthly_values)
            break

    if account_name:
        for row in rows:
            if len(row) >= 18 and row[0].strip() == account_name and row[1].strip().lower() == dept.lower():
                monthly_values = row[5:17]
                account_total_budget += sum(float(v.replace(",", "")) if v else 0 for v in monthly_values)

    return total_item_budget, account_total_budget, account_name

def get_ytd_actuals_for_account(dept, account_name):
    gc = get_gsheet_client()
    xero_sheet = gc.open_by_key("1U19XSieDNaDGN0khJJ8vFaDG75DwdKjE53d6MWi0Nt8").worksheet(XERO_SHEET_TAB)
    rows = xero_sheet.get_all_values()[3:]  # Skip to row 4

    ytd_total = 0.0
    for row in rows:
        if len(row) >= 15:
            acc = row[1].strip()
            val = row[10].replace(",", "").strip()
            dept_col = row[14].strip().lower()
            if acc.lower() == account_name.lower() and dept_col == dept.lower():
                try:
                    ytd_total += float(val)
                except ValueError:
                    continue
    return ytd_total

@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender = body.get("message", {}).get("sender", {})
    sender_name_full = sender.get("displayName", "there")
    sender_email = sender.get("email", "").lower()
    sender_first_name = sender_name_full.split()[0]
    message_text = body.get("message", {}).get("text", "").strip().lower()
    user_state = user_states.get(sender_email)

    # GREETING
    if any(message_text.startswith(g) for g in greeting_triggers):
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

    # REGULAR USER CONFIRMING FINANCE
    if user_state == "awaiting_department_confirmation":
        if message_text in ["yes", "correct"]:
            department = "Finance"
            user_states[sender_email] = "awaiting_cost_item_name"
            user_states[f"{sender_email}_department"] = department
            cost_items = get_cost_items_for_department(department)
            return {
                "text": f"Great! Here are the cost items for {department}:\n- " + "\n- ".join(cost_items)
            }
        else:
            user_states[sender_email] = "awaiting_manual_department"
            return {"text": "To which department does this PO belong?"}

    # SPECIAL USER PICKS DEPARTMENT
    if user_state == "awaiting_department_selection":
        if message_text.title() in all_departments:
            department = message_text.title()
            user_states[sender_email] = "awaiting_cost_item_name"
            user_states[f"{sender_email}_department"] = department
            cost_items = get_cost_items_for_department(department)
            return {
                "text": f"Thanks {sender_first_name}, here are the cost items for {department}:\n- " + "\n- ".join(cost_items)
            }
        else:
            return {"text": f"That department isn't recognized. Choose from:\n{', '.join(all_departments)}"}

    # REGULAR USER MANUAL DEPARTMENT CONFIRM
    if user_state == "awaiting_manual_department":
        if message_text.title() in all_departments:
            department = message_text.title()
            user_states[sender_email] = "awaiting_cost_item_name"
            user_states[f"{sender_email}_department"] = department
            cost_items = get_cost_items_for_department(department)
            return {
                "text": f"Got it. Here are the cost items for {department}:\n- " + "\n- ".join(cost_items)
            }
        else:
            return {"text": f"Please reply with a valid department:\n{', '.join(all_departments)}"}

    # HANDLE COST ITEM INPUT
    if user_state == "awaiting_cost_item_name":
        department = user_states.get(f"{sender_email}_department", "Finance")
        item = message_text.strip()

        # Validate item against department list
        valid_items = get_cost_items_for_department(department)
        matched_item = next((ci for ci in valid_items if ci.lower() == item.lower()), None)

        if matched_item:
            item_total, account_total, account_name = get_budget_for_cost_item_and_account(department, matched_item)
            ytd_actuals = get_ytd_actuals_for_account(department, account_name)

            response = (
                f"Cost Item: {matched_item}\n"
                f"- Budget for item: BHD {item_total:,.2f}\n"
                f"- Total budget for account ({account_name}): BHD {account_total:,.2f}\n"
                f"- YTD Actuals from Xero: BHD {ytd_actuals:,.2f}\n\n"
                "Please upload the related quote here to proceed with the PO request."
            )

            user_states[sender_email] = "awaiting_quote_upload"
            return {"text": response}
        else:
            return {
                "text": f"That cost item isn’t in the list for {department}. Please select from:\n- " + "\n- ".join(valid_items)
            }

    # DEFAULT CATCH
    return {
        "text": "I'm not sure how to help with that. Try saying 'Hi' to get started."
    }
