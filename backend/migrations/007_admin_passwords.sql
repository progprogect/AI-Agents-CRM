-- Admin passwords: allow login with email + password (alternative to OTP)
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
