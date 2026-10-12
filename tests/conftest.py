import os
import pytest

# Ensure required environment variables for test execution
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-key-at-least-32-chars-long-for-pytest")
os.environ.setdefault("OTP_PEPPER", "test-otp-pepper-secret-key-at-least-32-chars-long")
os.environ.setdefault("SMTP_HOST", "127.0.0.1")
os.environ.setdefault("SMTP_PORT", "1025")
os.environ.setdefault("SMTP_FROM", "test-auth@safestrata.local")
os.environ.setdefault("SMTP_STARTTLS", "false")
os.environ.setdefault("SMTP_SSL", "false")
