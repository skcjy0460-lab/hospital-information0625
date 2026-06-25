"""
관리자용 병원 정보 관리 페이지.

비밀번호 인증(st.secrets["ADMIN_PASSWORD"]) 후에만 접근 가능합니다.
- 신규 병원 등록
- 기존 병원 수정 / 비공개 처리 / 영구 삭제
- 전체 등록 현황 목록

진료과 입력은 자유 텍스트로 받은 뒤, Gemini AI로 표준 진료과명에
매핑(표준화)하고, 관리자가 결과를 검토/수정할 수 있도록 구성했습니다.
"""
from datetime import time

import pandas as pd
import streamlit as st

import db
from ai_helper import standardize_departments
from constants import DAYS_OF_WEEK, SIDO_LIST, STAFF_POSITIONS, STANDARD_DEPARTMENTS
from image_utils import process_uploaded_image

st.set_page_config(page_title="관리자 - 병원 정보 관리", page_icon="🔐", layout="wide")


# ---------------------------------------------------------------------------
# 관리자 인증
# ---------------------------------------------------------------------------
def require_admin_login() -> bool:
    if st.session_state.get("is_admin"):
        return True

    st.title("🔐 관리자 로그인")
    st.caption("병원 정보 등록/수정 권한이 있는 담당자만 접근할 수 있습니다.")
    pw = st.text_input("관리자 비밀번호", type="password", key="admin_pw_input")
    if st.button("로그인", type="primary"):
        correct_pw = st.secrets.get("ADMIN_PASSWORD", "")
        if correct_pw and pw == correct_pw:
            st.session_state["is_admin"] = True
            st.rerun()
        else:
            st.error("비밀번호가 일치하지 않습니다.")
    return False


if not require_admin_login():
    st.stop()

with st.sidebar:
    st.success("관리자로 로그인되어 있습니다.")
    if st.button("🚪 로그아웃"):
        st.session_state.pop("is_admin", None)
        st.rerun()

st.title("🏥 병원 정보 관리")

EMPTY_STAFF_TEMPLATE = pd.DataFrame(
    columns=["staff_name", "position", "department", "specialty_detail"]
)


def _default_hours_df():
    return pd.DataFrame([
        {
            "day_of_week": d,
            "is_closed": d in ("일", "공휴일"),
            "open_time": time(9, 0),
            "close_time": time(18, 0),
            "lunch_start": time(13, 0),
            "lunch_end": time(14, 0),
            "note": "",
        }
        for d in DAYS_OF_WEEK
    ])


def _to_time(value):
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    try:
        parts = str(value).split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 입력 섹션 렌더링 함수 (신규 등록 / 수정에서 공통으로 재사용)
# ---------------------------------------------------------------------------

