from app.core.email_templates import render_email


def test_render_email_includes_support_contact():
    html = render_email(
        preheader="pre", heading="Heading", body_html="<p>Body</p>", locale="ro"
    )
    assert "haihuistorage@proton.me" in html
    assert 'mailto:haihuistorage@proton.me' in html


def test_render_email_includes_cta_when_provided():
    html = render_email(
        preheader="pre",
        heading="Heading",
        body_html="<p>Body</p>",
        cta_label="Click me",
        cta_url="https://example.com/verify",
    )
    assert "Click me" in html
    assert "https://example.com/verify" in html


def test_render_email_omits_cta_block_when_not_provided():
    with_cta = render_email(
        preheader="p", heading="H", body_html="<p>B</p>", cta_label="Go", cta_url="https://x.test"
    )
    without_cta = render_email(preheader="p", heading="H", body_html="<p>B</p>")
    # Only the footer's mailto link remains without a CTA -- one fewer <a> tag.
    assert with_cta.count("<a ") == without_cta.count("<a ") + 1


def test_render_email_respects_locale_copy():
    ro_html = render_email(preheader="p", heading="H", body_html="<p>B</p>", locale="ro")
    en_html = render_email(preheader="p", heading="H", body_html="<p>B</p>", locale="en")
    assert "Ai nevoie de ajutor" in ro_html
    assert "Need help" in en_html


def test_render_email_unknown_locale_falls_back_to_ro():
    html = render_email(preheader="p", heading="H", body_html="<p>B</p>", locale="fr")
    assert "Ai nevoie de ajutor" in html
