# 국내 여행 추천 CLI 프로그램

여행 날짜를 입력하면 **Google Gemini API**로 여행 지역·날씨·행사 후보를 JSON으로 생성하고, Kakao Local API로 해당 지역 맛집을 검색한 뒤 Markdown 여행 리포트를 생성합니다.

## 1. 설치

Python 3.10 이상에서 실행합니다.

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. API 키 설정

`.env.example`을 `.env`로 복사한 뒤 실제 키를 입력합니다.

```env
GEMINI_API_KEY=실제_Gemini_API_키
KAKAO_REST_API_KEY=실제_Kakao_REST_API_키
GEMINI_MODEL=gemini-2.5-flash
```

Gemini API 키는 Google AI Studio에서 발급할 수 있습니다. 키는 코드, README, 로그, 결과 JSON에 작성하지 마세요. `.env`는 `.gitignore`에 포함되어 있습니다.

## 3. 실행

```bash
python main.py --date "2026-03-15"
# 또는
python main.py -date "2026-03-15"
```

날짜는 `YYYY-MM-DD` 형식이어야 합니다.

## 4. 결과물

실행 후 `results/`에 생성됩니다.

- `YYYY-MM-DD_travel_data.json`: 1차 추천, 맛집 목록, errors
- `YYYY-MM-DD_travel_plan.md`: 최종 여행 리포트

## 5. API 흐름

1. Gemini API에 여행 날짜를 전달하고 `response_mime_type=application/json`으로 구조화된 추천 결과를 받습니다.
2. 추천 결과의 `recommended_city`를 Kakao Local 키워드 검색 API의 `query`로 전달합니다. Kakao API는 `GET` 요청과 `Authorization: KakaoAK ...` 헤더를 사용합니다.
3. 추천 JSON과 맛집 목록을 Gemini에 전달해 Markdown 리포트를 생성합니다.

검색 결과가 0건이거나 Kakao API가 실패해도 맛집을 빈 배열로 처리하고 리포트 생성은 계속합니다. Gemini JSON 파싱 실패 시 최대 1회 재시도합니다.

## 6. 대표 오류 대응

- 인증 오류: API 키, 환경변수명, Kakao 헤더 설정 확인
- 쿼터 오류: 사용량과 결제/제한 확인
- 네트워크 오류: timeout 및 재실행 확인
- 파싱 오류: Gemini JSON 응답 설정과 필수 키 검증 확인

## 7. 보안 주의

`.env`의 실제 키를 GitHub, 과제 제출물, 화면 캡처, 로그에 포함하지 마세요. 키가 노출되었다면 즉시 해당 서비스에서 폐기하고 새 키를 발급하세요.
