from app import create_app
from app.services.chatbot_service import ChatbotService

app = create_app()
with app.app_context():
    message = 'tôi bị đau bụng'
    top_k = int(app.config.get('RAG_TOP_K', 3))
    diseases = ChatbotService.retrieve_diseases(message=message, top_k=top_k)

    min_sim = float(app.config.get('RAG_MIN_SIMILARITY', 0.35))
    top_score = diseases[0]['score'] if diseases else 0.0
    keywords = ChatbotService._get_keywords_from_message(message)

    keyword_match_exists = False
    if keywords and diseases:
        for d in diseases:
            symptoms_text = ChatbotService._strip_diacritics(
                f"{d.get('symptoms') or ''} {d.get('description') or ''}".lower()
            )
            if any(kw in symptoms_text for kw in keywords):
                keyword_match_exists = True
                break

    dataset_is_poor_match = (not diseases) or (top_score < min_sim) or (keywords and not keyword_match_exists)

    print('Diseases found:', len(diseases))
    print('Top score:', top_score)
    print('Min similarity:', min_sim)
    print('Keywords:', keywords)
    print('Keyword match exists:', keyword_match_exists)
    print('Dataset is poor match:', dataset_is_poor_match)

    if diseases:
        print('Top disease:', diseases[0]['name'], 'score:', diseases[0]['score'])