# We-meet

[cloud we-meet 프로젝트] 사내 업무 규정 AI 에이전트

# 프로젝트 폴더 구조에 관하여

- 귀찮아서 폴더 안나누고 걍 루트에 다 만들었습니다. 파일 별로 안많으니까 ㄱㅊㄱㅊ

# 가상환경 활성화

venv\Scripts\activate

# 가상환경 종료

deactive

# 서버 활성화

uvicorn main:app --reload

# 프론트용 서버 활성화

python -m http.server 3000

# AWS 서버 활성화

nohup uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
