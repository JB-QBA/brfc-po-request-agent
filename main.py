from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/chatbot")
async def chatbot_endpoint(request: Request):
    # Get the incoming JSON from Google Chat
    body = await request.json()

    # Get the message text the user typed in Chat
    message_text = body.get("message", {}).get("text", "")

    # Get the user's display name (e.g. Johann Botes)
    user = body.get("sender", {}).get("displayName", "Unknown user")

    # Print for debugging
    print(f"Received from {user}: {message_text}")

    # Format a simple response
    reply = {
        "text": f"Hi {user}, you said: '{message_text}'. I'm alive and responding!"
    }

    # Send it back to Google Chat
    return JSONResponse(content=reply)