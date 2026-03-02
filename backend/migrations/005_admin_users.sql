-- Admin users table for multi-user access management
-- Super admins are defined in ALLOWED_ADMIN_EMAILS env var
-- Regular users are stored in this table and managed via the admin UI

CREATE TABLE IF NOT EXISTS admin_users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_by VARCHAR(255) NOT NULL,  -- email of the super admin who added this user
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email, is_active);
