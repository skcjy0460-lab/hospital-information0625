"""
Supabase 연동 데이터 액세스 레이어.

보안 설계 원칙
--------------
- 환자(공개) 조회는 ANON KEY 클라이언트를 사용합니다.
  공개 조회 가능한 범위는 Supabase의 RLS(Row Level Security) SELECT 정책으로
  제한됩니다. (supabase_schema.sql 참고 — is_active = true 인 병원만 노출)
- 관리자 등록/수정/삭제는 SERVICE ROLE KEY 클라이언트를 사용합니다.
  SERVICE ROLE KEY는 RLS를 완전히 우회하므로 절대로 외부(브라우저, 클라이언트
  코드)에 노출되면 안 되며, Streamlit Secrets에만 저장해야 합니다.
  이 앱은 서버 사이드(Streamlit 서버)에서만 실행되므로 안전합니다.
"""
import uuid
import streamlit as st
from supabase import create_client, Client

BUCKET_NAME = "hospital-photos"


@st.cache_resource
def get_anon_client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])


@st.cache_resource
def get_admin_client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_ROLE_KEY"])


# ---------------------------------------------------------------------------
# 환자(공개) 조회용 함수 - ANON 클라이언트 사용
# ---------------------------------------------------------------------------

def fetch_hospitals(sido: str = None, sigungu: str = None, keyword: str = None, department: str = None):
    """공개(is_active=true) 병원 목록을 필터 조건에 맞게 조회합니다."""
    client = get_anon_client()
    query = (
        client.table("hospitals")
        .select("*, departments(*), medical_staff(*), business_hours(*)")
        .eq("is_active", True)
        .order("name")
    )
    if sido:
        query = query.eq("sido", sido)
    if sigungu:
        query = query.ilike("sigungu", f"%{sigungu}%")
    if keyword:
        query = query.ilike("name", f"%{keyword}%")

    response = query.execute()
    hospitals = response.data or []

    # 진료과 필터는 중첩 테이블(departments) 조건이라 PostgREST 단일 쿼리로
    # 처리하기 까다로워, 결과를 받아온 뒤 Python에서 필터링합니다.
    # (병원 수가 수백 단위를 넘어가면 DB 함수/RPC로 옮기는 것을 권장합니다.)
    if department:
        hospitals = [
            h for h in hospitals
            if department in [d["department_name"] for d in h.get("departments", [])]
        ]
    return hospitals


# ---------------------------------------------------------------------------
# 관리자용 함수 - SERVICE ROLE 클라이언트 사용 (RLS 우회)
# ---------------------------------------------------------------------------

def fetch_all_hospitals_admin():
    """비공개 병원을 포함한 전체 병원 목록을 조회합니다 (관리자 전용)."""
    client = get_admin_client()
    response = (
        client.table("hospitals")
        .select("*, departments(*), medical_staff(*), business_hours(*)")
        .order("name")
        .execute()
    )
    return response.data or []


def create_hospital(data: dict) -> str:
    client = get_admin_client()
    response = client.table("hospitals").insert(data).execute()
    return response.data[0]["id"]


def update_hospital(hospital_id: str, data: dict):
    client = get_admin_client()
    client.table("hospitals").update(data).eq("id", hospital_id).execute()


def set_hospital_active(hospital_id: str, is_active: bool):
    update_hospital(hospital_id, {"is_active": is_active})


def delete_hospital_permanently(hospital_id: str):
    """병원과 연관된 진료과/의료진/진료시간 데이터를 영구 삭제합니다.

    departments/medical_staff/business_hours 테이블은 hospital_id에 대해
    ON DELETE CASCADE로 설정되어 있어 hospitals 행만 삭제하면 자동으로
    함께 삭제됩니다. (Storage에 업로드된 사진 파일은 별도 삭제가 필요합니다.)
    """
    client = get_admin_client()
    client.table("hospitals").delete().eq("id", hospital_id).execute()


