-- 이전 추천은 모두 보유 종목 분석입니다. 새 관심 종목 분석을 별도로 구분합니다.
ALTER TABLE recommendations
  ADD COLUMN analysis_context VARCHAR(20) NOT NULL DEFAULT 'HOLDING' AFTER market;
