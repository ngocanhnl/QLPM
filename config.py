import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

    # MySQL example:
    # mysql+pymysql://user:password@localhost:3306/medical_platform?charset=utf8mb4
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:root@localhost:3307/medical_platform?charset=utf8mb4",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    WTF_CSRF_TIME_LIMIT = None

    # VNPay configuration
    VNPAY_VERSION = os.getenv("VNPAY_VERSION", "2.1.0")
    VNPAY_TMN_CODE = os.getenv("VNPAY_TMN_CODE", "ODZ5NOX0")
    VNPAY_HASH_SECRET = os.getenv("VNPAY_HASH_SECRET", "5V52YZPPD3EHTSGJOQQ9XG6VIREUZQLG")
    VNPAY_PAYMENT_URL = os.getenv(
        "VNPAY_PAYMENT_URL",
        "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html",
    )
    VNPAY_RETURN_URL_PATH = os.getenv("VNPAY_RETURN_URL_PATH", "/vnpay/return")
    VNPAY_LOCALE = os.getenv("VNPAY_LOCALE", "vn")
    VNPAY_CURR_CODE = os.getenv("VNPAY_CURR_CODE", "VND")
    VNPAY_ORDER_TYPE = os.getenv("VNPAY_ORDER_TYPE", "other")

    # Chatbot / RAG configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    
    # Gemini fallback configuration
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AAIzaSyCzZHRlsnsC1AFmny_V_YoTLgmjOnH8k2s")
    # Base for Generative Language API (generateContent)
    GEMINI_API_URL = os.getenv("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta")
    GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-1.5-pro")

    # Choose which LLM provider to use: "auto" | "openai" | "gemini"
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")
    
    RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
    # If top similarity score is below this threshold, treat as "no good match in dataset"
    # and use LLM triage fallback.
    RAG_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.35"))

    # If true, /chatbot will include raw LLM response (useful to verify Gemini/OpenAI).
    CHATBOT_DEBUG_LLM = os.getenv("CHATBOT_DEBUG_LLM", "false").strip().lower() in {"1", "true", "yes", "y", "on"}

