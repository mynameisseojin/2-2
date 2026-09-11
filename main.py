import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"


def parse_args():
    parser = argparse.ArgumentParser(description="국내 여행 추천 CLI 프로그램")
    parser.add_argument(
        "-date",
        "--date",
        required=False,
        help="여행 날짜: YYYY-MM-DD"
    )

    args = parser.parse_args()

    # --date를 입력하지 않은 경우 직접 입력받기
    if not args.date:
        args.date = input("여행 날짜를 입력하세요 (YYYY-MM-DD): ").strip()

    # 날짜 형식 검증
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        parser.error(
            "날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식으로 입력하세요."
        )

    return args



def require_env(name):
    value = os.getenv(name)
    if not value:
        print(f"오류: {name} 환경변수가 설정되지 않았습니다.")
        sys.exit(1)
    return value


def call_gemini(client, prompt, json_mode=False):
    config = types.GenerateContentConfig(temperature=0.4)
    if json_mode:
        config.response_mime_type = "application/json"
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        contents=prompt,
        config=config,
    )
    return response.text


def get_recommendation(client, date, errors):
    prompt = f'''여행 날짜는 {date}입니다. 국내 여행지 한 곳을 추천하세요.
반드시 다른 설명 없이 아래 JSON 객체만 출력하세요.
{{
  "recommended_city": "string",
  "weather": "string",
  "events": ["string"],
  "reason": "2~4문장 string"
}}
행사/축제는 해당 시기에 있을 법한 후보를 1~3개만 제시하고, 일정 변동 가능성을 명시하세요.'''
    for attempt in range(2):
        try:
            data = json.loads(call_gemini(client, prompt, json_mode=True))
            required = ["recommended_city", "weather", "events", "reason"]
            if not all(key in data for key in required):
                raise ValueError("필수 키가 누락되었습니다.")
            if not isinstance(data["events"], list):
                raise ValueError("events는 배열이어야 합니다.")
            return data
        except Exception as error:
            errors.append({"step": "recommendation" if attempt == 0 else "recommendation_retry", "type": "JSON_PARSE_ERROR", "message": str(error)})
            prompt = f'''{date} 국내 여행 추천 결과를 JSON으로만 출력하세요. 마크다운 금지.
필수 키: recommended_city(string), weather(string), events(array of strings), reason(string).'''
    return {"recommended_city": "데이터 없음", "weather": "데이터 없음", "events": [], "reason": "추천 데이터를 생성하지 못했습니다."}


def search_restaurants(city, api_key, errors):
    try:
        response = requests.get(
            "https://dapi.kakao.com/v2/local/search/keyword.json",
            headers={"Authorization": f"KakaoAK {api_key}"},
            params={"query": f"{city} 맛집", "size": 5, "sort": "accuracy"},
            timeout=15,
        )
        if response.status_code in (401, 403):
            raise RuntimeError(f"인증 실패 HTTP {response.status_code}")
        response.raise_for_status()
        documents = response.json().get("documents", [])
        restaurants = []
        for item in documents:
            restaurants.append({
                "name": item.get("place_name", ""),
                "address": item.get("road_address_name") or item.get("address_name", ""),
                "category": item.get("category_name", ""),
                "url": item.get("place_url", ""),
                "x": float(item["x"]) if item.get("x") else None,
                "y": float(item["y"]) if item.get("y") else None,
            })
        if not restaurants:
            errors.append({"step": "place_search", "type": "EMPTY_RESULT", "message": f"0 results for query={city} 맛집"})
        return restaurants
    except Exception as error:
        errors.append({"step": "place_search", "type": "API_ERROR", "message": str(error)})
        return []


def create_report(client, date, recommendation, restaurants, errors):
    payload = json.dumps({"recommendation": recommendation, "restaurants": restaurants, "errors": errors}, ensure_ascii=False, indent=2)
    prompt = f'''다음 JSON을 바탕으로 {date} 국내 여행 추천 리포트를 Markdown으로 작성하세요.
반드시 다음 제목을 포함하세요: 추천 지역, 추천 이유, 날씨 요약, 행사/축제, 맛집 추천, 1일 일정 제안, 오류 요약(errors).
맛집 배열이 비어 있으면 맛집 추천 아래에 '- 데이터 없음'이라고 쓰세요.
오전/오후/저녁 일정으로 제안하고, 확인되지 않은 정보는 일정 변동 가능성을 표시하세요.
JSON:
{payload}'''
    try:
        return call_gemini(client, prompt)
    except Exception as error:
        errors.append({"step": "report", "type": "GEMINI_ERROR", "message": str(error)})
        return f"# {date} 국내 여행 추천 리포트\n\n리포트 생성에 실패했습니다.\n\n## 오류 요약(errors)\n{json.dumps(errors, ensure_ascii=False, indent=2)}"


def main():
    load_dotenv()
    args = parse_args()
    gemini_key = require_env("GEMINI_API_KEY")
    kakao_key = require_env("KAKAO_REST_API_KEY")
    RESULTS_DIR.mkdir(exist_ok=True)
    errors = []
    client = genai.Client(api_key=gemini_key)

    print("[1/3] 1차 추천 생성 중(Gemini)...")
    recommendation = get_recommendation(client, args.date, errors)
    print(f"  - recommended_city: {recommendation['recommended_city']}")

    print("[2/3] 맛집 검색 중(카카오 Local)...")
    restaurants = search_restaurants(recommendation["recommended_city"], kakao_key, errors)
    print(f"  - 맛집 {len(restaurants)}곳 검색 완료")

    raw = {"date": args.date, "recommendation": recommendation, "restaurants": restaurants, "errors": errors}
    json_path = RESULTS_DIR / f"{args.date}_travel_data.json"
    json_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[3/3] 최종 리포트 생성 중(Gemini)...")
    report = create_report(client, args.date, recommendation, restaurants, errors)
    md_path = RESULTS_DIR / f"{args.date}_travel_plan.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"  - 리포트 생성 완료\n완료! {md_path} 를 확인하세요.")


if __name__ == "__main__":
    main()