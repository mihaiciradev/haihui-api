import io

import qrcode


def generate_qr_png(data: str) -> bytes:
    img = qrcode.make(data, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