def render_basic_info_section(key_prefix: str, existing: dict | None = None):
    existing = existing or {}
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("병원명 *", value=existing.get("name", ""), key=f"{key_prefix}_name")
        sido_index = SIDO_LIST.index(existing["sido"]) if existing.get("sido") in SIDO_LIST else 0
        sido = st.selectbox("시/도 *", SIDO_LIST, index=sido_index, key=f"{key_prefix}_sido")
        sigungu = st.text_input("시/군/구", value=existing.get("sigungu", ""), key=f"{key_prefix}_sigungu")
        address = st.text_input("상세 주소", value=existing.get("address", ""), key=f"{key_prefix}_address")
    with col2:
        main_specialty = st.text_input(
            "메인 진료과목 *",
            value=existing.get("main_specialty", ""),
            placeholder="예: 정형외과 (관절/척추 특화)",
            key=f"{key_prefix}_main_spec",
        )
        special_features = st.text_input(
            "특정과 / 특화 진료",
            value=existing.get("special_features", ""),
            placeholder="예: 척추센터, 인공관절센터, 도수치료실",
            key=f"{key_prefix}_special",
        )
        hotline_phone = st.text_input(
            "핫라인(문의) 전화번호 *",
            value=existing.get("hotline_phone", ""),
            placeholder="예: 053-000-0000",
            key=f"{key_prefix}_hotline",
        )
        hotline_note = st.text_input(
            "문의 안내 문구",
            value=existing.get("hotline_note", ""),
            placeholder="예: 평일 09:00~18:00 상담 가능",
            key=f"{key_prefix}_hotline_note",
        )

    st.markdown("**병원 사진 (최대 2장)**")
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        if existing.get("photo_url_1"):
            st.image(existing["photo_url_1"], caption="현재 사진 1", width=220)
        photo1 = st.file_uploader(
            "사진 1 업로드 (교체 시에만 새로 업로드)",
            type=["jpg", "jpeg", "png"],
            key=f"{key_prefix}_photo1",
        )
    with pcol2:
        if existing.get("photo_url_2"):
            st.image(existing["photo_url_2"], caption="현재 사진 2", width=220)
        photo2 = st.file_uploader(
            "사진 2 업로드 (교체 시에만 새로 업로드)",
            type=["jpg", "jpeg", "png"],
            key=f"{key_prefix}_photo2",
        )

    st.markdown(
        "**병원 특징 및 특화서비스** (선택) — 한 줄에 하나씩 입력하면 환자 화면에서 목록 형태로 보여집니다."
    )
    feature_highlights = st.text_area(
        "특징 / 특화서비스 내용",
        value=existing.get("feature_highlights", "") or "",
        placeholder="예:\n최신 3.0T MRI 장비 보유\n24시간 응급의료센터 운영\n전담 코디네이터 1:1 상담\n전용 주차장 100대 동시 이용 가능",
        height=120,
        key=f"{key_prefix}_feature_highlights",
    )

    return {
        "name": name.strip(),
        "sido": sido,
        "sigungu": sigungu.strip(),
        "address": address.strip(),
        "main_specialty": main_specialty.strip(),
        "special_features": special_features.strip(),
        "hotline_phone": hotline_phone.strip(),
        "hotline_note": hotline_note.strip(),
        "feature_highlights": feature_highlights.strip(),
        "photo1_file": photo1,
        "photo2_file": photo2,
    }


