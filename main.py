from fastapi import FastAPI, Request
import json

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "ok"}

@app.post("/")
async def chat_webhook(request: Request):
    body = await request.json()
    print("Received request:", json.dumps(body, indent=2))

    sender = body.get("message", {}).get("sender", {}).get("displayName", "there")
    text = body.get("message", {}).get("text", "")

    return {
        "text": f"Hi {sender}, you said: '{text}'. I'm alive and responding!"
    }