-- ============================================================================
-- 같이 갈래? 발표 전 데이터 정리 (Supabase SQL Editor에서 실행)
-- ============================================================================
-- 언제: 리허설이 끝난 뒤, 시연용 이용자·모임을 새로 만들기 "전"에 한 번 (발표 전날 10/20 밤 권장)
-- 남기는 것: 공공 API로 받은 행사(KOPIS·한국관광공사·한국문화정보원), KOPIS 통계(kopis_stats), 수집 기록(collect_runs)
-- 지우는 것: 사람이 만든 데이터 전부(이용자·모임·참여·메시지·좋아요)
--            + 공공 API가 아닌 활동(예전 시드의 가짜 행사 source='API', 지난 러닝 등 source='user')
--
-- 예전 버전(id를 하나하나 적은 방식)을 바꾼 이유
--   1) 호스트인 '찬휘' 계정의 참여 행까지 지워서, 호스트가 참여자에 없는 모임(참여 0명)이 남았다
--   2) 연령대 '10대'를 '20대'로 바꿔 저장했다 (없는 사실을 만드는 것이라 하지 않는다)
--   3) id를 직접 적어 두면, 그 사이 DB가 바뀌었을 때 엉뚱한 행을 지울 수 있다
--
-- 주의
--   - TRUNCATE ... RESTART IDENTITY 는 쓰지 않는다. 번호가 1부터 다시 시작하면 휴대폰에 남은
--     예전 계정 번호(user_id)가 발표 날 새로 합류한 청중의 계정을 가리키게 된다.
--   - activities를 통째로 비우지 않는다. 비어 있으면 서버가 재시작할 때 시연용 시드(KAIST 러닝·이용자)가 다시 들어간다.
--   - 실행 뒤 팀원 휴대폰·발표 노트북 브라우저에서 '로그아웃'(또는 사이트 데이터 삭제)하고 새로 합류한다.
-- ============================================================================

-- 0) 미리 보기: 이 SELECT만 먼저 실행해서 지워질 건수를 확인한다
SELECT 'users (지움)' AS what, count(*) FROM users
UNION ALL SELECT 'meetups (지움)', count(*) FROM meetups
UNION ALL SELECT 'participants (지움)', count(*) FROM participants
UNION ALL SELECT 'messages (지움)', count(*) FROM messages
UNION ALL SELECT 'likes (지움)', count(*) FROM likes
UNION ALL SELECT 'activities: 공공 API 아님 (지움)', count(*) FROM activities
  WHERE source IS NULL OR source NOT IN ('KOPIS', '한국관광공사', '한국문화정보원')
UNION ALL SELECT 'activities: 공공 API (남김)', count(*) FROM activities
  WHERE source IN ('KOPIS', '한국관광공사', '한국문화정보원');

-- 1) 정리: BEGIN ~ COMMIT을 한 번에 실행한다 (중간에 실패하면 전부 취소된다)
BEGIN;

DELETE FROM messages;
DELETE FROM participants;
DELETE FROM likes;
DELETE FROM meetups;
DELETE FROM users;
DELETE FROM activities
WHERE source IS NULL OR source NOT IN ('KOPIS', '한국관광공사', '한국문화정보원');

COMMIT;

-- 2) 확인: 공공 API 행사만 남았는지
SELECT source, count(*) FROM activities GROUP BY source ORDER BY 2 DESC;
