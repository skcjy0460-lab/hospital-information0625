-- =====================================================================
-- 지역 병원 정보 안내 서비스 - Supabase 스키마
-- Supabase 대시보드 > SQL Editor 에서 전체를 그대로 실행하세요.
-- =====================================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------
-- 1. 병원 기본정보
-- ---------------------------------------------------------------------
create table if not exists hospitals (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    sido text not null,
    sigungu text,
    address text,
    photo_url_1 text,
    photo_url_2 text,
    main_specialty text,
    special_features text,
    feature_highlights text,
    hotline_phone text not null,
    hotline_note text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 2. 진료과 (병원 1 : 진료과 N)
-- ---------------------------------------------------------------------
create table if not exists departments (
    id uuid primary key default gen_random_uuid(),
    hospital_id uuid not null references hospitals(id) on delete cascade,
    department_name text not null,
    raw_input text,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 3. 의료진 (병원 1 : 의료진 N)
-- ---------------------------------------------------------------------
create table if not exists medical_staff (
    id uuid primary key default gen_random_uuid(),
    hospital_id uuid not null references hospitals(id) on delete cascade,
    staff_name text not null,
    position text,
    department text,
    specialty_detail text,
    display_order int not null default 0,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 4. 진료시간 (병원 1 : 요일 N)
-- ---------------------------------------------------------------------
create table if not exists business_hours (
    id uuid primary key default gen_random_uuid(),
    hospital_id uuid not null references hospitals(id) on delete cascade,
    day_of_week text not null,
    open_time time,
    close_time time,
    lunch_start time,
    lunch_end time,
    is_closed boolean not null default false,
    note text
);

-- updated_at 자동 갱신 트리거
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_hospitals_updated_at on hospitals;
create trigger trg_hospitals_updated_at
before update on hospitals
for each row execute function set_updated_at();

-- =====================================================================
-- RLS (Row Level Security)
-- - 공개 조회(anon key)는 is_active = true 인 병원만 SELECT 가능
-- - INSERT / UPDATE / DELETE 정책은 별도로 만들지 않습니다.
--   관리자 화면은 SERVICE ROLE KEY를 사용하므로 RLS를 우회하여
--   비공개 병원 포함 전체 데이터에 접근/수정할 수 있습니다.
-- =====================================================================
alter table hospitals enable row level security;
alter table departments enable row level security;
alter table medical_staff enable row level security;
alter table business_hours enable row level security;

create policy "public_select_active_hospitals"
on hospitals for select
using (is_active = true);

create policy "public_select_departments"
on departments for select
using (
  exists (select 1 from hospitals h where h.id = departments.hospital_id and h.is_active = true)
);

create policy "public_select_staff"
on medical_staff for select
using (
  exists (select 1 from hospitals h where h.id = medical_staff.hospital_id and h.is_active = true)
);

create policy "public_select_hours"
on business_hours for select
using (
  exists (select 1 from hospitals h where h.id = business_hours.hospital_id and h.is_active = true)
);

-- ---------------------------------------------------------------------
-- 5. 광고 배너 (환자 화면 상단 자동 순환 노출)
-- ---------------------------------------------------------------------
create table if not exists ad_banners (
    id uuid primary key default gen_random_uuid(),
    image_url text not null,
    link_url text,
    display_order int not null default 0,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

alter table ad_banners enable row level security;

create policy "public_select_active_banners"
on ad_banners for select
using (is_active = true);
