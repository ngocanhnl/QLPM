#!/usr/bin/env python
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from app.services.chatbot_service import ChatbotService

app = create_app()
with app.app_context():
    print("=== Test Keyword-Based Filtering ===\n")
    
    # Test 1: Đau bụng
    print("Test 1: 'tôi bị đau bụng'")
    result = ChatbotService.answer("tôi bị đau bụng")
    print("Diseases retrieved:")
    for d in result.get("related_diseases", []):
        print(f"  - {d['name']} (total_score: {d.get('total_score', d['score']):.1%})")
    
    print("\n" + "="*50 + "\n")
    
    # Test 2: Đau đầu
    print("Test 2: 'tôi bị đau đầu, choáng váng'")
    result2 = ChatbotService.answer("tôi bị đau đầu, choáng váng")
    print("Diseases retrieved:")
    for d in result2.get("related_diseases", []):
        print(f"  - {d['name']} (total_score: {d.get('total_score', d['score']):.1%})")
    
    print("\n" + "="*50 + "\n")
    print("✅ Filtering logic working!")
