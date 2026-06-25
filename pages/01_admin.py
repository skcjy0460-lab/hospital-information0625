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
import public_data_helper
from ai_helper import standardize_departments, extract_hospital_info_from_text
from constants import DAYS_OF_WEEK, SIDO_LIST, STAFF_POSITIONS, STANDARD_DEPARTMENTS
from excel_helper import generate_excel_template
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
tab_new, tab_excel, tab_edit, tab_list, tab_banner = st.tabs(
    ["➕ 신규 병원 등록", "📁 엑셀 일괄 등록", "✏️ 병원 수정 / 삭제", "📋 전체 등록 현황", "📢 광고 배너 관리"]
)

# --- 신규 등록 -------------------------------------------------------------
with tab_new:
    st.subheader("신규 병원 등록")

    # ----- 보조 입력 1: 공공데이터(HIRA)에서 자동으로 가져오기 -----
    with st.expander("🔎 공공데이터에서 병원정보 자동으로 가져오기 (선택)", expanded=False):
        st.caption(
            "건강보험심사평가원 공공데이터에서 병원명으로 검색해 주소/전화번호/진료과목을 "
            "자동으로 채울 수 있습니다. (HIRA_API_KEY가 secrets에 설정되어 있어야 합니다)"
        )
        hira_search_name = st.text_input("병원명으로 검색", key="hira_search_name")
        if st.button("검색", key="hira_search_btn"):
            if not hira_search_name.strip():
                st.warning("병원명을 입력해주세요.")
            else:
                try:
                    with st.spinner("공공데이터에서 검색 중입니다..."):
                        results = public_data_helper.search_hospital_basis(hira_search_name.strip())
                    st.session_state["hira_search_results"] = results
                    if not results:
                        st.info("검색 결과가 없습니다. 병원명을 다르게 입력해보세요.")
                except Exception as e:
                    st.error(f"공공데이터 조회 중 오류가 발생했습니다: {e}")

        hira_results = st.session_state.get("hira_search_results", [])
        if hira_results:
            hira_options = {
                f"{r.get('yadmNm')} - {r.get('addr')} ({r.get('telno') or '전화번호 없음'})": r
                for r in hira_results
            }
            hira_pick_label = st.selectbox(
                "검색 결과에서 선택", list(hira_options.keys()), key="hira_search_pick"
            )
            if st.button("✅ 이 정보로 자동 채우기", type="primary", key="hira_apply_btn"):
                picked = hira_options[hira_pick_label]
                sido_guess = (picked.get("sidoCdNm") or "").strip()
                matched_sido = next(
                    (s for s in SIDO_LIST if sido_guess and (sido_guess in s or s in sido_guess)),
                    None,
                )

                st.session_state["new_name"] = picked.get("yadmNm", "") or ""
                if matched_sido:
                    st.session_state["new_sido"] = matched_sido
                st.session_state["new_sigungu"] = picked.get("sgguCdNm", "") or ""
                st.session_state["new_address"] = picked.get("addr", "") or ""
                st.session_state["new_hotline"] = picked.get("telno", "") or ""

                try:
                    with st.spinner("진료과목 정보도 가져오는 중입니다..."):
                        depts = public_data_helper.fetch_hospital_departments(picked.get("ykiho", ""))
                    if depts:
                        st.session_state["new_dept_raw"] = ", ".join(depts)
                except Exception:
                    pass  # 진료과목 조회 실패해도 기본정보는 그대로 적용

                st.session_state.pop("hira_search_results", None)
                st.success("기본정보를 채웠습니다. 아래 양식에서 확인 후 저장해주세요.")
                st.rerun()

    # ----- 보조 입력 2: 텍스트 붙여넣기 -> AI 자동분류 -----
    with st.expander("📋 텍스트 붙여넣기로 AI 자동분류 (선택)", expanded=False):
        st.caption(
            "병원 홈페이지나 네이버 플레이스 페이지 내용을 복사해서 붙여넣으면, "
            "AI가 이름/주소/진료과/특징 등을 자동으로 분류해서 채워줍니다. "
            "(추출 결과는 반드시 한 번 확인해주세요)"
        )
        ai_paste_text = st.text_area(
            "병원 정보 텍스트 붙여넣기", height=150, key="ai_paste_text",
            placeholder="병원 홈페이지나 네이버 플레이스 내용을 그대로 복사해서 붙여넣어주세요.",
        )
        if st.button("🤖 AI로 자동분류", key="ai_paste_btn"):
            if not ai_paste_text.strip():
                st.warning("텍스트를 먼저 붙여넣어주세요.")
            else:
                with st.spinner("AI가 텍스트를 분석하는 중입니다..."):
                    extracted = extract_hospital_info_from_text(ai_paste_text)

                if extracted:
                    if extracted.get("name"):
                        st.session_state["new_name"] = extracted["name"]
                    if extracted.get("sido") in SIDO_LIST:
                        st.session_state["new_sido"] = extracted["sido"]
                    if extracted.get("sigungu"):
                        st.session_state["new_sigungu"] = extracted["sigungu"]
                    if extracted.get("address"):
                        st.session_state["new_address"] = extracted["address"]
                    if extracted.get("main_specialty"):
                        st.session_state["new_main_spec"] = extracted["main_specialty"]
                    if extracted.get("special_features"):
                        st.session_state["new_special"] = extracted["special_features"]
                    if extracted.get("hotline_phone"):
                        st.session_state["new_hotline"] = extracted["hotline_phone"]
                    if extracted.get("hotline_note"):
                        st.session_state["new_hotline_note"] = extracted["hotline_note"]
                    depts = extracted.get("departments") or []
                    if depts:
                        st.session_state["new_dept_raw"] = ", ".join(depts)
                    features = extracted.get("feature_highlights") or []
                    if features:
                        st.session_state["new_feature_highlights"] = "\n".join(features)

                    st.success("AI 추출 결과를 채웠습니다. 아래 양식에서 꼭 확인 후 저장해주세요.")
                    st.rerun()

    st.divider()
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

