-- activities 상세 설명·관람 조건 칸 추가 (2026-11-22)
--
-- 백엔드(Render)가 시작할 때 database.ensure_schema가 같은 칸을 자동으로 추가하므로
-- 이 파일을 꼭 돌려야 하는 것은 아니다. Supabase SQL Editor에서 먼저 확인하고 싶을 때 쓴다.
-- 칸을 추가만 하고, 모두 비워 둘 수 있으며, 이미 있으면 건너뛴다 (여러 번 실행해도 안전).

alter table activities add column if not exists detail_text text;
alter table activities add column if not exists detail_source varchar(32);
alter table activities add column if not exists text_hash varchar(64);
alter table activities add column if not exists min_age_months int;
alter table activities add column if not exists runtime_min int;
alter table activities add column if not exists intro_images text;
alter table activities add column if not exists detail_checked_at timestamp;

-- 확인: 칸 7개가 보이면 성공
-- select column_name, data_type from information_schema.columns
--  where table_name = 'activities' and column_name in
--  ('detail_text','detail_source','text_hash','min_age_months','runtime_min','intro_images','detail_checked_at');
