"""Self-service admin 2FA reset -- for when the authenticator app is lost.
Requires the current admin password to authenticate the request, so this
can't be used by anyone who only knows the admin's email.

Usage:
    python -m scripts.reset_admin_totp --email founder@haihui.ro
"""

import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.core.security import verify_secret
from app.core.totp import generate_totp_secret, totp_provisioning_uri, verify_totp
from app.database import AsyncSessionLocal
from app.models.user import User


async def main(email: str) -> None:
    password = getpass.getpass("Current admin password: ")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email, User.is_admin.is_(True)))
        admin = result.scalar_one_or_none()
        if admin is None or not admin.admin_password_hash:
            raise SystemExit(f"No admin account for {email}")
        if not verify_secret(password, admin.admin_password_hash):
            raise SystemExit("Wrong password")

        totp_secret = generate_totp_secret()
        print(
            "\nAdd this to your authenticator app now "
            "(Google Authenticator, Authy, 1Password, etc.):"
        )
        print(f"  Manual entry key (time-based/TOTP): {totp_secret}")
        print(f"  Account name: {email}")
        print("  (or, if your app can import a link/QR from a URI:)")
        print(f"  {totp_provisioning_uri(totp_secret, email)}")

        code = input("\nEnter the 6-digit code from the app to confirm: ").strip()
        if not verify_totp(totp_secret, code):
            raise SystemExit("Code did not verify -- run the script again.")

        admin.admin_totp_secret = totp_secret
        admin.admin_failed_totp_attempts = 0
        admin.admin_totp_locked_until = None
        await db.commit()

    print(f"\n2FA reset for {email}. Log in again -- it'll ask for the new code.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.email))
