USE court_case_tracker;

CREATE TABLE IF NOT EXISTS auth_users (
  user_id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  email VARCHAR(254) NOT NULL UNIQUE,
  display_name VARCHAR(120) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_sessions (
  token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  user_id INT NOT NULL,
  created_at DATETIME NOT NULL,
  expires_at DATETIME NOT NULL,
  CONSTRAINT fk_auth_session_user FOREIGN KEY (user_id)
    REFERENCES auth_users(user_id) ON DELETE CASCADE,
  INDEX idx_auth_sessions_expiry (expires_at)
);