def render_department_section(key_prefix: str, initial_raw: str = "", initial_departments=None):
    st.markdown("**진료과 등록** — 쉼표(,)로 구분해서 입력한 뒤 AI 표준화를 적용하세요.")
    raw_text = st.text_input(
        "진료과 원본 입력",
        value=initial_raw,
        placeholder="예: 정형외과, 내과, 신경외과, 재활의학과",
        key=f"{key_prefix}_dept_raw",
    )

    suggestion_key = f"{key_prefix}_dept_suggestions"

    col1, _ = st.columns([1, 3])
    with col1:
        if st.button("🤖 AI로 표준화 적용", key=f"{key_prefix}_dept_ai_btn"):
            if not raw_text.strip():
                st.warning("진료과를 먼저 입력해주세요.")
            else:
                with st.spinner("AI가 진료과명을 표준화하는 중입니다..."):
                    result = standardize_departments(raw_text)
                st.session_state[suggestion_key] = pd.DataFrame(result)

    # 수정 화면에서 처음 진입할 때는 기존 등록 데이터를 그대로 표시
    if initial_departments and suggestion_key not in st.session_state:
        st.session_state[suggestion_key] = pd.DataFrame([
            {
                "raw": d.get("raw_input") or d["department_name"],
                "standardized": d["department_name"],
                "is_custom": d["department_name"] not in STANDARD_DEPARTMENTS,
            }
            for d in initial_departments
        ])

    if suggestion_key in st.session_state and not st.session_state[suggestion_key].empty:
        st.caption("AI 제안 결과를 확인하고, 필요하면 '표준 진료과명' 칸을 직접 수정하세요.")
        edited = st.data_editor(
            st.session_state[suggestion_key],
            column_config={
                "raw": st.column_config.TextColumn("원본 입력", disabled=True),
                "standardized": st.column_config.TextColumn("표준 진료과명 (수정가능)"),
                "is_custom": st.column_config.CheckboxColumn("표준목록 외 항목", disabled=True),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"{key_prefix}_dept_editor",
        )
        return edited.to_dict("records")

    return []


def render_staff_section(key_prefix: str, initial_staff=None):
    st.markdown("**의료진 등록**")
    if initial_staff:
        df = pd.DataFrame([
            {
                "staff_name": s["staff_name"],
                "position": s.get("position") or "",
                "department": s.get("department") or "",
                "specialty_detail": s.get("specialty_detail") or "",
            }
            for s in initial_staff
        ])
    else:
        df = EMPTY_STAFF_TEMPLATE.copy()

    edited = st.data_editor(
        df,
        column_config={
            "staff_name": st.column_config.TextColumn("이름 *"),
            "position": st.column_config.SelectboxColumn("직급", options=STAFF_POSITIONS),
            "department": st.column_config.SelectboxColumn("담당 진료과", options=STANDARD_DEPARTMENTS),
            "specialty_detail": st.column_config.TextColumn("전문분야 / 약력"),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"{key_prefix}_staff_editor",
    )
    return edited.to_dict("records")


def render_hours_section(key_prefix: str, initial_hours=None):
    st.markdown("**진료시간 등록**")
    if initial_hours:
        hours_by_day = {h["day_of_week"]: h for h in initial_hours}
        rows = []
        for d in DAYS_OF_WEEK:
            h = hours_by_day.get(d, {})
            rows.append({
                "day_of_week": d,
                "is_closed": h.get("is_closed", d in ("일", "공휴일")),
                "open_time": _to_time(h.get("open_time")) or time(9, 0),
                "close_time": _to_time(h.get("close_time")) or time(18, 0),
                "lunch_start": _to_time(h.get("lunch_start")),
                "lunch_end": _to_time(h.get("lunch_end")),
                "note": h.get("note") or "",
            })
        df = pd.DataFrame(rows)
    else:
        df = _default_hours_df()

    edited = st.data_editor(
        df,
        column_config={
            "day_of_week": st.column_config.TextColumn("요일", disabled=True),
            "is_closed": st.column_config.CheckboxColumn("휴진"),
            "open_time": st.column_config.TimeColumn("진료 시작", format="HH:mm"),
            "close_time": st.column_config.TimeColumn("진료 종료", format="HH:mm"),
            "lunch_start": st.column_config.TimeColumn("점심 시작", format="HH:mm"),
            "lunch_end": st.column_config.TimeColumn("점심 종료", format="HH:mm"),
            "note": st.column_config.TextColumn("비고 (예: 야간진료/예약전화 등)"),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key=f"{key_prefix}_hours_editor",
    )
    return edited.to_dict("records")


# ---------------------------------------------------------------------------
# 탭 구성
# ---------------------------------------------------------------------------
tab_new, tab_edit, tab_list, tab_banner = st.tabs(
    ["➕ 신규 병원 등록", "✏️ 병원 수정 / 삭제", "📋 전체 등록 현황", "📢 광고 배너 관리"]
)

# --- 신규 등록 -------------------------------------------------------------
with tab_new:
    st.subheader("신규 병원 등록")
    basic = render_basic_info_section("new")
    st.divider()
    dept_rows = render_department_section("new")
    st.divider()
    staff_rows = render_staff_section("new")
    st.divider()
    hour_rows = render_hours_section("new")
    st.divider()

    if st.button("✅ 병원 등록 완료", type="primary", key="new_submit"):
        errors = []
        if not basic["name"]:
            errors.append("병원명을 입력해주세요.")
        if not basic["main_specialty"]:
            errors.append("메인 진료과목을 입력해주세요.")
        if not basic["hotline_phone"]:
            errors.append("핫라인 전화번호를 입력해주세요.")
        if not dept_rows:
            errors.append("진료과를 1개 이상 등록해주세요. (AI 표준화 버튼을 눌러주세요)")

        if errors:
            for e in errors:
                st.error(e)
        else:
            try:
                with st.spinner("등록 중입니다..."):
                    photo_url_1 = photo_url_2 = None
                    if basic["photo1_file"] is not None:
                        img_bytes, ctype = process_uploaded_image(basic["photo1_file"])
                        photo_url_1 = db.upload_hospital_photo(img_bytes, ctype)
                    if basic["photo2_file"] is not None:
                        img_bytes, ctype = process_uploaded_image(basic["photo2_file"])
                        photo_url_2 = db.upload_hospital_photo(img_bytes, ctype)

                    hospital_data = {
                        "name": basic["name"],
                        "sido": basic["sido"],
                        "sigungu": basic["sigungu"],
                        "address": basic["address"],
                        "main_specialty": basic["main_specialty"],
                        "special_features": basic["special_features"],
                        "hotline_phone": basic["hotline_phone"],
                        "hotline_note": basic["hotline_note"],
                        "feature_highlights": basic["feature_highlights"],
                        "photo_url_1": photo_url_1,
                        "photo_url_2": photo_url_2,
                    }
                    hospital_id = db.create_hospital(hospital_data)
                    db.replace_departments(hospital_id, dept_rows)
                    db.replace_medical_staff(hospital_id, staff_rows)
                    db.replace_business_hours(hospital_id, hour_rows)

                st.success(f"'{basic['name']}' 병원이 등록되었습니다!")
                st.balloons()
            except Exception as e:
                st.error(f"등록 중 오류가 발생했습니다: {e}")

# --- 수정 / 삭제 ------------------------------------------------------------
with tab_edit:
    st.subheader("병원 수정 / 삭제")
    try:
        all_hospitals = db.fetch_all_hospitals_admin()
    except Exception as e:
        st.error("병원 목록을 불러오는 중 오류가 발생했습니다.")
        st.exception(e)
        all_hospitals = []

    if not all_hospitals:
        st.info("등록된 병원이 없습니다. '신규 병원 등록' 탭에서 먼저 등록해주세요.")
    else:
        name_options = {
            f"{h['name']} ({h['sido']} {h.get('sigungu') or ''})".strip() + (
                "" if h.get("is_active", True) else " [비공개]"
            ): h["id"]
            for h in all_hospitals
        }
        selected_label = st.selectbox("수정할 병원 선택", list(name_options.keys()), key="edit_select")
        selected_id = name_options[selected_label]
        hospital = next(h for h in all_hospitals if h["id"] == selected_id)

        basic_e = render_basic_info_section("edit", existing=hospital)
        st.divider()
        dept_rows_e = render_department_section(
            "edit",
            initial_raw=", ".join(
                d.get("raw_input") or d["department_name"] for d in hospital.get("departments", [])
            ),
            initial_departments=hospital.get("departments", []),
        )
        st.divider()
        staff_rows_e = render_staff_section("edit", initial_staff=hospital.get("medical_staff", []))
        st.divider()
        hour_rows_e = render_hours_section("edit", initial_hours=hospital.get("business_hours", []))
        st.divider()

        col_save, col_toggle, col_delete = st.columns(3)
        with col_save:
            if st.button("💾 수정 내용 저장", type="primary", key="edit_save"):
                try:
                    with st.spinner("수정 중입니다..."):
                        update_data = {
                            "name": basic_e["name"],
                            "sido": basic_e["sido"],
                            "sigungu": basic_e["sigungu"],
                            "address": basic_e["address"],
                            "main_specialty": basic_e["main_specialty"],
                            "special_features": basic_e["special_features"],
                            "hotline_phone": basic_e["hotline_phone"],
                            "hotline_note": basic_e["hotline_note"],
                            "feature_highlights": basic_e["feature_highlights"],
                        }
                        if basic_e["photo1_file"] is not None:
                            img_bytes, ctype = process_uploaded_image(basic_e["photo1_file"])
                            update_data["photo_url_1"] = db.upload_hospital_photo(img_bytes, ctype)
                        if basic_e["photo2_file"] is not None:
                            img_bytes, ctype = process_uploaded_image(basic_e["photo2_file"])
                            update_data["photo_url_2"] = db.upload_hospital_photo(img_bytes, ctype)

                        db.update_hospital(selected_id, update_data)
                        db.replace_departments(selected_id, dept_rows_e)
                        db.replace_medical_staff(selected_id, staff_rows_e)
                        db.replace_business_hours(selected_id, hour_rows_e)

                    st.success("수정이 완료되었습니다.")
                except Exception as e:
                    st.error(f"수정 중 오류가 발생했습니다: {e}")

        with col_toggle:
            is_active = hospital.get("is_active", True)
            label = "🚫 비공개 처리" if is_active else "✅ 다시 공개하기"
            if st.button(label, key="edit_toggle_active"):
                db.set_hospital_active(selected_id, not is_active)
                st.success("처리되었습니다.")
                st.rerun()

        with col_delete:
            confirm = st.checkbox("영구 삭제를 확인합니다", key="edit_delete_confirm")
            if st.button("🗑️ 영구 삭제", disabled=not confirm, key="edit_delete_btn"):
                db.delete_hospital_permanently(selected_id)
                st.success("삭제되었습니다.")
                st.rerun()

# --- 전체 목록 --------------------------------------------------------------
with tab_list:
    st.subheader("전체 등록 병원 현황")
    try:
        all_h = db.fetch_all_hospitals_admin()
    except Exception as e:
        st.error("목록을 불러오는 중 오류가 발생했습니다.")
        st.exception(e)
        all_h = []

    if not all_h:
        st.info("등록된 병원이 없습니다.")
    else:
        df = pd.DataFrame([
            {
                "병원명": h["name"],
                "지역": f"{h['sido']} {h.get('sigungu') or ''}".strip(),
                "메인 진료과목": h.get("main_specialty"),
                "진료과 수": len(h.get("departments", [])),
                "의료진 수": len(h.get("medical_staff", [])),
                "공개상태": "공개" if h.get("is_active", True) else "비공개",
            }
            for h in all_h
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 광고 배너 관리 --------------------------------------------------------
with tab_banner:
    st.subheader("광고 배너 관리")
    st.caption(
        "환자용 화면 상단에 노출되는 배너입니다. 여러 개 등록하면 설정한 시간마다 "
        "자동으로 다음 배너로 넘어갑니다. 클릭 시 이동할 링크는 선택사항입니다."
    )

    try:
        banners = db.fetch_all_banners_admin()
    except Exception as e:
        st.error("배너 목록을 불러오는 중 오류가 발생했습니다.")
        st.exception(e)
        banners = []

    st.markdown("### ➕ 새 배너 추가")
    new_banner_file = st.file_uploader(
        "배너 이미지 업로드 (가로로 넓은 이미지를 권장합니다, 예: 1200x300)",
        type=["jpg", "jpeg", "png"],
        key="banner_new_file",
    )
    new_banner_link = st.text_input(
        "클릭 시 이동할 링크 (선택)", placeholder="https://...", key="banner_new_link"
    )
    new_banner_order = st.number_input(
        "노출 순서 (작은 숫자가 먼저 보입니다)",
        min_value=0, value=len(banners), step=1, key="banner_new_order",
    )

    if st.button("배너 등록", type="primary", key="banner_new_submit"):
        if new_banner_file is None:
            st.error("배너 이미지를 업로드해주세요.")
        else:
            try:
                with st.spinner("등록 중입니다..."):
                    img_bytes, ctype = process_uploaded_image(new_banner_file)
                    image_url = db.upload_hospital_photo(img_bytes, ctype)
                    db.create_banner({
                        "image_url": image_url,
                        "link_url": new_banner_link.strip() or None,
                        "display_order": int(new_banner_order),
                        "is_active": True,
                    })
                st.success("배너가 등록되었습니다.")
                st.rerun()
            except Exception as e:
                st.error(f"등록 중 오류가 발생했습니다: {e}")

    st.divider()
    st.markdown("### 등록된 배너 목록")
    if not banners:
        st.info("등록된 배너가 없습니다.")
    else:
        for b in banners:
            with st.container(border=True):
                col_img, col_info, col_actions = st.columns([1, 2, 1])
                with col_img:
                    st.image(b["image_url"], use_container_width=True)
                with col_info:
                    st.caption(f"노출 순서: {b.get('display_order')}")
                    if b.get("link_url"):
                        st.caption(f"링크: {b['link_url']}")
                    st.caption("상태: " + ("✅ 활성" if b.get("is_active") else "🚫 비활성"))
                with col_actions:
                    toggle_label = "🚫 비활성화" if b.get("is_active") else "✅ 활성화"
                    if st.button(toggle_label, key=f"banner_toggle_{b['id']}"):
                        db.update_banner(b["id"], {"is_active": not b.get("is_active")})
                        st.rerun()
                    if st.button("🗑️ 삭제", key=f"banner_delete_{b['id']}"):
                        db.delete_banner(b["id"])
                        st.rerun()
