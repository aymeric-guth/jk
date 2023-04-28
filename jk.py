import os
import sys
import subprocess
import shlex
import logging
from dataclasses import dataclass
from typing import Any
import json
import pprint as ppprint
import pathlib

from yaml import CLoader as Loader, load


__version__ = "0.0.1"
logging.basicConfig(level=logging.DEBUG)


class ValidationError(Exception):
    ...


@dataclass(frozen=True, repr=True)
class PreConditions:
    env: list[str]
    validators: list[list[str]]

    @classmethod
    def from_dict(cls, pre_conditions: dict[Any, Any]):
        return PreConditions(
            env=pre_conditions.get("env", []),
            validators=[
                f"'{validator}'" for validator in pre_conditions.get("validators", [])
            ],
        )


@dataclass(frozen=True, repr=True)
class Executor:
    path: str
    options: str

    @classmethod
    def from_dict(cls, executor: dict[Any, Any]):
        path = executor.get("path", "")
        if not path:
            raise ValidationError(f"`path` is not defined for `executor`: {executor}")
        if not os.access(path, os.X_OK):
            raise SystemExit(f"`executor` {executor} is not executable")
        options = executor.get("options", "")
        return Executor(path=path, options=options)

    def to_sh(self) -> list[str]:
        return [self.path, *shlex.split(self.options)]


@dataclass(frozen=True, repr=True)
class Task:
    verb: str
    cmd: str
    executor: Executor
    pre_conditions: PreConditions

    @classmethod
    def from_dict(cls, verb: str, task: dict[Any, Any]):
        cmd = task.get("cmd", "")
        if not cmd:
            raise ValidationError(f"`cmd` is not defined for `task` {task}")
        executor = task.get("executor", "")
        if not executor:
            raise ValidationError(f"`executor` is not defined for `task` {task}")
        return Task(
            verb=verb,
            cmd=cmd,
            executor=Executor.from_dict(executor),
            pre_conditions=PreConditions.from_dict(task.get("pre-conditions", {})),
        )

    def to_sh(self) -> list[str]:
        return [*self.executor.to_sh(), *shlex.split(f"'{self.cmd.rstrip().lstrip()}'")]


def pprint(d: dict[Any, Any]) -> str:
    try:
        return json.dumps(d, indent=4)
    except json.JSONDecodeError:
        return str(d)


def check_sh_identifier(identifier: str) -> str:
    return identifier


def get_verb(prompt: list[str]) -> str:
    return prompt[1]


# pp = ppprint.PrettyPrinter(indent=4, compact=False)
pp = lambda o: ppprint.pformat(o, indent=4, width=140)

### sanity-check
if len(sys.argv) != 2:
    raise SystemExit("Usage: jk <command>")

### user-input
verb = get_verb(sys.argv)

jk_local_conig = os.getenv("JK_LOCAL_CONFIG")
if jk_local_conig is None:
    jk_local_conig = ".jk.yml"

### config load
with open(pathlib.Path().cwd() / jk_local_conig) as f:
    ### yaml format validation for free
    data = load(f, Loader=Loader)

logging.info(f"config={pprint(data)}")

### config level sanity check
if not (executors := data.get("executors", "")):
    raise SystemExit("missing mapping: `executors`")
if len(executors) < 1:
    raise SystemExit("at least 1 `executor` must be defined")

if not (tasks := data.get("tasks", "")):
    raise SystemExit("missing mapping: `tasks`")
if len(tasks) < 1:
    raise SystemExit("at least 1 `task` must be defined")

logging.info(f"tasks={pprint(tasks)}")

### executors validation
executors = [Executor.from_dict(executor) for executor in executors.values()]

logging.info(
    "executors={}".format("\n".join([repr(executor) for executor in executors]))
)

### match user `verb` against config
if verb not in {i for i in tasks}:
    raise SystemExit(f"`verb`: {verb} is not defined in config")

### sanity check `cmd` is defined for `verb`
task = Task.from_dict(verb=verb, task=tasks.get(verb))
logging.info(f"task={pp(task)}")

### merge pre-condition class
logging.info(f"{task.pre_conditions=}")
for var in task.pre_conditions.env:
    logging.info(f"check {var=!r}")
    if os.getenv(check_sh_identifier(var)) is None:
        raise SystemExit(f"pre-condition failed for {var!r}")

for validator in task.pre_conditions.validators:
    logging.info(f"validator={pp(validator)}")
    subprocess.Popen(["sh", "-c", validator], env=os.environ)
    # if subprocess.run(validator, env=os.environ, shell=True).returncode != 0:
    #     raise SystemExit(f"pre-condition failed for {validator=}, non-zero return code")

    ### file exists, file is executable, shbang?
    # if not os.path.exists(validator):
    #     raise SystemExit(
    #         f"pre-condition failed for {validator=}, file does not exists"
    #     )
    # if not os.access(validator, os.X_OK):
    #     raise SystemExit(
    #         f"pre-condition failed for {validator=}, not executable"
    #     )
    # logging.info(f"running {validator=}")
    #     )

process = subprocess.Popen(task.to_sh(), env=os.environ)
