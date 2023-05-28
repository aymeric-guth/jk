# https://www.youtube.com/watch?v=NR-BGPhDICA
from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(loader=FileSystemLoader("templates"), autoescape=select_autoescape())
template = env.get_template("config.yml.j2")
res = template.render(
    **{
        "cmd_run_python": """
        : \\
        && [ -d .venv ] && rm -rf .venv \\
        && python3 -m virtualenv .venv \\
        && [ -f requirements.txt ] \\
        && .venv/bin/python -m pip install -r requirements.txt \\
        && [ -n "${commands[direnv]}" ] \\
        && direnv reload \\
        && :
""",
    }
)
print(res)
