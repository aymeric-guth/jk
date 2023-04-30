from typing import Any, Self
import os
import sys
import subprocess
import shlex
import logging
from dataclasses import dataclass
import pathlib
import collections

# import ipdb
import yaml
from rich.logging import RichHandler


__version__ = "0.0.1"
loglevel = os.getenv("JK_LOGLEVEL")
if not loglevel:
    loglevel = logging.ERROR
FORMAT = "%(message)s"
logging.basicConfig(
    level=loglevel, format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

YamlNode = yaml.nodes.ScalarNode | yaml.nodes.MappingNode | yaml.nodes.SequenceNode


class ValidationError(Exception):
    ...


class UndefinedIdentifier:
    def __bool__(self) -> bool:
        return False


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

    def query(self, identifier: str) -> bool:
        value = self._registry.get(identifier, UndefinedIdentifier())
        if not isinstance(value, UndefinedIdentifier):
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

    def __repr__(self) -> str:
        _env = [f"{k}={v}" for k, v in self._registry.items()]
        _env.sort()
        return "Env({})".format(", ".join(_env))


@dataclass(frozen=True, repr=True)
class Path:
    value: pathlib.Path
    raw: str

    @classmethod
    def from_str(cls, path: str) -> Self:
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
    def from_str(cls, cmd: str) -> Self:
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
            _ctx = Path.from_str(ctx)
        else:
            _ctx = Path.from_str(os.getcwd())

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
            cmd=Cmd.from_str(cmd),
            executor=Executor.from_dict(executor),
            pre_conditions=PreConditions.from_dict(task.get("pre-conditions", {})),
        )

    def to_sh(self) -> list[str]:
        if self.executor.quote:
            return [*self.executor.to_sh(), self.cmd.value]
        else:
            return [*self.executor.to_sh(), *self.cmd.to_sh()]


def visit(root: YamlNode) -> list[tuple[YamlNode, YamlNode]]:
    queue: collections.deque[YamlNode] = collections.deque([root])
    res: list[tuple[YamlNode, YamlNode]] = []
    last: Optional[YamlNode] = None
    node: YamlNode

    while queue:
        node = queue.popleft()
        if isinstance(node, yaml.ScalarNode) and node.tag == "!include":
            assert last is not None
            res.append((last, node))
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                queue.append(child)
        elif isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                queue.extend((k, v))
        last = node
    return res


def check_sh_identifier(identifier: str) -> str:
    return identifier


def get_verb(prompt: list[str]) -> str:
    return prompt[1]


def main() -> int:
    ### harvest caller's environment
    env = Env()

    ### sanity-check
    if len(sys.argv) != 2:
        raise SystemExit("Usage: jk <command>")

    ### user-input
    verb = get_verb(sys.argv)

    if not env.query("JK_LOCAL_CONFIG"):
        env.set("JK_LOCAL_CONFIG", pathlib.Path().cwd() / ".jk.yml")
    # TODO check .yml, check valid yaml
    elif pathlib.Path(env.get("JK_LOCAL_CONFIG")).exists():
        env.set("JK_LOCAL_CONFIG", pathlib.Path(env.get("JK_LOCAL_CONFIG")))
    else:
        raise SystemExit(
            f"JK_LOCAL_CONFIG={env.get('JK_LOCAL_CONFIG')} is not a valid path"
        )

    ### config load
    with open(env.get("JK_LOCAL_CONFIG"), "r") as f:
        ### yaml format validation for free
        root = yaml.compose(f, yaml.CLoader)

    ### pre-processing for !include
    tags = visit(root)
    for parent, node in tags:
        _path = env.libdir / f"{parent.value}.yml"
        logging.info(f"{_path=}")
        assert _path.exists(), f"{_path!s} does not exist"
        assert _path.is_file(), f"{_path!s} is not a file"
        with open(_path) as f:
            _include = yaml.load(f, yaml.CLoader)
            logging.info(f"{_include=}")
            assert (
                _include.get(node.value, None) is not None
            ), f"could not find `{node.value}` in {_path}"
            node.value = _include[node.value]
            node.tag = "tag:yaml.org,2002:str"

    data = yaml.load(yaml.serialize(root), yaml.CLoader)

    logging.info(f"config={data}")

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
    executors = [Executor.from_dict(executor) for executor in executors.values()]
    logging.info(f"{executors=}")

    ### match user `verb` against config
    if verb not in {i for i in tasks}:
        raise SystemExit(f"`verb`: {verb} is not defined in config")

    ### sanity check `cmd` is defined for `verb`
    task = Task.from_dict(verb=verb, task=tasks.get(verb))
    logging.info(f"{task=}")

    ### pre-condition
    logging.info(f"{task.pre_conditions=}")

    ### pre-conditions, env
    logging.info(f"pre_conditions.env={task.pre_conditions.env}")
    for identifier in task.pre_conditions.env:
        logging.info(f"{identifier=}")
        if not os.getenv(check_sh_identifier(identifier)):
            raise ValidationError(
                f"pre-condition failed for environment variable {identifier=}, undefined"
            )

    ### pre-conditions, validators
    for validator in task.pre_conditions.validators:
        logging.info(f"validator={validator}")
        proc = subprocess.Popen(["sh", "-c", validator], env=os.environ)
        while proc.poll() is None:
            ...
        if proc.returncode != 0:
            raise SystemExit(
                f"pre-condition failed for {validator=}, non-zero return code"
            )

    ### task execution
    logging.info(f"{task=}")
    logging.info(f"cmd={task.to_sh()}")
    logging.info(f"{env=}")

    proc = subprocess.Popen(
        [*task.to_sh()], env=env.dump(), cwd=task.executor.ctx.value
    )
    while proc.poll() is None:
        ...
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
