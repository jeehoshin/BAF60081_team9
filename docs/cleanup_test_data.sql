-- ============================================================================
-- 같이 갈래? 발표 전 테스트/시드 더미 데이터 정리 SQL (Supabase SQL Editor 실행용)
-- ============================================================================
-- 보존 대상:
--   1) 공공 API로 수집된 실제 공연·축제·전시 (source IN ('KOPIS', '한국관광공사', '한국문화정보원'))
--   2) 실제 시연용 러닝 활동 (갑천 저녁 러닝, 오리연못 산책 런, 여의도공원 러닝 등)
-- 삭제 대상:
--   1) 초기 가짜 시드 공연/축제/전시 (activity_id IN (2, 3, 4): 넙죽이 팬아트 전시, 캠퍼스 번개 버스킹, 대전 재즈 나잇)
--   2) 사용자가 임의로 올린 가짜 축제/공연/전시 (activity_id = 160 '여의도 불꽃축제' 등 source='user' 이면서 러닝이 아닌 항목)
--   3) 테스트용 모임 (meetup_id IN (6, 8, 10) 또는 이름에 '테스트'가 들어간 모임)
--   4) 테스트용 계정 및 중복 생성된 계정 ('테스트2', '테스트261017', 모임/메시지가 없는 중복 '찬휘' 계정)
-- ============================================================================

BEGIN;

-- 1. 삭제할 가짜 활동(2, 3, 4, 160 및 source='API' 또는 사용자 등록 비-러닝)에 연결된 하위 데이터 정리
DELETE FROM messages
WHERE meetup_id IN (
    SELECT meetup_id FROM meetups
    WHERE activity_id IN (
        SELECT activity_id FROM activities
        WHERE activity_id IN (2, 3, 4, 160)
           OR source = 'API'
           OR (source = 'user' AND activity_type <> '러닝')
    )
);

DELETE FROM participants
WHERE meetup_id IN (
    SELECT meetup_id FROM meetups
    WHERE activity_id IN (
        SELECT activity_id FROM activities
        WHERE activity_id IN (2, 3, 4, 160)
           OR source = 'API'
           OR (source = 'user' AND activity_type <> '러닝')
    )
);

DELETE FROM meetups
WHERE activity_id IN (
    SELECT activity_id FROM activities
    WHERE activity_id IN (2, 3, 4, 160)
       OR source = 'API'
       OR (source = 'user' AND activity_type <> '러닝')
);

DELETE FROM likes
WHERE activity_id IN (
    SELECT activity_id FROM activities
    WHERE activity_id IN (2, 3, 4, 160)
       OR source = 'API'
       OR (source = 'user' AND activity_type <> '러닝')
);

DELETE FROM activities
WHERE activity_id IN (2, 3, 4, 160)
   OR source = 'API'
   OR (source = 'user' AND activity_type <> '러닝');

-- 2. 테스트용 모임(meetup_id IN (6, 8, 10) 또는 이름에 '테스트' 포함) 정리
DELETE FROM messages
WHERE meetup_id IN (
    SELECT meetup_id FROM meetups
    WHERE meetup_id IN (6, 8, 10) OR name LIKE '%테스트%'
);

DELETE FROM participants
WHERE meetup_id IN (
    SELECT meetup_id FROM meetups
    WHERE meetup_id IN (6, 8, 10) OR name LIKE '%테스트%'
);

DELETE FROM meetups
WHERE meetup_id IN (6, 8, 10) OR name LIKE '%테스트%';

-- 3. 테스트용 이용자('테스트%' 닉네임) 및 모임이 없는 중복 '찬휘' 계정(7, 8, 9, 10, 11) 정리
DELETE FROM messages
WHERE user_id IN (
    SELECT user_id FROM users
    WHERE nickname LIKE '%테스트%' OR user_id IN (7, 8, 9, 10, 11, 14, 15, 16)
);

DELETE FROM participants
WHERE user_id IN (
    SELECT user_id FROM users
    WHERE nickname LIKE '%테스트%' OR user_id IN (7, 8, 9, 10, 11, 14, 15, 16)
);

DELETE FROM likes
WHERE user_id IN (
    SELECT user_id FROM users
    WHERE nickname LIKE '%테스트%' OR user_id IN (7, 8, 9, 10, 11, 14, 15, 16)
);

DELETE FROM users
WHERE (nickname LIKE '%테스트%' OR user_id IN (7, 8, 9, 10, 11, 14, 15, 16))
  AND user_id NOT IN (SELECT host_id FROM meetups);

-- 4. 기존 시드 이용자 중 구버전 연령대('10대', '40대+')나 성별('기타')이 있다면 팀 공통 값으로 정리
UPDATE users SET age_group = '20대' WHERE age_group = '10대';
UPDATE users SET age_group = '40대' WHERE age_group = '40대+';
UPDATE users SET gender = NULL WHERE gender = '기타';

COMMIT;
