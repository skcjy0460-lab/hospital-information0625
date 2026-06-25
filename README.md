# 🏥 지역 병원 정보 안내 서비스

환자가 인터넷 검색으로는 찾기 어려운 **병원 의료진 구성 / 진료과 / 진료시간 / 메인 진료과목 /
핫라인 문의처**를 한눈에 볼 수 있게 해주는 Streamlit 기반 웹앱입니다.

- 환자용 화면(`app.py`): 지역/진료과/병원명으로 필터링해서 카드 형태로 조회 (누구나 접근 가능)
- 관리자용 화면(`pages/01_admin.py`): 비밀번호로 보호된 등록/수정/삭제 화면
- 데이터 저장: Supabase (PostgreSQL + Storage)
- AI 보조 기능: 관리자가 입력한 진료과 원문 텍스트를 Gemini API로 표준 진료과명에 자동 매핑

---

## 1. 폴더 구조

```
hospital_directory_app/
├── app.py                          # 환자용 메인 페이지
├── pages/
│   └── 01_admin.py        # 관리자 등록/수정/삭제 페이지
├── db.py                           # Supabase 데이터 액세스 레이어
├── ai_helper.py                    # Gemini 기반 진료과 표준화
├── image_utils.py                  # 업로드 사진 리사이즈/압축
├── constants.py                    # 표준 진료과/시도 목록 등 상수
├── ui_components.py                # 환자용 병원 카드 렌더링
├── supabase_schema.sql             # Supabase 테이블/RLS 생성 SQL
├── requirements.txt
├── .gitignore
└── .streamlit/
    └── secrets.toml.example        # secrets.toml 작성용 예시 (실제 키는 X)
```

---

## 2. Supabase 설정

