import os
import re
import asyncio
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from prisma import Prisma



load_dotenv()

def split_hierarchical(text, filename_category):
    chunks = []
    
    # 💡 무진님의 검증된 정규식 완벽 적용! (괄호가 있는 '제O조(' 기준으로 통째로 자름)
    parts = re.split(r'(?=제\s*\d+\s*조(?:의\s*\d+)?\s*\()', text)
    
    current_category = filename_category
    current_chapter = "일반사항" 

    for part in parts:
        part = part.strip()
        if not part:
            continue

        lines = part.split('\n')
        first_line = lines[0].strip()
        
        # 첫 줄이 조항으로 시작하는지 확인
        match_article = re.match(r'^제\s*(\d+)\s*조(?:의\s*(\d+))?', first_line)

        if match_article:
            num = match_article.group(1)
            sub = match_article.group(2)
            article_num = f"제{num}조" + (f"의{sub}" if sub else "")
            
            content_lines = []
            next_category = current_category
            next_chapter = current_chapter

            for line in lines:
                line_clean = line.strip()
                if not line_clean: continue
                
                # 목차 및 찌꺼기 무시
                if '····' in line_clean or '....' in line_clean: continue
                if re.match(r'^-?\s*\d+\s*-?$', line_clean): continue
                if "한국순환자원유통지원센터" in line_clean and "규정집" in line_clean: continue

                is_metadata = False
                
                # 덩어리 안에서 '장'이 감지되면 다음 조항을 위해 상태 업데이트
                match_chapter = re.match(r'^제\s*\d+\s*장\s*(.*)', line_clean)
                if match_chapter:
                    next_chapter = line_clean
                    is_metadata = True

                if not is_metadata:
                    content_lines.append(line_clean)
            
            clean_content = "\n".join(content_lines)
            
            # DB 저장용 청크 생성
            chunks.append({
                "category": current_category,
                "chapter": current_chapter,
                "article_num": article_num,
                "content": f"[{current_category} / {current_chapter}]\n{clean_content}"
            })
            
            current_category = next_category
            current_chapter = next_chapter

        else:
            # 문서 맨 앞 서론/목차 부분에서 '장' 정보 스캔
            for line in lines:
                line_clean = line.strip()
                match_chapter = re.match(r'^제\s*\d+\s*장\s*(.*)', line_clean)
                if match_chapter:
                    current_chapter = line_clean

    return chunks

async def main():
    db = Prisma()
    await db.connect()
    print("DB 연결 성공")

    print("🧹 기존 Policy 데이터를 모두 삭제합니다...")
    await db.execute_raw('TRUNCATE TABLE "Policy";')

    # 💡 터미널 로그에 맞게 파일명 지정 (실제 폴더 내 파일명과 동일해야 합니다)
    pdf_targets = {
        "복리후생내용.pdf": "복리후생비 지급 내규",
        "업무차량관리내용.pdf": "업무용차량 관리 내규",
        "휴가내용.pdf": "복무에 관한 내규",
        "동호회내용.pdf": "사내동호회 설립 및 지원금 지급에 관한 내규"
    }
    
    all_articles = []
    
    for pdf_file, category_name in pdf_targets.items():
        if not os.path.exists(pdf_file):
            print(f"⚠️ '{pdf_file}' 파일이 폴더에 없습니다. 이름을 확인해 주세요!")
            continue
            
        print(f"📄 {pdf_file} 분석 중...")
        try:
            loader = PyPDFLoader(pdf_file)
            pages = loader.load()
            full_text = "\n".join([page.page_content for page in pages])
            
            file_articles = split_hierarchical(full_text, category_name)
            print(f"   -> {len(file_articles)}개 조항 추출 완료")
            all_articles.extend(file_articles)
        except Exception as e:
            print(f"   ❌ {pdf_file} 분석 실패: {e}")

    print(f"\n✂️ 총 {len(all_articles)}개의 통합 조항이 준비되었습니다.")
    
    print("🧠 한국어 전용 AI 모델 로드 중 (최초 1회 로딩 시 시간이 조금 걸립니다)...")
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    
    success_count = 0
    for chunk in all_articles:
        if len(chunk["content"]) < 30: 
            continue

        try:
            vector = embeddings.embed_query(chunk["content"])

            # 💡 form_url 컬럼에 빈 배열(text[])을 안전하게 넣도록 PostgreSQL 문법 적용
            await db.execute_raw(
                '''
                INSERT INTO "Policy" (category, chapter, article_num, content, embedding, form_url)
                VALUES ($1, $2, $3, $4, $5::vector, $6::text[])
                ''',
                chunk["category"], chunk["chapter"], chunk["article_num"], chunk["content"], vector, []
            )
            print(f"   ✔️ [{chunk['category']}] {chunk['article_num']} 저장 완료")
            success_count += 1
        except Exception as e:
            print(f"   ❌ 저장 실패 ({chunk['article_num']}): {e}")

    print(f"\n🎉 작업 완료! 깨끗해진 DB에 총 {success_count}개의 고정밀 조항이 저장되었습니다!")
    await db.disconnect()

if __name__ == "__main__":
    os.environ["PYTHONUTF8"] = "1"
    asyncio.run(main())