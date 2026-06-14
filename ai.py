# ai.py
import json
import asyncio
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

load_dotenv()

# 1. 모델 초기화 (서버 켜질 때 한 번만 로드)
embeddings = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7)

async def stream_chat(query: str, db, session_id: int = None):
    try:
        yield f"data: {json.dumps({'type': 'status', 'message': '🔍 사내 규정 데이터베이스를 검색 중입니다...'}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.5)

        # 🚀 1. 세션(채팅방) 관리 & 유저 메시지 저장
        if not session_id:
            # 첫 질문이면 새 채팅방(Session) 생성 (제목은 질문의 첫 15글자)
            title = query[:15] + "..." if len(query) > 15 else query
            new_session = await db.chatsession.create(
                data={"userId": 1, "title": title}
            )
            session_id = new_session.id
            
            # 새 세션이 생성되었음을 프론트엔드에 알림 (URL 업데이트용)
            yield f"data: {json.dumps({'type': 'session_info', 'sessionId': session_id}, ensure_ascii=False)}\n\n"

        # 유저의 질문 DB에 저장
        await db.message.create(
            data={"sessionId": session_id, "role": "user", "content": query}
        )

        # 🚀 2. 과거 대화 내역(History) 불러오기
        past_messages = await db.message.find_many(
            where={"sessionId": session_id},
            order={"createdAt": "asc"}
        )
        
        # 프롬프트에 넣을 수 있게 텍스트로 결합
        history_text = ""
        for msg in past_messages[:-1]: # 방금 넣은 현재 질문은 제외
            role_name = "사용자" if msg.role == "user" else "AI"
            history_text += f"[{role_name}]: {msg.content}\n"

        # 3. 벡터 DB 검색 (기존 로직 동일)
        query_vector = embeddings.embed_query(query)
        vector_str = '[' + ','.join(map(str, query_vector)) + ']'

        search_results = await db.query_raw(
            '''
            SELECT category, chapter, article_num, content, form_url 
            FROM "Policy" 
            ORDER BY embedding <=> $1::vector 
            LIMIT 3
            ''',
            vector_str
        )

        yield f"data: {json.dumps({'type': 'status', 'message': '💡 관련 규정을 찾았습니다. 답변을 정리 중입니다...'}, ensure_ascii=False)}\n\n"

        # 4. 컨텍스트 조립 (기존 로직 동일)
        context_text = ""
        for idx, row in enumerate(search_results):
            category = row.get("category", "")
            article = row.get("article_num", "")
            content = row.get("content", "")
            form_url = row.get("form_url", [])
            
            context_text += f"\n[관련규정 {idx+1}] {category} {article}\n{content}\n"
            if form_url and len(form_url) > 0:
                for f_idx, url in enumerate(form_url):
                    context_text += f"▶ 첨부양식 URL {f_idx+1}: {url}\n"

        # 🚀 5. 프롬프트 수정 (과거 대화 내역 포함)
        prompt_template = PromptTemplate.from_template(
            """당신은 사내 규정을 안내하는 친절하고 전문적인 AI 어시스턴트입니다.
            반드시 아래 제공된 [관련규정]을 바탕으로 사용자의 질문에 답변하세요.
            이전 대화 맥락인 [이전 대화 내역]이 있다면 이를 참고하여 자연스럽게 답변하세요.
            
            [규칙]
            1. 규정에 없는 내용은 "해당 내용은 규정집에서 찾을 수 없습니다"라고 답하세요.
            2. 관련규정에 '첨부양식 URL'들이 있다면 답변 끝에 관련된 양식들을 모두 나열하여 '[양식 이름](S3 URL 주소)' 형태로 안내하세요.
            
            [관련규정]
            {context}

            [이전 대화 내역]
            {history}

            [사용자 질문]
            {question}
            """
        )
        prompt = prompt_template.format(context=context_text, history=history_text, question=query)

        # 6. 답변 생성
        response = await llm.ainvoke(prompt)
        final_answer = response.content

        # 🚀 7. AI 답변을 DB에 저장
        await db.message.create(
            data={"sessionId": session_id, "role": "ai", "content": final_answer}
        )

        # 8. 프론트엔드로 전송
        yield f"data: {json.dumps({'type': 'text', 'chunk': final_answer}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"