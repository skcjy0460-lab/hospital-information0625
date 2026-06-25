"""
엑셀 일괄 등록 기능에서 사용하는 양식 생성 유틸리티.
"""
import io
import pandas as pd

TEMPLATE_COLUMNS = [
    "병원명", "시도", "시군구", "주소", "메인진료과목", "특정과_특화진료",
    "진료과목(쉼표구분)", "핫라인전화", "핫라인안내문구", "병원특징(세미콜론구분)",
]


def generate_excel_template() -> bytes:
    """일괄 등록용 빈 엑셀 양식(예시 1행 포함)을 바이트로 생성합니다."""
    sample = [{
        "병원명": "예시병원",
        "시도": "대구광역시",
        "시군구": "수성구",
        "주소": "달구벌대로 0000",
        "메인진료과목": "정형외과(관절/척추 특화)",
        "특정과_특화진료": "척추센터, 인공관절센터",
        "진료과목(쉼표구분)": "정형외과, 신경외과, 재활의학과",
        "핫라인전화": "053-000-0000",
        "핫라인안내문구": "평일 09:00~18:00 상담 가능",
        "병원특징(세미콜론구분)": "최신 3.0T MRI 보유;24시간 응급실 운영",
    }]
    df = pd.DataFrame(sample, columns=TEMPLATE_COLUMNS)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="병원목록")
    return buffer.getvalue()
