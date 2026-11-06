USE court_case_tracker;

-- Run once on a fresh database. Every name and case number below is fictional.
INSERT INTO judges (judge_id, full_name, designation, court_name) VALUES
  (1, 'Justice Mira Rao', 'Presiding Judge', 'District Civil Court'),
  (2, 'Justice Arvind Sen', 'Appellate Judge', 'High Court');

INSERT INTO parties (party_id, party_name, party_type) VALUES
  (1, 'Asha Nair', 'Person'),
  (2, 'Northbridge Housing Board', 'Organization'),
  (3, 'Rohan Mehta', 'Person'),
  (4, 'Cedar Works Ltd', 'Organization');

INSERT INTO cases
  (case_id, case_number, title, court_name, filed_on, assigned_judge_id, parent_case_id)
VALUES
  (101, 'DEMO/2025/001', 'Housing allotment dispute', 'District Civil Court',
   CURRENT_DATE - INTERVAL 14 MONTH, 1, NULL),
  (201, 'DEMO/2026/021', 'Housing allotment appeal', 'High Court',
   CURRENT_DATE - INTERVAL 8 MONTH, 2, 101),
  (301, 'DEMO/2026/061', 'Higher housing appeal', 'High Court',
   CURRENT_DATE - INTERVAL 2 MONTH, 2, 201),
  (102, 'DEMO/2025/014', 'Contract payment dispute', 'District Civil Court',
   CURRENT_DATE - INTERVAL 10 MONTH, 1, NULL),
  (103, 'DEMO/2026/108', 'Property boundary dispute', 'District Civil Court',
   CURRENT_DATE - INTERVAL 1 MONTH, 1, NULL);

INSERT INTO case_parties (case_id, party_id, party_role) VALUES
  (101, 1, 'Petitioner'), (101, 2, 'Respondent'),
  (201, 2, 'Appellant'), (201, 1, 'Respondent'),
  (301, 1, 'Appellant'), (301, 2, 'Respondent'),
  (102, 3, 'Petitioner'), (102, 4, 'Respondent'),
  (103, 1, 'Petitioner'), (103, 4, 'Respondent');

INSERT INTO hearings
  (case_id, judge_id, hearing_date, purpose, hearing_status) VALUES
  (101, 1, CURRENT_DATE - INTERVAL 12 MONTH, 'Initial hearing', 'Held'),
  (101, 1, CURRENT_DATE - INTERVAL 9 MONTH, 'Evidence review', 'Held'),
  (201, 2, CURRENT_DATE - INTERVAL 6 MONTH, 'Appeal admission', 'Held'),
  (301, 2, CURRENT_DATE + INTERVAL 12 DAY, 'Arguments', 'Scheduled'),
  (102, 1, CURRENT_DATE + INTERVAL 7 DAY, 'Witness statements', 'Scheduled');

-- The trigger changes cases 101 and 201 to Disposed.
INSERT INTO judgments (case_id, judgment_date, outcome, summary) VALUES
  (101, CURRENT_DATE - INTERVAL 9 MONTH, 'Petition dismissed',
   'The sample court found insufficient evidence for the requested allotment.'),
  (201, CURRENT_DATE - INTERVAL 3 MONTH, 'Appeal dismissed',
   'The sample appellate court upheld the earlier decision.');