1. [supabase.com](https://supabase.com)에서 새 프로젝트를 생성합니다.
2. **SQL Editor**를 열고 `supabase_schema.sql` 내용 전체를 붙여넣어 실행합니다.
   → `hospitals`, `departments`, `medical_staff`, `business_hours` 테이블과
     공개 조회용 RLS 정책이 한 번에 생성됩니다.
3. **Storage** 메뉴에서 `hospital-photos` 라는 이름의 **버킷을 생성**하고,
   "Public bucket"으로 설정합니다. (환자 화면에서 사진 URL을 바로 보여주기 위함)
4. **Project Settings > API** 메뉴에서 아래 3개 값을 확인합니다.
   - `Project URL` → `SUPABASE_URL`
   - `anon public` 키 → `SUPABASE_ANON_KEY`
   - `service_role` 키 → `SUPABASE_SERVICE_ROLE_KEY`
     ⚠️ **service_role 키는 RLS를 완전히 우회하는 만능 키입니다. 절대 외부에 노출하지 마세요.**
     이 앱에서는 관리자 페이지(서버 사이드)에서만 사용되므로 안전합니다.

---

## 3. Gemini API 키 발급

1. [Google AI Studio](https://aistudio.google.com/)에 접속해 API 키를 발급받습니다. (무료 티어 제공)
2. 발급받은 키를 `GEMINI_API_KEY`에 입력합니다.
3. 코드 내 `ai_helper.py`의 `GEMINI_MODEL_NAME` 값(`gemini-2.5-flash`)은
   추후 더 적합한/최신 모델이 나오면 그 값만 바꿔주면 됩니다.

---

## 3-1. (선택) 공공데이터 병원정보 자동 검색 — HIRA API 키 발급

관리자 화면의 "🔎 공공데이터에서 병원정보 자동으로 가져오기" 기능을 쓰려면:

1. [data.go.kr](https://www.data.go.kr/data/15001698/openapi.do)에서
   "건강보험심사평가원_병원정보서비스" 활용신청 (무료, 개발계정은 보통 즉시 자동승인)
2. 마이페이지 > 개발계정 상세보기에서 **"Decoding"(디코딩) 키**를 복사
   (⚠️ "Encoding" 키를 넣으면 이중 인코딩되어 인증 오류가 날 수 있습니다)
3. `HIRA_API_KEY`에 입력

이 키를 설정하지 않아도 나머지 기능(직접 입력, 엑셀 일괄 등록, AI 텍스트 자동분류)은
정상 동작합니다. 이 기능만 선택적으로 못 쓰게 됩니다.

---

## 4. Secrets 설정

`.streamlit/secrets.toml.example` 파일을 복사해서 `.streamlit/secrets.toml`로 저장한 뒤,
앞에서 발급받은 값들을 채워넣으세요.

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

`.streamlit/secrets.toml`은 `.gitignore`에 포함되어 있어 GitHub에 올라가지 않습니다.
**절대 직접 커밋하지 마세요.**

---

## 5. 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속 → 환자용 화면이 보입니다.
좌측 사이드바 상단 페이지 메뉴에서 "Admin"을 클릭하면 관리자 화면으로 이동합니다.

---

## 6. Streamlit Cloud 배포

1. 이 폴더를 GitHub 저장소에 푸시합니다 (secrets.toml은 제외됨).
2. [share.streamlit.io](https://share.streamlit.io)에서 New app → 해당 저장소 선택,
   Main file path는 `app.py`로 지정합니다.
3. 앱 설정(Settings) > **Secrets** 메뉴에 `secrets.toml.example`과 동일한 형식으로
   실제 키 값을 입력합니다.
4. Deploy 후, 동일한 URL에서 환자용/관리자용 화면을 모두 사용할 수 있습니다.

---

## 6-1. 병원을 많이(50곳 이상) 등록해야 할 때

"신규 병원 등록" 탭 안에 타이핑을 줄여주는 보조 기능 2가지가 있습니다 (둘 다 선택사항이며, 결과는 항상 직접 확인 후 저장해야 합니다):

- **🔎 공공데이터에서 자동으로 가져오기**: 병원명 검색 → 건강보험심사평가원 공공데이터에서
  주소/전화번호/진료과목을 자동으로 채워줍니다. (HIRA_API_KEY 필요, 3-1번 항목 참고)
- **📋 텍스트 붙여넣기로 AI 자동분류**: 병원 홈페이지/네이버 플레이스 내용을 복사해서
  붙여넣으면 Gemini가 이름/주소/진료과/특징 등을 자동으로 분류해서 채워줍니다.

여러 병원을 한 번에 등록하려면 **"📁 엑셀 일괄 등록" 탭**을 사용하세요:

1. "엑셀 양식 다운로드"로 빈 양식을 받습니다.
2. 병원명/시도/주소/진료과목/핫라인 등을 행 단위로 채웁니다 (시도는 양식의 표준 명칭 그대로).
3. 업로드하면 기본정보 + 진료과가 한 번에 등록됩니다.
4. **의료진 명단 / 진료시간 / 사진**은 일괄 처리가 까다로운 항목이라 제외되어 있습니다.
   일괄 등록 후 "병원 수정 / 삭제" 탭에서 병원별로 추가해주세요.

## 7. 운영 시 참고사항

- **관리자 비밀번호 관리**: 운영 중인 컨설턴트/병원 담당자가 여러 명이라면,
  추후 비밀번호 1개 대신 사용자별 계정 시스템(예: Supabase Auth)으로 확장하는 것을
  권장합니다. 현재는 단일 비밀번호 방식의 간단한 보호만 적용되어 있습니다.
- **AI 표준화 비용**: Gemini API 무료 티어 한도 내에서는 비용이 발생하지 않지만,
  요청량이 많아지면 한도를 확인하세요.
- **사진 용량**: 업로드 시 자동으로 가로 1280px 이하로 리사이즈 + JPEG 압축되므로
  Storage 용량 부담이 크지 않습니다.
- **데이터 영속성**: SQLite 등 로컬 파일 기반 DB를 쓰지 않고 Supabase를 사용하므로,
  Streamlit Cloud 앱이 재시작/재배포되어도 데이터가 유지됩니다.

---

## 8. 향후 확장 아이디어

- 병원 상세 페이지(개별 URL)로 분리해서 카카오톡 등으로 공유하기
- 카카오맵/네이버지도 연동으로 위치 시각화
- 환자 즐겨찾기, 리뷰/평점 기능
- 의료진 사진 등록
- 병원종류(종합병원/병원/의원 등) 필드 추가 및 필터
- 관리자 계정별 권한 분리 (Supabase Auth 연동)
