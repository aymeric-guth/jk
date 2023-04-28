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
import ipdb

from yaml import CLoader as Loader, load


__version__ = "0.0.1"
loglevel = os.getenv("JK_LOGLEVEL")
if loglevel is None:
    loglevel = logging.ERROR
logging.basicConfig(level=loglevel)


class ValidationError(Exception):
    ...


@dataclass(frozen=True, repr=True)
class Cmd:
    value: str

    @classmethod
    def from_dict(cls, cmd: str):
        return Cmd(value=cmd.rstrip().lstrip())

    def to_sh(self) -> list[str]:
        return shlex.split(self.value)


@dataclass(frozen=True, repr=True)
class PreConditions:
    env: list[str]
    validators: list[str]

    @classmethod
    def from_dict(cls, pre_conditions: dict[Any, Any]):
        return PreConditions(
            env=pre_conditions.get("env", []),
            validators=pre_conditions.get("validators", []),
        )


@dataclass(frozen=True, repr=True)
class Executor:
    path: str
    options: str
    quote: bool

    @classmethod
    def from_dict(cls, executor: dict[Any, Any]):
        path = executor.get("path", "")
        if not path:
            raise ValidationError(f"`path` is not defined for `executor`: {executor}")

        _path = os.path.expandvars(path)
        if not os.access(_path, os.X_OK):
            raise SystemExit(f"`executor` {executor} is not executable")
        options = executor.get("options", "")
        return Executor(path=_path, options=options, quote=executor.get("quote", False))

    def to_sh(self) -> list[str]:
        return [self.path, *shlex.split(self.options)]


@dataclass(frozen=True, repr=True)
class Task:
    verb: str
    cmd: Cmd
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
            cmd=Cmd.from_dict(cmd),
            executor=Executor.from_dict(executor),
            pre_conditions=PreConditions.from_dict(task.get("pre-conditions", {})),
        )

    def to_sh(self) -> list[str]:
        if self.executor.quote:
            return [*self.executor.to_sh(), self.cmd.value]
        else:
            return [*self.executor.to_sh(), *self.cmd.to_sh()]


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

### pre-condition
logging.info(f"{task.pre_conditions=}")

### pre-conditions, env
logging.info(f"env={pp(task.pre_conditions.env)}")
for identifier in task.pre_conditions.env:
    logging.info(f"{identifier=}")
    if os.getenv(check_sh_identifier(identifier)) is None:
        raise ValidationError(
            f"pre-condition failed for environment variable {identifier=}, undefined"
        )

### pre-conditions, validators
for validator in task.pre_conditions.validators:
    logging.info(f"validator={pp(validator)}")
    proc = subprocess.Popen(["sh", "-c", validator], env=os.environ)
    while proc.poll() is None:
        ...
    if proc.returncode != 0:
        raise SystemExit(f"pre-condition failed for {validator=}, non-zero return code")

### task execution
proc = subprocess.Popen([*task.to_sh()], env=os.environ)
while proc.poll() is None:
    ...
raise SystemExit(proc.returncode)
