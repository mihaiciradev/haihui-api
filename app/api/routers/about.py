"""Standalone pitch page (§ product ask) -- a link an admin can send to a
prospective partner business to explain the platform in under a minute,
without needing a slide deck. Self-contained HTML, same brand tokens as the
transactional emails, served directly by the API since there's no separate
marketing site yet.
"""

# ruff: noqa: E501 -- HTML/SVG markup below, not code.

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["about"])

NAVY = "#245880"
GOLD = "#D1A568"
INK = "#1a1a1a"
MUTED = "#5c5e66"
BORDER = "#e5e5e8"
PAGE_BG = "#f4f4f5"

_HEADING_FONT = "'Libre Franklin', 'Segoe UI', Arial, sans-serif"
_BODY_FONT = "'Source Sans 3', 'Segoe UI', Arial, sans-serif"

_SVG_FLOW = f"""
<svg viewBox="0 0 800 230" xmlns="http://www.w3.org/2000/svg" role="img"
  aria-label="Turistul rezervă online, lasă bagajul la un partener local, apoi îl ridică oricând în programul de lucru."
  style="width:100%; height:auto; display:block;">
  <line x1="90" y1="70" x2="710" y2="70" stroke="{BORDER}" stroke-width="3"/>
  <polygon points="205,64 220,70 205,76" fill="{GOLD}"/>
  <polygon points="425,64 440,70 425,76" fill="{GOLD}"/>
  <polygon points="645,64 660,70 645,76" fill="{GOLD}"/>

  <g>
    <circle cx="90" cy="70" r="42" fill="{NAVY}"/>
    <circle cx="90" cy="56" r="10" fill="#ffffff"/>
    <path d="M70 92 Q90 68 110 92 L110 96 L70 96 Z" fill="#ffffff"/>
    <rect x="100" y="82" width="14" height="16" rx="2" fill="{GOLD}"/>
    <text x="90" y="140" text-anchor="middle" font-family="{_HEADING_FONT}" font-weight="700" font-size="15" fill="{INK}">Rezervă online</text>
    <text x="90" y="160" text-anchor="middle" font-family="{_BODY_FONT}" font-size="12" fill="{MUTED}">Alege orașul și</text>
    <text x="90" y="176" text-anchor="middle" font-family="{_BODY_FONT}" font-size="12" fill="{MUTED}">un partener local</text>
  </g>

  <g>
    <circle cx="310" cy="70" r="42" fill="{NAVY}"/>
    <rect x="292" y="50" width="36" height="40" rx="4" fill="#ffffff"/>
    <rect x="298" y="56" width="6" height="6" fill="{NAVY}"/>
    <rect x="308" y="56" width="6" height="6" fill="{NAVY}"/>
    <rect x="298" y="66" width="6" height="6" fill="{NAVY}"/>
    <rect x="316" y="66" width="6" height="6" fill="{NAVY}"/>
    <rect x="308" y="76" width="14" height="6" fill="{NAVY}"/>
    <text x="310" y="140" text-anchor="middle" font-family="{_HEADING_FONT}" font-weight="700" font-size="15" fill="{INK}">Confirmă prin email</text>
    <text x="310" y="160" text-anchor="middle" font-family="{_BODY_FONT}" font-size="12" fill="{MUTED}">Un link de conectare</text>
    <text x="310" y="176" text-anchor="middle" font-family="{_BODY_FONT}" font-size="12" fill="{MUTED}">confirmă rezervarea</text>
  </g>

  <g>
    <circle cx="530" cy="70" r="42" fill="{NAVY}"/>
    <path d="M530 44 C512 44 512 66 530 90 C548 66 548 44 530 44 Z" fill="#ffffff"/>
    <circle cx="530" cy="60" r="8" fill="{NAVY}"/>
    <text x="530" y="140" text-anchor="middle" font-family="{_HEADING_FONT}" font-weight="700" font-size="15" fill="{INK}">Lasă bagajul</text>
    <text x="530" y="160" text-anchor="middle" font-family="{_BODY_FONT}" font-size="12" fill="{MUTED}">La partener, identificat</text>
    <text x="530" y="176" text-anchor="middle" font-family="{_BODY_FONT}" font-size="12" fill="{MUTED}">printr-un cod QR</text>
  </g>

  <g>
    <circle cx="710" cy="70" r="42" fill="{GOLD}"/>
    <path d="M692 60 Q710 40 728 60 L728 92 Q710 100 692 92 Z" fill="#ffffff"/>
    <path d="M700 74 L707 81 L722 64" stroke="{NAVY}" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="710" y="140" text-anchor="middle" font-family="{_HEADING_FONT}" font-weight="700" font-size="15" fill="{INK}">Ridică oricând</text>
    <text x="710" y="160" text-anchor="middle" font-family="{_BODY_FONT}" font-size="12" fill="{MUTED}">În programul de</text>
    <text x="710" y="176" text-anchor="middle" font-family="{_BODY_FONT}" font-size="12" fill="{MUTED}">lucru al partenerului</text>
  </g>
</svg>
"""

