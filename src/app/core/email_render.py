from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def render_email_template(template_name: str, **context):

    template = _env.get_template(template_name)

    return template.render(**context)
