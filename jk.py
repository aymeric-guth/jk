import os
import sys
import subprocess
import shlex
import logging

from yaml import CLoader as Loader, CDumper as Dumper, load


__version__ = "0.0.1"


logging.basicConfig(level=logging.DEBUG)
if len(sys.argv) != 2:
    raise SystemExit("Usage: jk.py <command>")


def check_sh_identifier(identifier: str) -> str:
    return identifier


### user-input
verb = sys.argv[1]
### sanity-check

with open(".jk.yml") as f:
    data = load(f, Loader=Loader)
logging.info(f"{data=}")

nodes = [i for i in data]
if verb not in nodes:
    raise SystemExit(f"{verb=} not defined in config")

logging.info(f"{nodes=}")

if not (commands := data.get(verb).get("commands", "")):
    raise SystemExit(f"{verb=} has no commands")

if pre_conditions := data.get(verb).get("pre-conditions", ""):
    logging.info(f"{pre_conditions=}")
    if env := pre_conditions.get("env", ""):
        for var in env:
            logging.info(f"check {var=}")
            if os.getenv(check_sh_identifier(var)) is None:
                raise SystemExit(f"pre-condition failed for {var}")

    if validators := pre_conditions.get("validators", ""):
        logging.info(f"{validators=}")
        for validator in validators:
            logging.info(f"{validator=}")
            ### file exists, file is executable, shbang?
            if not os.path.exists(validator):
                raise SystemExit(
                    f"pre-condition failed for {validator=}, file does not exists"
                )
            if not os.access(validator, os.X_OK):
                raise SystemExit(
                    f"pre-condition failed for {validator=}, not executable"
                )
            logging.info(f"running {validator=}")
            if subprocess.run(validator, env=os.environ).returncode != 0:
                raise SystemExit(
                    f"pre-condition failed for {validator=}, non-zero return code"
                )

for cmd in commands:
    subprocess.run(shlex.split(cmd), env=os.environ)

# ( project-env-valid ) || return 1
# [ ! -f .venv/bin/python ] && return 1
# [ -z "$VIRTUAL_ENV" ] && return 1
# .venv/bin/python -m build . --wheel || return 1
