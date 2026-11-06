CREATE DATABASE IF NOT EXISTS court_case_tracker
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE court_case_tracker;

CREATE TABLE IF NOT EXISTS judges (
  judge_id INT AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(120) NOT NULL,
  designation VARCHAR(100) NOT NULL,
  court_name VARCHAR(120) NOT NULL
);

CREATE TABLE IF NOT EXISTS parties (
  party_id INT AUTO_INCREMENT PRIMARY KEY,
  party_name VARCHAR(150) NOT NULL,
  party_type VARCHAR(20) NOT NULL,
  CONSTRAINT chk_party_type CHECK (party_type IN ('Person', 'Organization'))
);

CREATE TABLE IF NOT EXISTS cases (
  case_id INT AUTO_INCREMENT PRIMARY KEY,
  case_number VARCHAR(40) NOT NULL UNIQUE,
  title VARCHAR(200) NOT NULL,
  court_name VARCHAR(120) NOT NULL,
  filed_on DATE NOT NULL,
  case_status VARCHAR(16) NOT NULL DEFAULT 'Pending',
  assigned_judge_id INT NOT NULL,
  parent_case_id INT NULL,
  CONSTRAINT fk_case_judge FOREIGN KEY (assigned_judge_id)
    REFERENCES judges(judge_id) ON DELETE RESTRICT,
  CONSTRAINT fk_case_parent FOREIGN KEY (parent_case_id)
    REFERENCES cases(case_id) ON DELETE RESTRICT,
  CONSTRAINT chk_case_status CHECK (case_status IN ('Pending', 'Disposed')),
  INDEX idx_cases_status_date (case_status, filed_on),
  INDEX idx_cases_parent (parent_case_id)
);

CREATE TABLE IF NOT EXISTS case_parties (
  case_id INT NOT NULL,
  party_id INT NOT NULL,
  party_role VARCHAR(30) NOT NULL,
  PRIMARY KEY (case_id, party_id),
  CONSTRAINT fk_case_party_case FOREIGN KEY (case_id)
    REFERENCES cases(case_id) ON DELETE RESTRICT,
  CONSTRAINT fk_case_party_party FOREIGN KEY (party_id)
    REFERENCES parties(party_id) ON DELETE RESTRICT,
  CONSTRAINT chk_party_role CHECK (
    party_role IN ('Petitioner', 'Respondent', 'Appellant')
  )
);

CREATE TABLE IF NOT EXISTS hearings (
  hearing_id INT AUTO_INCREMENT PRIMARY KEY,
  case_id INT NOT NULL,
  judge_id INT NOT NULL,
  hearing_date DATE NOT NULL,
  purpose VARCHAR(200) NOT NULL,
  hearing_status VARCHAR(16) NOT NULL DEFAULT 'Scheduled',
  CONSTRAINT fk_hearing_case FOREIGN KEY (case_id)
    REFERENCES cases(case_id) ON DELETE RESTRICT,
  CONSTRAINT fk_hearing_judge FOREIGN KEY (judge_id)
    REFERENCES judges(judge_id) ON DELETE RESTRICT,
  CONSTRAINT chk_hearing_status CHECK (
    hearing_status IN ('Scheduled', 'Held', 'Adjourned', 'Cancelled')
  ),
  INDEX idx_hearings_case_date (case_id, hearing_date)
);

CREATE TABLE IF NOT EXISTS judgments (
  judgment_id INT AUTO_INCREMENT PRIMARY KEY,
  case_id INT NOT NULL UNIQUE,
  judgment_date DATE NOT NULL,
  outcome VARCHAR(100) NOT NULL,
  summary TEXT NOT NULL,
  document_url VARCHAR(500) NULL,
  CONSTRAINT fk_judgment_case FOREIGN KEY (case_id)
    REFERENCES cases(case_id) ON DELETE RESTRICT
);

CREATE OR REPLACE VIEW cases_pending_over_six_months AS
SELECT c.case_id, c.case_number, c.title, c.court_name, c.filed_on,
       c.case_status, j.full_name AS judge_name
FROM cases AS c
JOIN judges AS j ON j.judge_id = c.assigned_judge_id
WHERE c.case_status = 'Pending'
  AND c.filed_on < CURRENT_DATE - INTERVAL 6 MONTH;

DROP TRIGGER IF EXISTS trg_judgment_disposes_case;
CREATE TRIGGER trg_judgment_disposes_case
AFTER INSERT ON judgments
FOR EACH ROW
  UPDATE cases SET case_status = 'Disposed' WHERE case_id = NEW.case_id;

-- MySQL CHECK constraints cannot reference an AUTO_INCREMENT column.
-- AFTER INSERT sees the generated case_id; BEFORE UPDATE sees the new value.
DROP TRIGGER IF EXISTS trg_case_not_own_parent_insert;
DROP TRIGGER IF EXISTS trg_case_not_own_parent_update;
DELIMITER $$
CREATE TRIGGER trg_case_not_own_parent_insert
AFTER INSERT ON cases
FOR EACH ROW
BEGIN
  IF NEW.parent_case_id = NEW.case_id THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A case cannot be its own parent.';
  END IF;
END$$

CREATE TRIGGER trg_case_not_own_parent_update
BEFORE UPDATE ON cases
FOR EACH ROW
BEGIN
  IF NEW.parent_case_id = NEW.case_id THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A case cannot be its own parent.';
  END IF;
END$$
DELIMITER ;
