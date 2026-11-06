USE court_case_tracker;

-- Six court domain tables, plus auth_users and auth_sessions after login setup.
SELECT table_name FROM information_schema.tables
WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- The two judged cases should be Disposed due to the trigger.
SELECT c.case_number, c.case_status, j.judgment_date
FROM cases AS c JOIN judgments AS j ON j.case_id = c.case_id
ORDER BY c.case_id;

-- This report comes from the view, not a hardcoded date in the application.
SELECT case_number, title, filed_on, judge_name
FROM cases_pending_over_six_months ORDER BY filed_on;

-- This join shows the many to many relationship and the role on the link.
SELECT c.case_number, p.party_name, cp.party_role
FROM case_parties AS cp
JOIN cases AS c ON c.case_id = cp.case_id
JOIN parties AS p ON p.party_id = cp.party_id
ORDER BY c.case_id, cp.party_role;

-- Start at original case 101 and follow every appeal level.
WITH RECURSIVE appeal_chain AS (
  SELECT case_id, parent_case_id, case_number, title, 0 AS level
  FROM cases WHERE case_id = 101
  UNION ALL
  SELECT child.case_id, child.parent_case_id, child.case_number,
         child.title, parent.level + 1
  FROM cases AS child
  JOIN appeal_chain AS parent ON child.parent_case_id = parent.case_id
)
SELECT level, case_number, title FROM appeal_chain ORDER BY level, case_id;
