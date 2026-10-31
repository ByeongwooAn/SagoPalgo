-- 실주문/기존 PAPER 원장과 별도인 주문 시뮬레이션 저장소. 실주문 설정을 변경하지 않습니다.
CREATE TABLE IF NOT EXISTS order_simulation_sessions (
  session_id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  state_json JSON NOT NULL,
  revision BIGINT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  KEY idx_order_simulation_user (user_id, created_at),
  CONSTRAINT fk_order_simulation_user FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB COMMENT='실계좌 전송 없는 가상 주문 시나리오와 가상 계좌';
