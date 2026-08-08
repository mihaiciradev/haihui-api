"""One-off CLI to provision an admin account. Admins have no signup path (§3.3).

Usage:
    python -m scripts.create_admin --email founder@haihui.ro
"""

import argparse
import asyncio
import getpass
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.security import hash_secret
from app.core.totp import generate_totp_secret, totp_provisioning_uri, verify_totp
from app.database import AsyncSessionLocal
from app.models.user import User


async def main(email: str) -> None:
    password = getpass.getpass("Admin password (min 8 chars): ")
    if len(password) < 8:
        raise SystemExit("Password too short")

    totp_secret = generate_totp_secret()
    print("Add this to an authenticator app now (Google Authenticator, Authy, 1Password, etc.):")
    print(f"  Manual entry key (time-based/TOTP): {totp_secret}")
    print(f"  Account name: {email}")
    print("  (or, if your app can import a link/QR from a URI:)")
    print(f"  {totp_provisioning_uri(totp_secret, email)}")

    code = input("Enter the 6-digit code from the app to confirm enrollment: ").strip()
    if not verify_totp(totp_secret, code):
        raise SystemExit("Code did not verify — run the script again.")

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            raise SystemExit(f"User {email} already exists")

        admin = User(
            email=email,
            is_admin=True,
            admin_password_hash=hash_secret(password),
            admin_totp_secret=totp_secret,
            admin_totp_confirmed_at=datetime.now(UTC),
        )
        db.add(admin)
        await db.commit()

    print(f"Admin created and 2FA-enrolled: {email}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.email))