# --- 엑셀 일괄 등록 ----------------------------------------------------------
with tab_excel:
    st.subheader("엑셀 일괄 등록")
    st.caption(
        "여러 병원의 기본정보(이름/지역/진료과/핫라인 등)를 엑셀로 한 번에 등록합니다. "
        "**의료진 명단 / 진료시간 / 사진은 일괄 등록 후 '병원 수정 / 삭제' 탭에서 "
        "병원별로 추가해주세요.** (한 번에 처리하기 까다로운 항목이라 분리했습니다)"
    )

    st.download_button(
        "📥 엑셀 양식 다운로드",
        data=generate_excel_template(),
        file_name="병원_일괄등록_양식.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="excel_template_download",
    )

    apply_ai_standardize = st.checkbox(
        "진료과목에 AI 표준화 자동 적용 (권장)", value=True, key="excel_ai_std",
        help="끄면 엑셀에 입력한 진료과목 텍스트를 그대로(쉼표 단위로만 분리해서) 저장합니다.",
    )

    excel_file = st.file_uploader("작성한 엑셀 파일 업로드 (.xlsx)", type=["xlsx"], key="excel_upload")

    if excel_file is not None:
        try:
            preview_df = pd.read_excel(excel_file)
        except Exception as e:
            st.error(f"엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")
            preview_df = None

        if preview_df is not None:
            st.markdown(f"**{len(preview_df)}개 행을 발견했습니다. 미리보기:**")
            st.dataframe(preview_df, use_container_width=True, hide_index=True)

            if st.button("✅ 일괄 등록 시작", type="primary", key="excel_submit"):
                required_cols = ["병원명", "시도", "메인진료과목", "핫라인전화"]
                missing_cols = [c for c in required_cols if c not in preview_df.columns]

                if missing_cols:
                    st.error(
                        f"필수 열이 없습니다: {', '.join(missing_cols)} "
                        "— 다운로드한 양식의 열 이름을 그대로 사용해주세요."
                    )
                else:
                    progress = st.progress(0)
                    status = st.empty()
                    success_count = 0
                    error_rows = []
                    total = len(preview_df)

                    for i, row in preview_df.iterrows():
                        try:
                            name = str(row.get("병원명") or "").strip()
                            sido = str(row.get("시도") or "").strip()
                            hotline = str(row.get("핫라인전화") or "").strip()
                            main_spec = str(row.get("메인진료과목") or "").strip()

                            if not name or not sido or not hotline or not main_spec:
                                error_rows.append((i + 2, "필수값 누락 (병원명/시도/메인진료과목/핫라인전화)"))
                                continue
                            if sido not in SIDO_LIST:
                                error_rows.append((i + 2, f"'시도' 값이 올바르지 않습니다: {sido}"))
                                continue

                            hospital_data = {
                                "name": name,
                                "sido": sido,
                                "sigungu": str(row.get("시군구") or "").strip(),
                                "address": str(row.get("주소") or "").strip(),
                                "main_specialty": main_spec,
                                "special_features": str(row.get("특정과_특화진료") or "").strip(),
                                "hotline_phone": hotline,
                                "hotline_note": str(row.get("핫라인안내문구") or "").strip(),
                                "feature_highlights": str(row.get("병원특징(세미콜론구분)") or "")
                                    .replace(";", "\n").strip(),
                            }
                            hospital_id = db.create_hospital(hospital_data)

                            dept_raw = str(row.get("진료과목(쉼표구분)") or "").strip()
                            if dept_raw:
                                if apply_ai_standardize:
                                    dept_result = standardize_departments(dept_raw)
                                else:
                                    dept_result = [
                                        {"raw": d.strip(), "standardized": d.strip(), "is_custom": True}
                                        for d in dept_raw.split(",") if d.strip()
                                    ]
                                db.replace_departments(hospital_id, dept_result)

                            success_count += 1
                        except Exception as row_err:
                            error_rows.append((i + 2, str(row_err)))

                        progress.progress((i + 1) / total)
                        status.text(f"{i + 1}/{total} 처리 중...")

                    status.empty()
                    progress.empty()
                    st.success(f"✅ {success_count}개 병원이 등록되었습니다.")
                    if error_rows:
                        st.warning(f"⚠️ {len(error_rows)}개 행에서 문제가 발생했습니다 (엑셀 행 번호 기준):")
                        for row_num, err in error_rows:
                            st.caption(f"- {row_num}행: {err}")

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
