import os
import sys
import subprocess
import shlex
import logging
from dataclasses import dataclass
from typing import Optional, Any

from yaml import CLoader as Loader, CDumper as Dumper, load


__version__ = "0.0.1"
logging.basicConfig(level=logging.DEBUG)


class ValidationError(Exception):
    ...


@dataclass(frozen=True, repr=True)
class PreConditions:
    env: list[str]
    validators: list[str]

    @classmethod
    def from_json(cls, pre_conditions: dict[Any, Any]):
        return PreConditions(
            env=pre_conditions.get("env", []),
            validators=pre_conditions.get("validators", []),
        )


@dataclass(frozen=True, repr=True)
class Executor:
    path: str
    options: str

    @classmethod
    def from_json(cls, executor: dict[Any, Any]):
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
            executor=Executor.from_json(executor),
            pre_conditions=PreConditions.from_json(task.get("pre-conditions", {})),
        )

    def to_sh(self) -> str:
        return [*self.executor.to_sh(), *shlex.split(f"'{self.cmd.rstrip().lstrip()}'")]


def check_sh_identifier(identifier: str) -> str:
    return identifier


def get_verb(prompt: list[str]) -> str:
    return prompt[1]


### sanity-check
if len(sys.argv) != 2:
    raise SystemExit("Usage: jk.py <command>")

### user-input
verb = get_verb(sys.argv)

### config load
with open(".jk.yml") as f:
    ### yaml format validation for free
    data = load(f, Loader=Loader)

logging.info(f"{data=}")


### config level sanity check
if not (executors := data.get("executors", "")):
    raise SystemExit("missing mapping: `executors`")
if len(executors) < 1:
    raise SystemExit("at least 1 `executor` must be defined")

if not (tasks := data.get("tasks", "")):
    raise SystemExit("missing mapping: `tasks`")
if len(tasks) < 1:
    raise SystemExit("at least 1 `task` must be defined")
logging.info(f"{tasks=}")

### executors validation
executors = [Executor.from_json(executor) for executor in executors.values()]

logging.info(f"{executors=}")

### match user `verb` against config
if verb not in {i for i in tasks}:
    raise SystemExit(f"`verb`: {verb} is not defined in config")

### sanity check `cmd` is defined for `verb`
task = Task.from_dict(verb=verb, task=tasks.get(verb))


### merge pre-condition class
logging.info(f"{task.pre_conditions=}")
for var in task.pre_conditions.env:
    logging.info(f"check {var=}")
    if os.getenv(check_sh_identifier(var)) is None:
        raise SystemExit(f"pre-condition failed for {var}")

for validator in task.pre_conditions.validators:
    logging.info(f"{validator=}")

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
    # if subprocess.run(validator, env=os.environ).returncode != 0:
    #     raise SystemExit(
    #         f"pre-condition failed for {validator=}, non-zero return code"
    #     )

print(task.to_sh())
subprocess.Popen(task.to_sh(), env=os.environ)

# ( project-env-valid ) || return 1
# [ ! -f .venv/bin/python ] && return 1
# [ -z "$VIRTUAL_ENV" ] && return 1
# .venv/bin/python -m build . --wheel || return 1
