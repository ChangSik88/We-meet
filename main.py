import os
import boto3
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from prisma import Prisma
from pydantic import BaseModel
from ai import stream_chat
from typing import List, Optional # 🚀 Optional 추가 (sessionId를 안 보낼 수도 있기 때문)

load_dotenv()

db = Prisma()

# 1. lifespan 먼저 정의 (🚀 서버 시작 시 1번 더미 유저 자동 생성 추가)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # [서버 켜질 때 실행]
    await db.connect()
    print("✅ 서버 시작: Prisma DB 연결 성공")
    
    # 🚀 PoC용 더미 유저(ID: 1)가 없으면 자동 생성 로직
    existing_user = await db.user.find_unique(where={"id": 1})
    if not existing_user:
        await db.user.create(
            data={
                "id": 1,
                "email": "test@wemeet.com",
                "name": "PoC테스터"
            }
        )
        print("👤 PoC용 더미 유저(ID: 1) 생성 완료")
    
    yield  # 💡 이 지점에서 FastAPI 서버가 메인 작동을 시작하며 대기합니다.
    
    # [서버 꺼질 때 실행]
    await db.disconnect()
    print("🛑 서버 종료: Prisma DB 연결 해제")

# 2. FastAPI 앱을 '딱 한 번만' 생성하면서 lifespan 연결
app = FastAPI(title="We-meet AI Agent API", lifespan=lifespan)

# 3. 생성된 앱에 CORS 미들웨어(방패) 장착
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🚀 AWS S3 클라이언트 초기화
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)
BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")

# ---------------------------------------------------------
# 💬 [AI 채팅 관련 API]
# ---------------------------------------------------------

# 🚀 채팅 요청 규격 (sessionId 추가)
class ChatRequest(BaseModel):
    Question: str
    sessionId: Optional[int] = None  # None이면 새 채팅방 생성으로 간주

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """사용자 질문 처리 API"""
    return StreamingResponse(
        # 🚀 ai.py의 stream_chat으로 sessionId를 함께 넘겨줍니다.
        stream_chat(request.Question, db, request.sessionId),
        media_type="text/event-stream"
    )

# ---------------------------------------------------------
# 🗂️ [채팅방(세션) 및 메시지 관리 API - 신규 추가]
# ---------------------------------------------------------

@app.get("/api/sessions")
async def get_my_sessions(userId: int = 1):
    """좌측 사이드바용: 1번 유저의 채팅방 목록을 최신순으로 반환"""
    sessions = await db.chatsession.find_many(
        where={"userId": userId},
        order={"createdAt": "desc"}
    )
    return {"sessions": sessions}

@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: int):
    """채팅방 클릭 시: 해당 채팅방의 과거 대화 내역 반환"""
    messages = await db.message.find_many(
        where={"sessionId": session_id},
        order={"createdAt": "asc"} # 옛날 메시지부터 순서대로 보여주기 위해 asc
    )
    return {"messages": messages}

# ---------------------------------------------------------
# 📁 [규정 및 폼 파일 관리 API - 기존 유지]
# ---------------------------------------------------------

@app.post("/api/upload-form")
async def upload_form_to_s3(file: UploadFile = File(...)):
    """관리자가 양식 파일을 S3에 업로드하고 URL을 받아오는 API"""
    try:
        file_extension = file.filename.split(".")[-1]
        unique_filename = f"forms/{uuid.uuid4()}.{file_extension}"
        
        s3_client.upload_fileobj(
            file.file, 
            BUCKET_NAME, 
            unique_filename,
            ExtraArgs={"ContentType": file.content_type} 
        )
        
        region = os.getenv("AWS_REGION")
        s3_url = f"https://{BUCKET_NAME}.s3.{region}.amazonaws.com/{unique_filename}"
        
        return {"message": "업로드 성공", "form_url": s3_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 업로드 실패: {str(e)}")
    
class FormUpdateRequest(BaseModel):
    form_url: List[str] 

@app.patch("/api/policies/{policy_id}/form-url")
async def link_form_to_policy(policy_id: int, request: FormUpdateRequest):
    try:
        updated_policy = await db.policy.update(
            where={"id": policy_id},
            data={"form_url": request.form_url} 
        )
        return {
            "message": "성공적으로 모든 URL이 연결되었습니다.",
            "form_url": updated_policy.form_url
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/policies")
async def get_all_policies():
    """관리자가 파일 URL을 매핑할 때 조항 ID를 확인할 수 있도록 목록을 제공합니다."""
    policies = await db.policy.find_many(
        order={"id": "asc"}
    )
    
    result = []
    for p in policies:
        result.append({
            "id": p.id,
            "category": p.category,
            "chapter": p.chapter,
            "article_num": p.article_num,
            "form_url": p.form_url
        })
    return {"policies": result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)