def replace_departments(hospital_id: str, dept_rows: list[dict]):
    """기존 진료과를 모두 삭제하고 새 목록으로 교체합니다."""
    client = get_admin_client()
    client.table("departments").delete().eq("hospital_id", hospital_id).execute()
    rows = [
        {
            "hospital_id": hospital_id,
            "department_name": d["standardized"],
            "raw_input": d.get("raw") or d["standardized"],
        }
        for d in dept_rows
        if d.get("standardized")
    ]
    if rows:
        client.table("departments").insert(rows).execute()


def replace_medical_staff(hospital_id: str, staff_rows: list[dict]):
    """기존 의료진을 모두 삭제하고 새 목록으로 교체합니다."""
    client = get_admin_client()
    client.table("medical_staff").delete().eq("hospital_id", hospital_id).execute()
    rows = []
    for idx, s in enumerate(staff_rows):
        if not s.get("staff_name"):
            continue
        rows.append({
            "hospital_id": hospital_id,
            "staff_name": s["staff_name"],
            "position": s.get("position"),
            "department": s.get("department"),
            "specialty_detail": s.get("specialty_detail"),
            "display_order": idx,
        })
    if rows:
        client.table("medical_staff").insert(rows).execute()


def replace_business_hours(hospital_id: str, hour_rows: list[dict]):
    """기존 진료시간을 모두 삭제하고 새 목록으로 교체합니다."""
    client = get_admin_client()
    client.table("business_hours").delete().eq("hospital_id", hospital_id).execute()
    rows = []
    for h in hour_rows:
        if not h.get("day_of_week"):
            continue
        is_closed = bool(h.get("is_closed"))
        rows.append({
            "hospital_id": hospital_id,
            "day_of_week": h["day_of_week"],
            "is_closed": is_closed,
            "open_time": None if is_closed else _time_to_str(h.get("open_time")),
            "close_time": None if is_closed else _time_to_str(h.get("close_time")),
            "lunch_start": _time_to_str(h.get("lunch_start")),
            "lunch_end": _time_to_str(h.get("lunch_end")),
            "note": h.get("note") or None,
        })
    if rows:
        client.table("business_hours").insert(rows).execute()


def _time_to_str(value):
    if value is None or value == "":
        return None
    return str(value)


def upload_hospital_photo(file_bytes: bytes, content_type: str) -> str:
    """가공된 이미지 바이트를 Supabase Storage에 업로드하고 공개 URL을 반환합니다.
    (병원 사진뿐 아니라 광고 배너 이미지 업로드에도 동일하게 재사용합니다.)
    """
    client = get_admin_client()
    ext = "jpg" if content_type == "image/jpeg" else "png"
    path = f"{uuid.uuid4()}.{ext}"
    client.storage.from_(BUCKET_NAME).upload(path, file_bytes, {"content-type": content_type})
    return client.storage.from_(BUCKET_NAME).get_public_url(path)


# ---------------------------------------------------------------------------
# 광고 배너 - 환자 화면 상단에 자동 순환 노출
# ---------------------------------------------------------------------------

def fetch_active_banners():
    """공개(is_active=true) 배너를 노출 순서대로 조회합니다."""
    client = get_anon_client()
    response = (
        client.table("ad_banners")
        .select("*")
        .eq("is_active", True)
        .order("display_order")
        .execute()
    )
    return response.data or []


def fetch_all_banners_admin():
    """비활성 배너를 포함한 전체 배너 목록을 조회합니다 (관리자 전용)."""
    client = get_admin_client()
    response = client.table("ad_banners").select("*").order("display_order").execute()
    return response.data or []


def create_banner(data: dict) -> str:
    client = get_admin_client()
    response = client.table("ad_banners").insert(data).execute()
    return response.data[0]["id"]


def update_banner(banner_id: str, data: dict):
    client = get_admin_client()
    client.table("ad_banners").update(data).eq("id", banner_id).execute()


def delete_banner(banner_id: str):
    client = get_admin_client()
    client.table("ad_banners").delete().eq("id", banner_id).execute()
