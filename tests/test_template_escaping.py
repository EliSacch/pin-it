from pathlib import Path

PAYLOAD = '" onfocus="alert(1)" x="<b>'
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "app" / "templates"


def test_tooltip_trigger_values_are_autoescaped(app):
    template = app.jinja_env.from_string(
        '{% from "macros/tooltip.html" import tooltip %}'
        "{% call tooltip(text) %}<button aria-label=\"{{ label }}\"></button>{% endcall %}"
    )

    html = template.render(label=PAYLOAD, text=PAYLOAD)

    assert 'onfocus="alert(1)"' not in html
    assert "<b>" not in html
    assert "&#34; onfocus=&#34;alert(1)&#34;" in html


def test_form_actions_escapes_its_arguments(app):
    template = app.jinja_env.from_string(
        '{% from "macros/formActions.html" import formActions %}{{ formActions(label, label) }}'
    )

    html = template.render(label=PAYLOAD)

    assert 'onfocus="alert(1)"' not in html
    assert "<b>" not in html


def test_templates_do_not_disable_autoescaping():
    offenders = [
        str(path.relative_to(TEMPLATES_DIR))
        for path in TEMPLATES_DIR.rglob("*.html")
        if "|safe" in path.read_text().replace(" ", "")
        or "autoescapefalse" in path.read_text().replace(" ", "")
    ]

    assert offenders == []
