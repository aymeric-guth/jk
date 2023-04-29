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
from typing import Self

# import ipdb
from yaml import CLoader as Loader, load


__version__ = "0.0.1"
loglevel = os.getenv("JK_LOGLEVEL")
if not loglevel:
    loglevel = logging.ERROR
logging.basicConfig(level=loglevel)


class ValidationError(Exception):
    ...


class Env:
    def __init__(self):
        self._registry: dict[str, Any] = {k: v for k, v in os.environ.items()}
        if "JK_LIBDIR" not in self._registry:
            self._registry.get("HOME")
            os.getenv("HOME")
            self._registry.update({"JK_LIBDIR": pathlib.Path(__file__).parent})
            logging.warning(
                f"JK_LIBDIR is not defined, using default: {self._registry['JK_LIBDIR']}"
            )
            return
        libdir = pathlib.Path(self._registry["JK_LIBDIR"])
        if not libdir.exists() or not libdir.is_dir():
            raise SystemExit(f"JK_LIBDIR={libdir!s} is not a valid path")
        self._registry["JK_LIBDIR"] = libdir

    @property
    def libdir(self) -> pathlib.Path:
        return self._registry["JK_LIBDIR"]

    @libdir.setter
    def libdir(self, value: Any) -> None:
        raise TypeError("libdir is read-only")

    def get(self, identifier: str) -> str:
        value = self._registry.get(identifier)
        if value is None:
            raise RuntimeError(f"{identifier=} is not defined")
        return value

    def query(self, varname: str) -> bool:
        value = self._registry.get(varname)
        if value is not None:
            return True
        return False

    # value must implement __str__
    def set(self, identifier: str, value: Any) -> None:
        logging.info(f"Env.set(indentifier={identifier}, value={value})")
        prev = self._registry.get(identifier)
        if not prev or value != prev:
            self._registry.update({identifier: value})

    def dump(self) -> dict[str, str]:
        return {k: str(v) for k, v in self._registry.items()}


@dataclass(frozen=True, repr=True)
class Path:
    value: pathlib.Path
    raw: str

    @classmethod
    def from_dict(cls, path: str) -> Self:
        if "$" in path:
            path = os.path.expandvars(path)
        _path = pathlib.Path(path)
        if not _path.exists():
            raise ValidationError(f"`path` {path} does not exist")
        return Path(value=_path, raw=path)


@dataclass(frozen=True, repr=True)
class Cmd:
    value: str

    @classmethod
    def from_dict(cls, cmd: str) -> Self:
        return Cmd(value=cmd.rstrip().lstrip())

    def to_sh(self) -> list[str]:
        return shlex.split(self.value)


@dataclass(frozen=True, repr=True)
class PreConditions:
    env: list[str]
    validators: list[str]

    @classmethod
    def from_dict(cls, pre_conditions: dict[str, Any]) -> Self:
        return PreConditions(
            env=pre_conditions.get("env", []),
            validators=pre_conditions.get("validators", []),
        )


@dataclass(frozen=True, repr=True)
class Executor:
    path: str
    options: str
    quote: bool
    ctx: Path

    @classmethod
    def from_dict(cls, executor: dict[Any, Any]) -> Self:
        path = executor.get("path", "")
        if not path:
            raise ValidationError(f"`path` is not defined for `executor`: {executor}")

        _path = os.path.expandvars(path)
        if not os.access(_path, os.X_OK):
            raise SystemExit(f"`executor` {executor} is not executable")
        options = executor.get("options", "")
        ctx = executor.get("ctx", "")
        if ctx:
            _ctx = Path.from_dict(ctx)
        else:
            _ctx = Path.from_dict(os.getcwd())

        quote = executor.get("quote", False)
        if not isinstance(quote, bool):
            raise ValidationError(f"`quote` is not a boolean: {quote}")
        return Executor(path=_path, options=options, quote=quote, ctx=_ctx)

    def to_sh(self) -> list[str]:
        return [self.path, *shlex.split(self.options)]


@dataclass(frozen=True, repr=True)
class Task:
    verb: str
    cmd: Cmd
    executor: Executor
    pre_conditions: PreConditions

    @classmethod
    def from_dict(cls, verb: str, task: dict[Any, Any]) -> Self:
        cmd = task.get("cmd", "")
        if not cmd:
            raise ValidationError(f"`cmd` is not defined for `task` {task}")
        executor: dict[str, Any] = task.get("executor", "")
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
env = Env()


def main() -> int:
    ### sanity-check
    if len(sys.argv) != 2:
        raise SystemExit("Usage: jk <command>")

    ### user-input
    verb = get_verb(sys.argv)

    if not env.get("JK_LOCAL_CONFIG"):
        jk_local_config = pathlib.Path().cwd() / ".jk.yml"
    elif pathlib.Path(env.get("JK_LOCAL_CONFIG")).exists():
        jk_local_config = pathlib.Path(env.get("JK_LOCAL_CONFIG"))
    else:
        raise SystemExit(
            f"JK_LOCAL_CONFIG={env.get('JK_LOCAL_CONFIG')} is not a valid path"
        )

    ### config load
    with open(jk_local_config, "r") as f:
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
        if not os.getenv(check_sh_identifier(identifier)):
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
            raise SystemExit(
                f"pre-condition failed for {validator=}, non-zero return code"
            )

    ### task execution
    logging.info(f"task={pp(task)}")
    logging.info(f"cmd={task.to_sh()}")

    env.set("PWD", str(task.executor.ctx.value))
    proc = subprocess.Popen([*task.to_sh()], env=env.dump())
    while proc.poll() is None:
        ...
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
