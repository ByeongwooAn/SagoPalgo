-- New live publications only. Never synthesize availability for existing events.
CREATE TABLE IF NOT EXISTS market_stream_availability (
  event_id CHAR(64) NOT NULL PRIMARY KEY,
  content_hash CHAR(64) NOT NULL,
  clock_domain CHAR(36) NOT NULL,
  commit_observed_at DATETIME(6) NOT NULL,
  input_published_at DATETIME(6) NOT NULL,
  commit_elapsed_ns BIGINT NOT NULL,
  published_elapsed_ns BIGINT NOT NULL,
  clock_quality VARCHAR(24) NOT NULL,
  CONSTRAINT fk_market_availability_event FOREIGN KEY(event_id) REFERENCES market_stream_events(event_id),
  CONSTRAINT chk_market_availability_time CHECK(input_published_at>=commit_observed_at AND commit_elapsed_ns>=0 AND published_elapsed_ns>=commit_elapsed_ns),
  CONSTRAINT chk_market_availability_quality CHECK(clock_quality IN ('MONOTONIC_STABLE','CLOCK_STEP_DETECTED')),
  INDEX idx_market_availability_domain(clock_domain,input_published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
