"""Shared branded HTML shell for every transactional email.

Brand tokens per the platform plan (§2.3): Navy #245880, Gold #D1A568,
White; headings Libre Franklin, body Source Sans 3. Email clients don't
reliably load custom web fonts, so we declare them with close, widely
available fallbacks rather than embedding/linking fonts. Table-based layout
and inline styles throughout -- this is the one context where that's
correct, not an anti-pattern: it's what actually renders consistently
across Outlook, Gmail, and Apple Mail.
"""

# ruff: noqa: E501 -- HTML markup below, not code; wrapping tag attributes
# to fit a line-length limit doesn't improve readability here.

from datetime import UTC, datetime

from app.config import get_settings

NAVY = "#245880"
GOLD = "#D1A568"
INK = "#1a1a1a"
MUTED = "#5c5e66"
BORDER = "#e5e5e8"
PAGE_BG = "#f4f4f5"

_HEADING_FONT = "'Libre Franklin', 'Segoe UI', Arial, sans-serif"
_BODY_FONT = "'Source Sans 3', 'Segoe UI', Arial, sans-serif"

_COPY = {
    "ro": {
        "support_label": "Ai nevoie de ajutor? Scrie-ne la",
        "footer_note": "Acesta este un email automat trimis de HaiHui – Storage.",
        "rights": "Toate drepturile rezervate.",
    },
    "en": {
        "support_label": "Need help? Write to us at",
        "footer_note": "This is an automated email sent by HaiHui – Storage.",
        "rights": "All rights reserved.",
    },
}


def render_email(
    *,
    preheader: str,
    heading: str,
    body_html: str,
    locale: str = "ro",
    cta_label: str | None = None,
    cta_url: str | None = None,
) -> str:
    """body_html is trusted, pre-built HTML (short paragraphs) -- callers
    control it directly, it is never raw user input.
    """
    settings = get_settings()
    copy = _COPY.get(locale, _COPY["ro"])
    support_email = settings.email_reply_to or "haihuistorage@proton.me"
    year = datetime.now(UTC).year

    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
          <tr>
            <td align="center" style="padding: 4px 32px 28px;">
              <a href="{cta_url}" style="display:inline-block; background:{GOLD}; color:{NAVY};
                font-family:{_HEADING_FONT}; font-weight:700; font-size:15px; padding:14px 34px;
                border-radius:8px; text-decoration:none;">{cta_label}</a>
            </td>
          </tr>"""

    return f"""<!DOCTYPE html>
<html lang="{locale}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light">
<title>{heading}</title>
</head>
<body style="margin:0; padding:0; background:{PAGE_BG}; font-family:{_BODY_FONT};">
  <span style="display:none; max-height:0; max-width:0; overflow:hidden; opacity:0;">{preheader}</span>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE_BG};">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
          style="max-width:560px; background:#ffffff; border-radius:12px; overflow:hidden; border:1px solid {BORDER};">
          <tr>
            <td style="background:{NAVY}; padding:20px 32px;">
              <span style="font-family:{_HEADING_FONT}; font-size:19px; font-weight:800; color:#ffffff; letter-spacing:0.2px;">HaiHui</span>
              <span style="font-family:{_BODY_FONT}; font-size:13px; color:{GOLD}; margin-left:8px;">Storage</span>
            </td>
          </tr>
          <tr>
            <td style="padding:32px 32px 8px;">
              <h1 style="font-family:{_HEADING_FONT}; font-size:21px; color:{INK}; margin:0 0 16px; font-weight:700;">{heading}</h1>
              <div style="font-size:15px; line-height:1.65; color:{INK};">{body_html}</div>
            </td>
          </tr>
          {cta_html}
          <tr>
            <td style="padding:4px 32px 28px;">
              <div style="border-top:1px solid {BORDER}; padding-top:18px; font-size:13px; color:{MUTED}; line-height:1.6;">
                <p style="margin:0 0 6px;">{copy["support_label"]}
                  <a href="mailto:{support_email}" style="color:{NAVY}; text-decoration:underline;">{support_email}</a>
                </p>
                <p style="margin:0;">{copy["footer_note"]}</p>
              </div>
            </td>
          </tr>
          <tr>
            <td style="background:#fafafa; padding:14px 32px; text-align:center; font-size:12px; color:{MUTED};">
              &copy; {year} HaiHui – Storage. {copy["rights"]}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
