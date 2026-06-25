"""
환자(공개)용 화면에서 병원 정보를 카드 형태로 보여주는 렌더링 함수 모음.
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

DAY_ORDER = ["월", "화", "수", "목", "금", "토", "일", "공휴일"]

# 병원 사진 표시 높이(px) - 가로폭은 컬럼에 맞춰 항상 100%로 줄어들고 늘어남(반응형)
PHOTO_DISPLAY_HEIGHT = 280


def render_hospital_card(hospital: dict):
    with st.container(border=True):
        st.subheader(hospital.get("name", "이름 미등록"))

        location = " ".join(filter(None, [hospital.get("sido"), hospital.get("sigungu")]))
        if location:
            st.caption(f"📍 {location}" + (f" · {hospital['address']}" if hospital.get("address") else ""))

        # 사진은 나란히(가로) 배치하며, width:100%(% 단위)로 렌더링해서
        # 브라우저 창 크기/화면 비율이 바뀌어도 항상 컬럼 폭에 맞춰 함께 줄어들고 늘어납니다.
        # (st.image의 use_container_width는 렌더링 시점의 픽셀값으로 고정되는 경우가 있어,
        #  순수 CSS(%) 기반 <img> 태그로 대체했습니다.)
        photos = [p for p in [hospital.get("photo_url_1"), hospital.get("photo_url_2")] if p]
        if photos:
            photo_cols = st.columns(len(photos))
            for col, p in zip(photo_cols, photos):
                with col:
                    st.markdown(
                        f'<img src="{p}" style="width:100%;height:{PHOTO_DISPLAY_HEIGHT}px;'
                        f'object-fit:cover;border-radius:10px;display:block;" />',
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown("📷 *등록된 사진이 없습니다*")

        if hospital.get("main_specialty"):
            st.markdown(f"🌟 **메인 진료과목:** {hospital['main_specialty']}")
        if hospital.get("special_features"):
            st.markdown(f"✨ **특화 진료:** {hospital['special_features']}")

        depts = hospital.get("departments", [])
        if depts:
            dept_names = sorted({d["department_name"] for d in depts})
            chips = "&nbsp;".join(
                f'<span style="background-color:#EEF2FF;color:#3730A3;padding:3px 10px;'
                f'border-radius:14px;font-size:0.85em;margin-right:4px;">{name}</span>'
                for name in dept_names
            )
            st.markdown(f"**진료과:** {chips}", unsafe_allow_html=True)

        hotline = hospital.get("hotline_phone")
        if hotline:
            st.markdown(
                f'<a href="tel:{hotline}" style="display:inline-block;margin-top:8px;padding:8px 18px;'
                f'background-color:#FF4B4B;color:white;border-radius:8px;text-decoration:none;'
                f'font-weight:bold;">📞 핫라인 문의: {hotline}</a>',
                unsafe_allow_html=True,
            )
            if hospital.get("hotline_note"):
                st.caption(hospital["hotline_note"])

        staff = hospital.get("medical_staff", [])
        if staff:
            with st.expander(f"👨‍⚕️ 의료진 보기 ({len(staff)}명)"):
                for s in sorted(staff, key=lambda x: x.get("display_order") or 0):
                    line = f"**{s['staff_name']}**"
                    extra = " · ".join(filter(None, [s.get("position"), s.get("department")]))
                    if extra:
                        line += f" · {extra}"
                    st.markdown(line)
                    if s.get("specialty_detail"):
                        st.caption(s["specialty_detail"])

        hours = hospital.get("business_hours", [])
        if hours:
            with st.expander("🕒 진료시간 보기"):
                render_business_hours_table(hours)

        feature_highlights = hospital.get("feature_highlights")
        if feature_highlights:
            with st.expander("🏆 병원 특징 및 특화서비스"):
                for line in feature_highlights.split("\n"):
                    line = line.strip()
                    if line:
                        st.markdown(f"- {line}")


def render_banner_carousel(banners: list, interval_seconds: int = 5, height: int = 160):
    """
    여러 개의 광고 배너 이미지를 일정 시간마다 자동으로 전환해서 보여줍니다.
    배너가 1개면 전환 없이 고정으로 보여줍니다.

    banners: [{"image_url": str, "link_url": str|None}, ...] (display_order 순으로 정렬되어 들어온다고 가정)
    """
    if not banners:
        return

    slides_html = ""
    for i, b in enumerate(banners):
        img_tag = (
            f'<img src="{b["image_url"]}" '
            f'style="width:100%;height:100%;object-fit:cover;display:block;" />'
        )
        if b.get("link_url"):
            slide_inner = (
                f'<a href="{b["link_url"]}" target="_blank" rel="noopener noreferrer" '
                f'style="display:block;width:100%;height:100%;">{img_tag}</a>'
            )
        else:
            slide_inner = img_tag

        opacity = "1" if i == 0 else "0"
        slides_html += (
            f'<div class="banner-slide" style="position:absolute;top:0;left:0;width:100%;height:100%;'
            f'opacity:{opacity};transition:opacity 1s ease-in-out;">{slide_inner}</div>'
        )

    html = f"""
    <div style="position:relative;width:100%;height:{height}px;overflow:hidden;
                border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,0.12);">
        {slides_html}
    </div>
    <script>
        (function() {{
            const slides = document.querySelectorAll('.banner-slide');
            let idx = 0;
            if (slides.length > 1) {{
                setInterval(function() {{
                    slides[idx].style.opacity = '0';
                    idx = (idx + 1) % slides.length;
                    slides[idx].style.opacity = '1';
                }}, {interval_seconds * 1000});
            }}
        }})();
    </script>
    """
    # st.markdown은 보안상 <script>를 자동으로 제거하므로, 자동 전환(타이머) 기능을 위해
    # 실제 JS가 실행되는 components.html을 사용합니다.
    components.html(html, height=height + 10)


def render_business_hours_table(hours: list):
    hours_by_day = {h["day_of_week"]: h for h in hours}
    rows = []
    for day in DAY_ORDER:
        h = hours_by_day.get(day)
        if not h:
            continue
        if h.get("is_closed"):
            time_str = "휴진"
        else:
            open_t = (h.get("open_time") or "")[:5]
            close_t = (h.get("close_time") or "")[:5]
            time_str = f"{open_t} ~ {close_t}" if open_t or close_t else "-"
            if h.get("lunch_start") and h.get("lunch_end"):
                time_str += f" (점심 {h['lunch_start'][:5]}~{h['lunch_end'][:5]})"
        row = {"요일": day, "진료시간": time_str, "비고": h.get("note") or ""}
        rows.append(row)

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.caption("등록된 진료시간 정보가 없습니다.")
