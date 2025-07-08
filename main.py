from fastapi import FastAPI, Request
import json

app = FastAPI()

# Track user interaction state
user_states = {}

# Known users with special department access
special_users = {
    "finance@bahrainrfc.com": "Johann",
    "generalmanager@bahrainrfc.com": "Paul"
}

# All available departments
all_departments = [
    "Clubhouse", "Facilities", "Finance", "Front Office",
    "Human Capital", "Management", "Marketing", "Sponsorship", "Sports"
]

# Starting words that trigger the bot
greeting_triggers = ["hi", "hey", "howzit", "salam", "hello"]

@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender_info = body.get("message", {}).get("sender", {})
    sender_name = sender_info.get("displayName", "there")
    sender_email = sender_info.get("email", "").lower()
    message_text = body.get("message", {}).get("text", "").strip().lower()

    # If it's a new message with a greeting
    if any(message_text.startswith(greet) for greet in greeting_triggers):
        if sender_email in special_users:
            user_states[sender_email] = "awaiting_department_selection"
            return {
                "text": f"Hi {sender_name},\nWhat department would you like to raise a PO for?\nOptions: {', '.join(all_departments)}"
            }
        else:
            user_states[sender_email] = "awaiting_department_confirmation"
            return {
                "text": f"Hi {sender_name},\nAre we getting the PO details for the Finance department?"
            }

    # Handle user confirming their department (default case)
    if user_states.get(sender_email) == "awaiting_department_confirmation":
        if message_text in ["yes", "correct"]:
            user_states[sender_email] = "awaiting_cost_item_choice"
            return {
                "text": "Thanks for confirming.\nDo you know the cost item or would you like to choose from the list?\nOptions:\n- Yes, I know it\n- I’ll choose from list"
            }
        else:
            user_states[sender_email] = "awaiting_manual_department"
            return {
                "text": "To which department does this PO belong?"
            }

    # Handle department selection from special users
    if user_states.get(sender_email) == "awaiting_department_selection":
        if message_text.title() in all_departments:
            user_states[sender_email] = "awaiting_cost_item_choice"
            return {
                "text": f"Thanks for confirming the department: {message_text.title()}.\nDo you know the cost item or would you like to choose from the list?\nOptions:\n- Yes, I know it\n- I’ll choose from list"
            }
        else:
            return {
                "text": f"That department isn't recognized. Please choose from the following:\n{', '.join(all_departments)}"
            }

    # Handle when user is asked if they know the cost item
    if user_states.get(sender_email) == "awaiting_cost_item_choice":
        if message_text in ["yes", "i know it", "i'll type it"]:
            user_states[sender_email] = "awaiting_cost_item_name"
            return {"text": "Great, please type the cost item you'd like this PO to be allocated against."}
        else:
            user_states[sender_email] = "awaiting_cost_item_selection"
            return {"text": "Sure, please choose from the cost item list:\n- Office Supplies\n- Repairs and Maintenance\n- Travel Expenses\n- Equipment Purchase\n(You can expand this later)"}

    return {"text": "I'm not sure how to help with that just yet — please start again with 'Hi', 'Hey', 'Howzit', or 'Salam'."}
