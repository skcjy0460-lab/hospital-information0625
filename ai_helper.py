"""
Google Gemini API를 이용해 관리자가 입력한 진료과 원문 텍스트를
표준 진료과명으로 매핑(표준화)하는 보조 모듈입니다.

예) "정형 외과, 신경외과, 도수치료" 입력
    -> [{"raw": "정형 외과", "standardized": "정형외과", "is_custom": False},
        {"raw": "신경외과", "standardized": "신경외과", "is_custom": False},
        {"raw": "도수치료", "standardized": "도수치료", "is_custom": True}]

AI 호출이 실패하거나 응답 형식이 깨졌을 경우를 대비해, 항상 안전하게
원본 텍스트를 그대로 반환하는 폴백(fallback) 로직을 포함합니다.
실무에서는 외부 API 호출이 항상 성공한다고 가정하면 안 되므로,
이 폴백 처리가 실제로 매우 중요합니다.

※ 구버전 `google-generativeai` 패키지는 지원이 종료되어, 최신 통합 SDK인
  `google-genai` 패키지(from google import genai)를 사용합니다.
"""
import json
import streamlit as st
from google import genai

from constants import STANDARD_DEPARTMENTS

# 사용 모델: 비용 효율적인 flash 계열을 기본값으로 사용합니다.
# 추후 Google AI Studio에서 더 최신/적합한 모델이 출시되면 이 값만 교체하면 됩니다.
GEMINI_MODEL_NAME = "gemini-2.5-flash"


@st.cache_resource
def _get_client() -> genai.Client:
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


def _fallback_split(raw_text: str) -> list[dict]:
    """AI 호출 실패 시, 쉼표 기준으로만 분리해서 원본 그대로 반환합니다."""
    items = [x.strip() for x in raw_text.split(",") if x.strip()]
    return [{"raw": item, "standardized": item, "is_custom": True} for item in items]


def standardize_departments(raw_text: str) -> list[dict]:
    """
    쉼표로 구분된 진료과 원문 텍스트를 표준 진료과명으로 매핑합니다.

    Args:
        raw_text: 관리자가 입력한 원본 텍스트 (예: "정형 외과, 내과, 신경외과")

    Returns:
        [{"raw": str, "standardized": str, "is_custom": bool}, ...] 형태의 리스트.
        표준 목록에 적합한 항목이 없으면 is_custom=True로 표시되고,
        standardized 값은 원본 텍스트가 그대로 사용됩니다.
    """
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return []

    try:
        client = _get_client()
        prompt = f"""당신은 한국 의료기관의 진료과 명칭을 표준화하는 전문가입니다.

[표준 진료과 목록]
{", ".join(STANDARD_DEPARTMENTS)}

[입력 텍스트]
{raw_text}

[작업 지시]
1. 입력 텍스트를 쉼표(,) 기준으로 분리하세요.
2. 분리된 각 항목을 위 표준 진료과 목록 중 가장 적합한 항목으로 매핑하세요.
   (예: "정형 외과" -> "정형외과", "이비인후과(귀,코,목)" -> "이비인후과")
3. 표준 목록에 적합한 항목이 전혀 없는 경우(예: "도수치료", "건강검진" 같은
   진료과 명칭이 아닌 입력), standardized 값에 원본 텍스트를 그대로 쓰고
   is_custom을 true로 표시하세요.
4. 입력 항목 개수와 동일한 개수의 결과 객체를 반환하세요.

[출력 형식]
오직 JSON 배열만 출력하세요. 설명, 마크다운, 코드블록 기호(```)를 절대 포함하지 마세요.
각 객체 형식: {{"raw": "원본입력", "standardized": "표준진료과명", "is_custom": true 또는 false}}
"""
        response = client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=prompt,
        )
        text = (response.text or "").strip()
        # 모델이 코드블록을 붙이는 경우에 대한 방어 처리
        text = text.replace("```json", "").replace("```", "").strip()

        result = json.loads(text)
        if not isinstance(result, list) or not result:
            raise ValueError("AI 응답이 비어있거나 리스트 형식이 아닙니다.")

        # 필수 키 검증 - 형식이 어긋나면 폴백으로 전환
        for item in result:
            if "raw" not in item or "standardized" not in item:
                raise ValueError("AI 응답에 필수 키가 없습니다.")
            item.setdefault("is_custom", item["standardized"] not in STANDARD_DEPARTMENTS)

        return result

    except Exception as e:
        st.warning(
            f"AI 표준화 처리 중 문제가 발생하여 원본 입력을 그대로 사용합니다. "
            f"(직접 수정 가능) — 상세: {e}"
        )
        return _fallback_split(raw_text)


def extract_hospital_info_from_text(raw_text: str) -> dict:
    """
    병원 홈페이지/네이버 플레이스 등에서 복사한 자유 텍스트에서
    병원 등록에 필요한 정보를 한 번에 추출합니다.

    Returns:
        {
            "name": str, "sido": str, "sigungu": str, "address": str,
            "main_specialty": str, "special_features": str,
            "departments": [str, ...],
            "hotline_phone": str, "hotline_note": str,
            "feature_highlights": [str, ...],
        }
        추출 실패 시 빈 dict를 반환합니다 (호출부에서 경고 메시지를 먼저 보여줍니다).
    """
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return {}

    try:
        client = _get_client()
        prompt = f"""당신은 병원 홈페이지나 정보 페이지의 텍스트에서 병원 등록 정보를 추출하는 전문가입니다.

[표준 진료과 목록 (참고용)]
{", ".join(STANDARD_DEPARTMENTS)}

[원본 텍스트]
{raw_text}

[작업 지시]
위 텍스트에서 아래 항목들을 최대한 추출하세요. 텍스트에 없는 정보는 빈 문자열("") 또는 빈 배열([])로 두세요.
추측해서 지어내지 말고, 텍스트에 실제로 있는 내용만 추출하세요.

[출력 형식]
오직 JSON 객체만 출력하세요. 설명, 마크다운, 코드블록 기호(```)를 절대 포함하지 마세요.
{{
  "name": "병원명",
  "sido": "시/도 (예: 대구광역시, 서울특별시 형식으로)",
  "sigungu": "시/군/구",
  "address": "상세 주소",
  "main_specialty": "메인 진료과목 (있다면)",
  "special_features": "특정과/특화 진료 (있다면, 짧게)",
  "departments": ["진료과1", "진료과2"],
  "hotline_phone": "전화번호",
  "hotline_note": "문의/상담 가능 시간 등 안내문구 (있다면)",
  "feature_highlights": ["병원의 특징이나 보유 장비, 운영 프로그램 등을 항목별로"]
}}
"""
        response = client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=prompt,
        )
        text = (response.text or "").strip()
        text = text.replace("```json", "").replace("```", "").strip()

        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("AI 응답이 객체(dict) 형식이 아닙니다.")
        return result

    except Exception as e:
        st.warning(f"AI 자동분류 중 문제가 발생했습니다. 직접 입력해주세요. — 상세: {e}")
        return {}
