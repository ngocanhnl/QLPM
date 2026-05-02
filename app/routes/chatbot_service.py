import json
import math
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import date

from flask import current_app

from app.extensions import db
from app.models.doctor import Doctor
from app.models.disease import Disease
from app.models.hospital import Hospital
from app.models.schedule import Schedule
from app.models.user import User


class ChatbotService:
    @staticmethod
    def _strip_diacritics(text: str) -> str:
        # Normalize Vietnamese chars to ASCII so keyword matching works
        # even when DB text is stored without accents (e.g. "dau" vs "đau").
        normalized = unicodedata.normalize("NFKD", text or "")
        return "".join(c for c in normalized if not unicodedata.combining(c))

    @staticmethod
    def _openai_post(path: str, payload: dict) -> dict:
        api_key = (current_app.config.get("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")

        req = urllib.request.Request(
            url=f"https://api.openai.com/v1/{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _gemini_post(path: str, payload: dict) -> dict:
        """
        Gemini REST API call using correct format
        """
        gemini_key = (current_app.config.get("GEMINI_API_KEY") or "").strip()
        if not gemini_key:
            raise RuntimeError("Missing GEMINI_API_KEY")

        model = payload.get("model") or current_app.config.get("GEMINI_CHAT_MODEL") or "gemini-1.5-flash"
        messages = payload.get("messages") or []

        # Combine all messages into one prompt
        system_parts = [m.get("content", "") for m in messages if (m.get("role") or "") == "system"]
        user_parts = [m.get("content", "") for m in messages if (m.get("role") or "") != "system"]
        prompt = "\n\n".join([p for p in (system_parts + user_parts) if p]).strip()
        if not prompt:
            prompt = "No prompt provided."

        # Correct Gemini API endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"

        req_body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": float(payload.get("temperature", 0.7))
            }
        }

        req = urllib.request.Request(
            url=url,
            data=json.dumps(req_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Gemini API error: {data}")

        return {"choices": [{"message": {"content": text}}]}

    @staticmethod
    def _fallback_embedding(text: str, dim: int = 128) -> list[float]:
        # Deterministic local fallback when embedding API is unavailable.
        vec = [0.0] * dim
        for idx, ch in enumerate(text.lower()):
            vec[idx % dim] += (ord(ch) % 97) / 97.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def embed_text(text: str) -> list[float]:
        model = current_app.config.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        try:
            data = ChatbotService._openai_post(
                "embeddings",
                {
                    "model": model,
                    "input": text,
                },
            )
            return data["data"][0]["embedding"]
        except (KeyError, RuntimeError, urllib.error.URLError, urllib.error.HTTPError):
            return ChatbotService._fallback_embedding(text)

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(f"{v:.8f}" for v in vector) + "]"

    @staticmethod
    def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
        if not v1 or not v2:
            return 0.0
        size = min(len(v1), len(v2))
        dot = sum(v1[i] * v2[i] for i in range(size))
        n1 = math.sqrt(sum(v1[i] * v1[i] for i in range(size))) or 1.0
        n2 = math.sqrt(sum(v2[i] * v2[i] for i in range(size))) or 1.0
        return float(dot / (n1 * n2))

    @staticmethod
    def retrieve_diseases(message: str, top_k: int = 3, specialty: str | None = None) -> list[dict]:
        """
        Retrieve diseases using vector embedding similarity.
        This is fully dynamic - new diseases added to DB are automatically retrieved
        based on semantic similarity without any code changes needed.
        """
        top_k = max(1, int(top_k))
        uri = (current_app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower()
        query_embedding = ChatbotService.embed_text(message)

        if "postgresql" in uri:
            # PostgreSQL with pgvector
            vector_text = ChatbotService._vector_literal(query_embedding)
            sql = """
                SELECT id, name, symptoms, description, specialty,
                       (embedding <=> CAST(:vector AS vector)) AS distance
                FROM diseases
                WHERE embedding IS NOT NULL
            """
            params: dict[str, object] = {"vector": vector_text, "top_k": top_k}
            if specialty:
                sql += " AND specialty ILIKE :specialty "
                params["specialty"] = f"%{specialty}%"
            sql += " ORDER BY embedding <=> CAST(:vector AS vector) LIMIT :top_k "
            rows = db.session.execute(db.text(sql), params).mappings().all()
            scored = [
                {
                    "id": int(r["id"]),
                    "name": r["name"],
                    "symptoms": r["symptoms"],
                    "description": r["description"],
                    "specialty": r["specialty"],
                    "score": float(1.0 - float(r["distance"])),
                }
                for r in rows
            ]

        else:
            # MySQL - app-layer cosine similarity
            stmt = db.select(Disease).where(Disease.embedding.is_not(None))
            if specialty:
                stmt = stmt.where(Disease.specialty.ilike(f"%{specialty}%"))
            rows = db.session.execute(stmt).scalars().all()

            scored: list[dict] = []
            for r in rows:
                try:
                    disease_embedding = json.loads(r.embedding) if isinstance(r.embedding, str) else r.embedding
                    if not isinstance(disease_embedding, list):
                        continue
                    score = ChatbotService._cosine_similarity(query_embedding, [float(x) for x in disease_embedding])
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                scored.append(
                    {
                        "id": int(r.id),
                        "name": r.name,
                        "symptoms": r.symptoms,
                        "description": r.description,
                        "specialty": r.specialty,
                        "score": score,
                    }
                )

        # Sort by similarity score (descending) and return top k
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def persist_embedding_for_disease(disease_id: int) -> None:
        """Compute embedding from name + symptoms + description and save (MySQL JSON or PG vector)."""
        uri = (current_app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower()
        is_postgres = "postgresql" in uri
        disease = db.session.get(Disease, disease_id)
        if not disease:
            return
        content = f"{disease.name}\nSymptoms: {disease.symptoms}\nDescription: {disease.description}"
        embedding = ChatbotService.embed_text(content)
        if is_postgres:
            vector_text = ChatbotService._vector_literal(embedding)
            db.session.execute(
                db.text(
                    """
                    UPDATE diseases
                    SET embedding = CAST(:embedding AS vector)
                    WHERE id = :disease_id
                    """
                ),
                {"embedding": vector_text, "disease_id": disease_id},
            )
        else:
            disease.embedding = json.dumps(embedding)

    @staticmethod
    def suggest_doctors(specialty: str | None, limit: int = 5) -> list[dict]:
        today = date.today()
        stmt = (
            db.select(
                Doctor.id,
                User.username,
                Doctor.specialty,
                Doctor.experience_years,
                Hospital.name.label("hospital_name"),
                db.func.count(Schedule.id).label("available_slots"),
                db.func.min(Schedule.date).label("next_available_date"),
            )
            .join(User, User.id == Doctor.user_id)
            .outerjoin(Hospital, Hospital.id == Doctor.hospital_id)
            .outerjoin(
                Schedule,
                db.and_(
                    Schedule.doctor_id == Doctor.id,
                    Schedule.is_available.is_(True),
                    Schedule.date >= today,
                ),
            )
            .group_by(Doctor.id, User.username, Doctor.specialty, Doctor.experience_years, Hospital.name)
            .order_by(
                db.desc("available_slots"),
                db.desc(Doctor.experience_years),
            )
            .limit(limit)
        )
        if specialty:
            stmt = stmt.where(Doctor.specialty.ilike(f"%{specialty}%"))
        rows = db.session.execute(stmt).all()
        return [
            {
                "doctor_id": int(r.id),
                "doctor_name": r.username,
                "specialty": r.specialty,
                "hospital_name": r.hospital_name,
                "experience_years": int(r.experience_years or 0),
                "available_slots": int(r.available_slots or 0),
                "next_available_date": (r.next_available_date.isoformat() if r.next_available_date else None),
            }
            for r in rows
        ]

    @staticmethod
    def _build_context(diseases: list[dict], doctors: list[dict]) -> dict:
        """Build structured context for LLM."""
        return {
            "diseases": [
                {
                    "name": d["name"],
                    "specialty": d["specialty"],
                    "symptoms": d["symptoms"],
                    "description": d["description"],
                    "similarity_score": d["score"],
                }
                for d in diseases
            ],
            "doctors": [
                {
                    "name": d["doctor_name"],
                    "specialty": d["specialty"],
                    "hospital": d.get("hospital_name") or "N/A",
                    "available_slots": d["available_slots"],
                    "experience_years": d["experience_years"],
                }
                for d in doctors
            ],
        }

    @staticmethod
    def _get_keywords_from_message(message: str) -> set:
        """Extract Vietnamese keywords from message."""
        msg = ChatbotService._strip_diacritics(message.lower())
        words = re.findall(r"\w+", msg)
        # Remove common Vietnamese stopwords (ASCII normalized)
        stopwords = {
            "toi",
            "bi",
            "co",
            "la",
            "va",
            "duoc",
            "cai",
            "nay",
            "no",
            "khong",
            "do",
            "nguoi",
            "ma",
            # very generic symptom
            "dau",
        }
        return set(w for w in words if len(w) > 1 and w not in stopwords)

    @staticmethod
    def _filter_diseases_keyword_based(message: str, diseases: list[dict]) -> list[dict]:
        """
        Fallback: Filter diseases based on keyword matching when no API key.
        Promotes diseases whose symptoms/description contain keywords from the message.
        """
        keywords = ChatbotService._get_keywords_from_message(message)
        if not keywords:
            return diseases
        
        # Score each disease based on keyword overlap
        scored = []
        for d in diseases:
            symptoms_text = ChatbotService._strip_diacritics(
                (d.get("symptoms", "") + " " + d.get("description", "")).lower()
            )
            # Count matching keywords
            matches = sum(1 for kw in keywords if kw in symptoms_text)
            # Calculate match ratio
            match_ratio = matches / len(keywords) if keywords else 0
            scored.append({
                **d,
                'keyword_score': match_ratio,
                'total_score': d['score'] * 0.5 + match_ratio * 0.5  # Blend embedding + keyword score
            })
        
        # Sort by combined score
        scored.sort(key=lambda x: x['total_score'], reverse=True)
        # Return top diseases
        return scored[:len(diseases)]

    @staticmethod
    def _filter_diseases_with_llm(message: str, diseases: list[dict]) -> list[dict]:
        """
        Use ChatGPT to intelligently filter and re-rank diseases
        based on medical relevance to the symptom, not just embedding similarity.
        Falls back to keyword-based filtering if no API key.
        """
        openai_key = (current_app.config.get("OPENAI_API_KEY") or "").strip()
        gemini_key = (current_app.config.get("GEMINI_API_KEY") or "").strip()
        provider = (current_app.config.get("LLM_PROVIDER") or "auto").strip().lower()
        
        if not diseases:
            return diseases
        
        if not openai_key and not gemini_key:
            return ChatbotService._filter_diseases_keyword_based(message, diseases)

        use_gemini = provider == "gemini" or (provider == "auto" and bool(gemini_key))
        use_openai = provider == "openai" or (provider == "auto" and bool(openai_key) and not use_gemini)

        model = current_app.config.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        
        # Format diseases for filtering
        diseases_text = "\n".join([
            f"{i+1}. {d['name']} ({d['specialty']})\n"
            f"   Triệu chứng: {d['symptoms']}\n"
            f"   Mô tả: {d['description']}\n"
            f"   Embedding similarity: {d['score']:.1%}"
            for i, d in enumerate(diseases)
        ])
        
        system_prompt = (
            "Bạn là bác sĩ chuyên khoa có kiến thức y tế sâu. "
            "Hãy đánh giá mức độ liên quan Y TẾ thực tế giữa triệu chứng và bệnh (không phải embedding similarity). "
            "Lọc ra những bệnh THỰC SỰ liên quan và xếp hạng từ cao đến thấp. "
            "Bỏ qua những bệnh không liên quan (ví dụ: cao huyết áp với đau bụng)."
        )
        
        user_prompt = (
            f"User triệu chứng (câu hỏi người dùng): {message}\n\n"
            f"Danh sách bệnh từ vector embedding:\n{diseases_text}\n\n"
            f"Hãy lọc các bệnh THỰC SỰ liên quan với triệu chứng ở trên (User message), dựa trên kiến thức y tế; "
            f"KHÔNG dựa vào embedding similarity. "
            f"Trả lời dưới dạng JSON:\n"
            f'{{"relevant_diseases": ["bệnh 1", "bệnh 2", ...], "explanation": "giải thích ngắn"}}'
        )
        
        try:
            if use_openai:
                data = ChatbotService._openai_post(
                    "chat/completions",
                    {
                        "model": model,
                        "temperature": 0.3,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )
            elif use_gemini:
                gemini_model = current_app.config.get("GEMINI_CHAT_MODEL", "gemini-1.5-pro")
                data = ChatbotService._gemini_post(
                    "chat/completions",
                    {
                        "model": gemini_model,
                        "temperature": 0.3,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )
            else:
                return ChatbotService._filter_diseases_keyword_based(message, diseases)
        except Exception:
            # If provider failed, fallback to the other provider (if available).
            if use_openai and use_gemini:
                try:
                    gemini_model = current_app.config.get("GEMINI_CHAT_MODEL", "gemini-1.5-pro")
                    data = ChatbotService._gemini_post(
                        "chat/completions",
                        {
                            "model": gemini_model,
                            "temperature": 0.3,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                        },
                    )
                except Exception:
                    return ChatbotService._filter_diseases_keyword_based(message, diseases)
            else:
                return ChatbotService._filter_diseases_keyword_based(message, diseases)

        response_text = data["choices"][0]["message"]["content"]
        import json
        try:
            result = json.loads(response_text)
            relevant_names = set(result.get("relevant_diseases", []))
            # Filter and maintain order
            filtered = [d for d in diseases if d["name"] in relevant_names]
            return filtered if filtered else diseases
        except (json.JSONDecodeError, ValueError):
            # Fallback to keyword filtering if JSON parse fails
            return ChatbotService._filter_diseases_keyword_based(message, diseases)

    @staticmethod
    def _llm_reply(message: str, context: dict) -> dict:
        """
        Generate intelligent reply using OpenAI/Gemini if API key available;
        otherwise return formatted retrieval results.
        """
        openai_key = (current_app.config.get("OPENAI_API_KEY") or "").strip()
        gemini_key = (current_app.config.get("GEMINI_API_KEY") or "").strip()
        provider = (current_app.config.get("LLM_PROVIDER") or "auto").strip().lower()
        model = current_app.config.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")

        disease_info = "\n".join([
            f"• {d['name']} (chuyên khoa: {d['specialty']}, độ tương đồng: {d['similarity_score']:.1%})\n"
            f"  Triệu chứng: {d['symptoms']}\n"
            f"  Mô tả: {d['description']}"
            for d in context["diseases"]
        ]) if context["diseases"] else "Không tìm thấy bệnh phù hợp."

        doctor_info = "\n".join([
            f"• {d['name']} ({d['specialty']}) - {d['hospital']} - {d['available_slots']} slot trống ({d['experience_years']} năm kinh nghiệm)"
            for d in context["doctors"]
        ]) if context["doctors"] else "Không tìm thấy bác sĩ phù hợp."

        if openai_key or gemini_key:
            use_gemini = provider == "gemini" or (provider == "auto" and bool(gemini_key))
            use_openai = provider == "openai" or (provider == "auto" and bool(openai_key) and not use_gemini)

            system_prompt = (
                "Bạn là trợ lý tư vấn y tế chuyên nghiệp. Dựa trên dữ liệu vector embedding (semantic similarity), "
                "hãy tư vấn bệnh nhân về các bệnh có khả năng liên quan, chuyên khoa phù hợp, và bác sĩ được đề xuất. "
                "KHÔNG cung cấp chẩn đoán xác định, chỉ tư vấn dựa trên triệu chứng. Trả lời bằng tiếng Việt, ngắn gọn và chuyên nghiệp."
            )

            user_prompt = (
                f"Triệu chứng bệnh nhân: {message}\n\n"
                f"Dữ liệu từ vector embedding (sắp xếp theo độ tương đồng semantic):\n\n"
                f"Các bệnh có khả năng liên quan:\n{disease_info}\n\n"
                f"Các bác sĩ được gợi ý:\n{doctor_info}\n\n"
                f"Dựa trên dữ liệu embedding trên, hãy tạo một phản hồi tư vấn chuyên nghiệp."
            )

            try:
                if use_openai:
                    data = ChatbotService._openai_post(
                        "chat/completions",
                        {
                            "model": model,
                            "temperature": 0.7,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                        },
                    )
                    text = data["choices"][0]["message"]["content"]
                    return {"reply": text, "provider": "openai", "raw_text": text}

                if use_gemini:
                    gemini_model = current_app.config.get("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
                    data = ChatbotService._gemini_post(
                        "chat/completions",
                        {
                            "model": gemini_model,
                            "temperature": 0.7,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                        },
                    )
                    text = data["choices"][0]["message"]["content"]
                    return {"reply": text, "provider": "gemini", "raw_text": text}
            except Exception:
                pass

        static_reply = (
            f"**Dựa trên triệu chứng: '{message}'**\n\n"
            f"📋 Các bệnh có khả năng liên quan (theo độ tương đồng embedding):\n{disease_info}\n\n"
            f"👨‍⚕️ Bác sĩ được gợi ý:\n{doctor_info}\n\n"
            f"⚠️ **Khuyến nghị**: Đây chỉ là tư vấn dựa trên triệu chứng. "
            f"Vui lòng đặt lịch khám với bác sĩ để được chẩn đoán chính xác."
        )

        return {"reply": static_reply, "provider": None, "raw_text": None}


    @staticmethod
    def _llm_triage_fallback(message: str) -> dict:
        """
        When dataset retrieval does not find a good match,
        ask LLM directly based on symptoms to propose specialty + booking advice.
        Returns: {"reply": "...", "suggested_specialty": "..."}.
        """
        openai_key = (current_app.config.get("OPENAI_API_KEY") or "").strip()
        gemini_key = (current_app.config.get("GEMINI_API_KEY") or "").strip()
        provider = (current_app.config.get("LLM_PROVIDER") or "auto").strip().lower()

        if not openai_key and not gemini_key:
            return {"reply": "", "suggested_specialty": ""}

        use_gemini = provider == "gemini" or (provider == "auto" and bool(gemini_key))
        use_openai = provider == "openai" or (provider == "auto" and bool(openai_key) and not use_gemini)

        system_prompt = (
            "Bạn là trợ lý triage y tế. "
            "Không chẩn đoán xác định. "
            "Dựa trên triệu chứng người dùng, hãy đề xuất chuyên khoa phù hợp và hướng dẫn đặt lịch khám sớm nếu cần. "
            "Trả lời bằng tiếng Việt."
        )
        user_prompt = (
            f"Người dùng mô tả triệu chứng:\n{message}\n\n"
            "Hãy trả về JSON theo đúng format:\n"
            '{ "suggested_specialty": "tên chuyên khoa", "reply": "nội dung tư vấn ngắn, không chẩn đoán xác định, có khuyến nghị đặt lịch" }'
        )

        llm_provider_used = None
        llm_raw_text = ""
        try:
            if use_openai:
                llm_provider_used = "openai"
                model = current_app.config.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
                data = ChatbotService._openai_post(
                    "chat/completions",
                    {
                        "model": model,
                        "temperature": 0.3,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )
                text = data["choices"][0]["message"]["content"]
            elif use_gemini:
                llm_provider_used = "gemini"
                gemini_model = current_app.config.get("GEMINI_CHAT_MODEL", "gemini-1.5-pro")
                data = ChatbotService._gemini_post(
                    "chat/completions",
                    {
                        "model": gemini_model,
                        "temperature": 0.3,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )
                text = data["choices"][0]["message"]["content"]
            else:
                return {"reply": "", "suggested_specialty": ""}
        except Exception:
            return {"reply": "", "suggested_specialty": "", "llm_provider": None, "llm_raw_text": ""}

        try:
            import json as _json

            llm_raw_text = text or ""
            parsed = _json.loads(text)
            return {
                "reply": parsed.get("reply") or "",
                "suggested_specialty": parsed.get("suggested_specialty") or "",
                "llm_provider": llm_provider_used,
                "llm_raw_text": llm_raw_text,
            }
        except Exception:
            return {
                "reply": text,
                "suggested_specialty": "",
                "llm_provider": llm_provider_used,
                "llm_raw_text": llm_raw_text,
            }

    @staticmethod
    def answer(message: str) -> dict:
        top_k = int(current_app.config.get("RAG_TOP_K", 3))
        diseases = ChatbotService.retrieve_diseases(message=message, top_k=top_k)

        min_sim = float(current_app.config.get("RAG_MIN_SIMILARITY", 0.35))
        top_score = diseases[0]["score"] if diseases else 0.0
        keywords = ChatbotService._get_keywords_from_message(message)
        # Heuristic: if we can't find ANY keyword occurrences in retrieved diseases,
        # treat it as "no good match in dataset" even if embedding scores are non-zero.
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

        # If dataset match is poor, use LLM triage fallback directly.
        if dataset_is_poor_match:
            fallback = ChatbotService._llm_triage_fallback(message=message)
            suggested_specialty = fallback.get("suggested_specialty") or "General Medicine"
            doctors = ChatbotService.suggest_doctors(specialty=suggested_specialty)
            if not doctors:
                doctors = ChatbotService.suggest_doctors(specialty=None)

            if fallback.get("reply"):
                reply_text = fallback.get("reply")
                provider = fallback.get("llm_provider")
                raw_text = fallback.get("llm_raw_text")
            else:
                llm_result = ChatbotService._llm_reply(
                    message=message,
                    context=ChatbotService._build_context(diseases=diseases, doctors=doctors),
                )
                reply_text = llm_result.get("reply")
                provider = llm_result.get("provider")
                raw_text = llm_result.get("raw_text")

            result: dict = {
                "reply": reply_text,
                "suggested_specialty": suggested_specialty,
                "suggested_doctors": doctors,
                "related_diseases": diseases,
                "dataset_is_poor_match": True,
            }
            result["llm_debug"] = {
                "provider": provider,
                "raw_text": raw_text,
            }
            return result

        # Otherwise use current RAG pipeline.
        diseases = ChatbotService._filter_diseases_with_llm(message=message, diseases=diseases)

        # Pick doctors from the first specialty that actually returns results.
        doctors: list[dict] = []
        suggested_specialty = diseases[0]["specialty"] if diseases else "General Medicine"

        if diseases:
            seen: set[str] = set()
            specialty_order = []
            for d in diseases:
                spec = d.get("specialty") or ""
                if spec and spec not in seen:
                    seen.add(spec)
                    specialty_order.append(spec)

            for spec in specialty_order:
                doctors = ChatbotService.suggest_doctors(specialty=spec)
                if doctors:
                    suggested_specialty = spec
                    break

        if not doctors:
            # Final fallback: show doctors from any specialty.
            doctors = ChatbotService.suggest_doctors(specialty=None)

        context = ChatbotService._build_context(diseases=diseases, doctors=doctors)
        llm_result = ChatbotService._llm_reply(message=message, context=context)
        result = {
            "reply": llm_result.get("reply"),
            "suggested_specialty": suggested_specialty,
            "suggested_doctors": doctors,
            "related_diseases": diseases,
            "dataset_is_poor_match": False,
        }
        result["llm_debug"] = {
            "provider": llm_result.get("provider"),
            "raw_text": llm_result.get("raw_text"),
        }
        return result
