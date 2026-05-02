import time
from flask import Blueprint, jsonify, render_template, request

from app.extensions import csrf
from app.services.chatbot_service import ChatbotService

chatbot_bp = Blueprint("chatbot", __name__)

# Simple in-memory rate limit per client IP
_chatbot_last_request = {}
_chatbot_min_interval = 1.0


@chatbot_bp.get("/chatbot")
def chatbot_page():
    return render_template("chatbot/chat.html")


@chatbot_bp.post("/chatbot")
@csrf.exempt
def chatbot():
    client_ip = request.remote_addr or "unknown"
    now = time.time()
    last = _chatbot_last_request.get(client_ip, 0.0)

    if now - last < _chatbot_min_interval:
        return jsonify({"error": "Too many requests, please wait a moment."}), 429

    _chatbot_last_request[client_ip] = now

    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    result = ChatbotService.answer(message=message)
    payload_out = {
        "reply": result["reply"],
        "suggested_specialty": result["suggested_specialty"],
        "suggested_doctors": result["suggested_doctors"],
    }
    if "llm_debug" in result:
        payload_out["llm_debug"] = result["llm_debug"]
    return jsonify(payload_out)