_PAGE_HTML = f"""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Despre HaiHui Storage</title>
</head>
<body style="margin:0; padding:0; background:{PAGE_BG}; font-family:{_BODY_FONT};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE_BG};">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
          style="max-width:760px; background:#ffffff; border-radius:12px; overflow:hidden; border:1px solid {BORDER};">
          <tr>
            <td style="background:{NAVY}; padding:24px 40px;">
              <span style="font-family:{_HEADING_FONT}; font-size:22px; font-weight:800; color:#ffffff; letter-spacing:0.2px;">HaiHui</span>
              <span style="font-family:{_BODY_FONT}; font-size:14px; color:{GOLD}; margin-left:8px;">Storage</span>
            </td>
          </tr>

          <tr>
            <td style="padding:40px 40px 8px;">
              <h1 style="font-family:{_HEADING_FONT}; font-size:26px; color:{INK}; margin:0 0 14px; font-weight:700;">Depozitare de bagaje pentru turiști, printr-o rețea de afaceri locale</h1>
              <p style="font-size:15.5px; line-height:1.7; color:{INK}; margin:0;">
                HaiHui Storage conectează turiștii care au nevoie să lase bagajele undeva pentru câteva ore cu magazine,
                cafenele sau recepții din oraș care au spațiu liber. Turistul rezervă online, lasă bagajul la un partener
                și îl ridică atunci când vrea, în programul locației.
              </p>
            </td>
          </tr>

          <tr>
            <td style="padding:28px 40px 8px;">
              {_SVG_FLOW}
            </td>
          </tr>

          <tr>
            <td style="padding:28px 40px 8px;">
              <h2 style="font-family:{_HEADING_FONT}; font-size:18px; color:{INK}; margin:0 0 14px; font-weight:700;">Pentru un partener local</h2>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td valign="top" style="width:50%; padding:0 12px 16px 0;">
                    <p style="margin:0 0 4px; font-family:{_HEADING_FONT}; font-weight:700; font-size:14.5px; color:{INK};">Venit din spațiu neutilizat</p>
                    <p style="margin:0; font-size:14px; line-height:1.6; color:{MUTED};">Fiecare rezervare aduce un procent din valoarea depozitării, fără cost de intrare în platformă.</p>
                  </td>
                  <td valign="top" style="width:50%; padding:0 0 16px 12px;">
                    <p style="margin:0 0 4px; font-family:{_HEADING_FONT}; font-weight:700; font-size:14.5px; color:{INK};">Control total asupra capacității</p>
                    <p style="margin:0; font-size:14px; line-height:1.6; color:{MUTED};">Partenerul stabilește câte bagaje poate primi pe zi și programul de lucru, oricând le poate ajusta.</p>
                  </td>
                </tr>
                <tr>
                  <td valign="top" style="width:50%; padding:0 12px 0 0;">
                    <p style="margin:0 0 4px; font-family:{_HEADING_FONT}; font-weight:700; font-size:14.5px; color:{INK};">Identificare prin cod QR</p>
                    <p style="margin:0; font-size:14px; line-height:1.6; color:{MUTED};">Fiecare rezervare are un cod unic, scanabil, așa că nu e nevoie de evidență pe hârtie.</p>
                  </td>
                  <td valign="top" style="width:50%; padding:0 0 0 12px;">
                    <p style="margin:0 0 4px; font-family:{_HEADING_FONT}; font-weight:700; font-size:14.5px; color:{INK};">Panou propriu</p>
                    <p style="margin:0; font-size:14px; line-height:1.6; color:{MUTED};">Partenerul vede rezervările din locația lui direct din contul propriu, în timp real.</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:24px 40px 36px;">
              <div style="border-top:1px solid {BORDER}; padding-top:20px;">
                <p style="margin:0 0 6px; font-size:14px; color:{MUTED};">Vrei să devii partener sau ai întrebări?</p>
                <p style="margin:0; font-size:14.5px; color:{INK};">
                  Scrie-ne la
                  <a href="mailto:haihuistorage@proton.me" style="color:{NAVY}; text-decoration:underline; font-weight:700;">haihuistorage@proton.me</a>
                </p>
              </div>
            </td>
          </tr>

          <tr>
            <td style="background:#fafafa; padding:14px 40px; text-align:center; font-size:12px; color:{MUTED};">
              HaiHui Storage
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
async def about_page() -> HTMLResponse:
    return HTMLResponse(content=_PAGE_HTML)
