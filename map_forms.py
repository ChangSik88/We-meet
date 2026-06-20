import os
import asyncio
from dotenv import load_dotenv
from prisma import Prisma
from urllib.parse import unquote_plus

load_dotenv()

async def main():
    db = Prisma()
    await db.connect()
    print("✅ 로컬 DB 연결 성공")
    print("🔄 S3 양식 URL을 해당 규정 조항에 일괄 매핑(UPDATE)하기 시작합니다...\n")

    # 💡 팀장님이 작성해주신 리스트를 카테고리/조항별로 매핑 데이터 정제
    # PostgreSQL의 text[] 배열 특성을 살려, 순서대로 차곡차곡 쌓아(array_append) 넣습니다.
    form_mappings = [
        # 1. 업무용차량 관리 내규
        {"cat": "업무용차량 관리 내규", "article": "제13조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/업무차량/차량운행기록부(13%2C+14조).pdf"},
        {"cat": "업무용차량 관리 내규", "article": "제14조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/업무차량/차량운행기록부(13%2C+14조).pdf"},
        {"cat": "업무용차량 관리 내규", "article": "제16조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/업무차량/차량사고보고서(16조).pdf"},

        # 2. 복무에 관한 내규 (휴가)
        {"cat": "복무에 관한 내규", "article": "제9조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/휴가/경조특별휴가(9조관련).pdf"},
        {"cat": "복무에 관한 내규", "article": "제17조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/휴가/거주자이전자금지원기준(17조관련).pdf"},
        {"cat": "복무에 관한 내규", "article": "제8조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/휴가/휴가신청서(8%2C9%2C10조+관련).pdf"},
        {"cat": "복무에 관한 내규", "article": "제9조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/휴가/휴가신청서(8%2C9%2C10조+관련).pdf"},
        {"cat": "복무에 관한 내규", "article": "제10조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/휴가/휴가신청서(8%2C9%2C10조+관련).pdf"},
        {"cat": "복무에 관한 내규", "article": "제8조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/휴가/휴가취소신청서(8%2C9%2C10조+관련).pdf"},
        {"cat": "복무에 관한 내규", "article": "제9조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/휴가/휴가취소신청서(8%2C9%2C10조+관련).pdf"},
        {"cat": "복무에 관한 내규", "article": "제10조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/휴가/휴가취소신청서(8%2C9%2C10조+관련).pdf"},
        {"cat": "복무에 관한 내규", "article": "제11조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/휴가/출장명령서(11조+관련).pdf"},

        # 3. 사내동호회 설립 및 지원금 지급에 관한 내규
        {"cat": "사내동호회 설립 및 지원금 지급에 관한 내규", "article": "제3조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/동호회/동호회등록신청서(3조관련).pdf"},
        {"cat": "사내동호회 설립 및 지원금 지급에 관한 내규", "article": "제4조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/동호회/동호회활동보고서(4조관련).pdf"},

        # 4. 복리후생비 지급 내규
        {"cat": "복리후생비 지급 내규", "article": "제4조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/복리후생/학자금보조비지급신청서(4조관련).pdf"},
        {"cat": "복리후생비 지급 내규", "article": "제6조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/복리후생/경조비지급기준(6조관련).pdf"},
        {"cat": "복리후생비 지급 내규", "article": "제2조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/복리후생/복리후생비지급기준(2%2C3%2C8조+관련).pdf"},
        {"cat": "복리후생비 지급 내규", "article": "제3조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/복리후생/복리후생비지급기준(2%2C3%2C8조+관련).pdf"},
        {"cat": "복리후생비 지급 내규", "article": "제8조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/복리후생/복리후생비지급기준(2%2C3%2C8조+관련).pdf"},
        {"cat": "복리후생비 지급 내규", "article": "제9조", "url": "https://we-meet-s3-policy-file-138410485569-ap-northeast-2-an.s3.ap-northeast-2.amazonaws.com/복리후생/복지카드지원범위및대상(9조관련).pdf"}
    ]

    success_count = 0
    
    for item in form_mappings:
        try:
            # 🚀 인코딩된 URL을 순수 원본 텍스트(쉼표, 띄어쓰기 복구)로 강제 변환
            clean_url = unquote_plus(item["url"])

            await db.execute_raw(
                '''
                UPDATE "Policy"
                SET form_url = array_append(form_url, $1)
                WHERE category = $2 AND article_num = $3
                ''',
                clean_url, item["cat"], item["article"]  # 👈 item["url"] 대신 clean_url 사용
            )
            print(f"   🔗 매핑 성공: [{item['cat']}] {item['article']} -> {clean_url.split('/')[-1]}")
            success_count += 1
        except Exception as e:
            print(f"   ❌ 매핑 실패: [{item['cat']}] {item['article']} -> {e}")

    print(f"\n🎉 작업 완료! 총 {success_count}개의 파일 매핑 레코드가 업데이트되었습니다.")
    await db.disconnect()

if __name__ == "__main__":
    os.environ["PYTHONUTF8"] = "1"
    asyncio.run(main())