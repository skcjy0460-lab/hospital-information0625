"""
건강보험심사평가원(HIRA) '병원정보서비스' 공공데이터 Open API 연동.

병원명으로 검색하면 주소/전화번호/진료과목 등 기본정보를 가져와
관리자가 직접 타이핑하지 않고 자동으로 채울 수 있게 해줍니다.

API 신청 방법
-------------
1. https://www.data.go.kr 회원가입/로그인
2. "건강보험심사평가원_병원정보서비스" 검색 (또는 데이터셋 번호 15001698)
   https://www.data.go.kr/data/15001698/openapi.do
3. "활용신청" 클릭 → 활용 목적 작성 → 신청
   (개발계정은 보통 즉시 자동승인되며, 무료입니다)
4. 마이페이지 > 개발계정 상세보기에서 발급된 인증키 중
   **"Decoding" 키**(원본 그대로의 키)를 복사해서 GEMINI_API_KEY와 마찬가지로
   secrets.toml의 HIRA_API_KEY에 넣어주세요.
   ⚠️ "Encoding" 키를 넣으면 이중 인코딩되어 인증 오류가 날 수 있습니다.

⚠️ 주의: 이 모듈은 공공데이터포털에 공개된 표준 스펙을 기준으로 작성되었습니다.
   실제 응답 구조가 다르게 오는 극히 드문 경우, 화면에 표시되는 원본 응답을
   확인하면서 파싱 로직을 미세 조정해야 할 수 있습니다.
"""
import requests
import streamlit as st

BASIS_URL = "https://apis.data.go.kr/B551182/hospInfoService/getHospBasisList"
DEPT_URL = "https://apis.data.go.kr/B551182/hospInfoService/getDgsbjtInfo"

REQUEST_TIMEOUT = 10


def _get_service_key() -> str:
    return st.secrets.get("HIRA_API_KEY", "")


def _parse_items(payload: dict) -> list[dict]:
    """data.go.kr 표준 응답 포맷(response > body > items > item)을 안전하게 파싱합니다."""
    try:
        body = payload.get("response", {}).get("body", {})
        items = body.get("items")
        if not items:
            return []
        item = items.get("item", []) if isinstance(items, dict) else items
        if isinstance(item, dict):
            return [item]
        if isinstance(item, list):
            return item
        return []
    except (AttributeError, TypeError):
        return []


def search_hospital_basis(name: str, num_of_rows: int = 10) -> list[dict]:
    """
    병원명으로 병원 기본정보를 검색합니다.
    반환 항목 예: yadmNm(병원명), addr(주소), telno(전화번호),
                 sidoCdNm(시도명), sgguCdNm(시군구명), ykiho(암호화된 요양기호, 진료과목 조회에 필요)
    """
    service_key = _get_service_key()
    if not service_key:
        raise ValueError("HIRA_API_KEY가 secrets.toml에 설정되어 있지 않습니다.")

    params = {
        "serviceKey": service_key,
        "yadmNm": name,
        "pageNo": 1,
        "numOfRows": num_of_rows,
        "_type": "json",
    }
    response = requests.get(BASIS_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    return _parse_items(payload)


def fetch_hospital_departments(ykiho: str) -> list[str]:
    """요양기호(ykiho)로 해당 병원의 진료과목 명칭 목록을 조회합니다."""
    service_key = _get_service_key()
    if not service_key or not ykiho:
        return []

    params = {
        "serviceKey": service_key,
        "ykiho": ykiho,
        "pageNo": 1,
        "numOfRows": 50,
        "_type": "json",
    }
    response = requests.get(DEPT_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    items = _parse_items(payload)
    return [it.get("dgsbjtCdNm") for it in items if it.get("dgsbjtCdNm")]
