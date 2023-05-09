from typing import Any, Optional
import os
import sys
import subprocess
import shlex
import logging
from dataclasses import dataclass
import pathlib
import collections
import time

import ipdb
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
            self._registry.update(
                {"JK_LIBDIR": pathlib.Path(__file__).parent / "jklib"}
            )
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

    def get(self, identifier: str) -> Any:
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
    def from_str(cls, path: str) -> Any:
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
    def from_str(cls, cmd: str) -> Any:
        return Cmd(value=cmd.rstrip().lstrip())

    def to_sh(self) -> list[str]:
        return shlex.split(self.value)


@dataclass(frozen=True, repr=True)
class PreConditions:
    env: list[str]
    validators: list[str]

    @classmethod
    def from_dict(cls, pre_conditions: dict[str, Any]) -> Any:
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
    def from_dict(cls, executor: dict[Any, Any]) -> Any:
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
    on_success: Optional[Any] = None
    on_failure: Optional[Any] = None
    # pre_task: Optional[Any] = None
    # post_task: Optional[Any] = None

    @staticmethod
    def inject_executor(tasks: dict[Any, Any], key: str) -> dict[Any, Any]:
        task = tasks.get(key, None)
        if task is None:
            # task is not defined
            return tasks
        elif isinstance(task, str):
            # assume it is a cmd
            tasks.update({key: {"cmd": task, "executor": tasks.get("executor", None)}})
        elif task.get("executor", None) is None:
            # inject parent's executor
            task.update({"executor": tasks.get("executor", None)})
        return tasks

    @classmethod
    def from_dict(cls, verb: str, task: dict[Any, Any]) -> Any:
        cmd = task.get("cmd", "")
        if not cmd:
            raise ValidationError(f"`cmd` is not defined for `task` {task}")
        executor: dict[str, Any] = task.get("executor", "")
        if not executor:
            raise ValidationError(f"`executor` is not defined for `task` {task}")

        Task.inject_executor(task, "on-success")
        Task.inject_executor(task, "on-failure")

        on_success = task.get("on-success", None)
        on_failure = task.get("on-failure", None)

        if on_success is not None:
            on_success = Task.from_dict("", on_success)
        if on_failure is not None:
            on_failure = Task.from_dict("", on_failure)

        return Task(
            verb=verb,
            cmd=Cmd.from_str(cmd),
            executor=Executor.from_dict(executor),
            pre_conditions=PreConditions.from_dict(task.get("pre-conditions", {})),
            on_success=on_success,
            on_failure=on_failure,
        )

    def to_sh(self) -> list[str]:
        if self.executor.quote:
            return [*self.executor.to_sh(), self.cmd.value]
        else:
            return [*self.executor.to_sh(), *self.cmd.to_sh()]

    def run(self, env: Env) -> subprocess.Popen:
        return subprocess.Popen(
            [*self.to_sh()],
            env=env.dump(),
            cwd=self.executor.ctx.value,
        )

    def __str__(self) -> str:
        return f"{self.verb}: {self.cmd}\n"


@dataclass(frozen=True, repr=True)
class Task_:
    executor: Executor
    cmd: Cmd

    @classmethod
    def from_dict(cls, task: Optional[dict[Any, Any]]) -> Any:
        print(f"{task=}")
        if task is None:
            return task

        cmd = task.get("cmd", "")
        if not cmd:
            raise ValidationError(f"`cmd` is not defined for `task` {task}")

        executor: dict[str, Any] = task.get("executor", "")
        if not executor:
            raise ValidationError(f"`executor` is not defined for `task` {task}")

        return Task_(
            cmd=Cmd.from_str(cmd),
            executor=Executor.from_dict(executor),
        )

    def to_sh(self) -> list[str]:
        if self.executor.quote:
            return [*self.executor.to_sh(), self.cmd.value]
        else:
            return [*self.executor.to_sh(), *self.cmd.to_sh()]


@dataclass(frozen=True, repr=True)
class UserTask:
    verb: str
    pre_conditions: PreConditions
    task: Task_
    on_success: Optional[Task_] = None
    on_failure: Optional[Task_] = None
    pre_task: Optional[Task_] = None
    post_task: Optional[Task_] = None

    @staticmethod
    def inject_executor(tasks: dict[Any, Any], key: str) -> dict[Any, Any]:
        task = tasks.get(key, None)
        if task is not None and (task.get("executor", None) is None):
            task.update({"executor": tasks.get("executor", None)})
        return tasks

    @classmethod
    def from_dict(cls, verb: str, tasks: dict[Any, Any]) -> Any:
        UserTask.inject_executor(tasks, "on-success")
        UserTask.inject_executor(tasks, "on-failure")
        UserTask.inject_executor(tasks, "pre-task")
        UserTask.inject_executor(tasks, "post-task")

        return UserTask(
            verb=verb,
            task=Task_.from_dict(tasks),
            pre_conditions=PreConditions.from_dict(tasks.get("pre-conditions", {})),
            on_success=Task_.from_dict(tasks.get("on-success", None)),
            on_failure=Task_.from_dict(tasks.get("on-failure", None)),
            pre_task=Task_.from_dict(tasks.get("pre-task", None)),
            post_task=Task_.from_dict(tasks.get("post-task", None)),
        )


def visit(root: YamlNode) -> list[tuple[YamlNode, YamlNode]]:
    queue: collections.deque[YamlNode] = collections.deque([root])
    res: list[tuple[YamlNode, YamlNode]] = []
    last: Optional[YamlNode] = None
    node: YamlNode

    while queue:
        node = queue.popleft()
        logging.info(f"{node=}")

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


def load_includes(path: pathlib.Path, env: Env):
    assert path.exists(), f"{path!s} does not exist"
    assert path.is_file(), f"{path!s} is not a file"

    with open(path) as f:
        root = yaml.compose(f)

    for parent, node in visit(root):
        if isinstance(parent.value[0], tuple):
            _name = parent.value[0][0].value
        elif isinstance(parent, yaml.MappingNode):
            ...
        else:
            raise SystemExit(f"parent.value[0] is not a tuple: {parent=}")
            logging.error(f"{parent.value[0]=}")
            _name = parent.value[0].value[0]

        # try:
        #     _name = parent.value[0][0].value
        # except Exception:
        #     ipdb.set_trace()
        #     print()
        #     _name = ""

        if _name not in {
            "cmd",
            "env",
            "pre-conditions",
            "executor",
            "validators",
        }:
            _path = env.libdir / "tasks.yml"
        elif _name == "executor":
            _path = env.libdir / "executors.yml"
        else:
            _path = env.libdir / f"{parent.value}.yml"

        _node = load_includes(_path, env)
        for k, v in _node.value:
            if node.value == k.value:
                for i, (_k, _v) in enumerate(parent.value):
                    if _v is node:
                        parent.value[i] = v

                # ipdb.set_trace()
                # node.value = v.value
                # node.tag = v.tag
                break
        else:
            raise ValidationError(f"Could not find {node.value} in {parent.value}")

    return root


def check_sh_identifier(identifier: str) -> str:
    return identifier


def get_verb(prompt: list[str]) -> str:
    return prompt[1]


def handler(proc: subprocess.Popen) -> tuple[int, list, list]:
    stdout, stderr = proc.communicate()
    return proc.returncode, stdout, stderr


def _runner(proc: subprocess.Popen) -> int:
    try:
        while 1:
            time.sleep(0.01)
            if proc.poll() is not None:
                break
    except Exception as err:
        sys.stderr.write(str(err) + "\n")
        return 1
    except KeyboardInterrupt:
        return 0

    return proc.returncode


def runner(task: Task, env: Env) -> int:
    # if task.pre_task is not None:
    #     sys.stderr.write("pre_task\n")
    #     rc = _runner(task.pre_task.run(env))
    #     if rc != 0:
    #         raise SystemExit(rc)

    rc = _runner(task.run(env))

    if rc == 0 and task.on_success is not None:
        sys.stderr.write("on_success\n")
        rc = _runner(task.on_success.run(env))
        if rc != 0:
            raise SystemExit(rc)

    elif rc != 0 and task.on_failure is not None:
        sys.stderr.write("on_failure\n")
        rc = _runner(task.on_failure.run(env))
        if rc != 0:
            raise SystemExit(rc)

    # if task.post_task is not None:
    #     sys.stderr.write("post_task\n")
    #     last = rc
    #     rc = _runner(task.post_task.run(env))
    #     if rc != 0:
    #         raise SystemExit(rc)
    #     return last

    sys.stderr.write("no_handler\n")

    return rc


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

    logging.info(f"JK_LIBDIR={env.libdir}")
    logging.info(f"JK_LOCAL_CONFIG={env.get('JK_LOCAL_CONFIG')}")

    ### config load
    ### pre-processing for !include
    root = load_includes(env.get("JK_LOCAL_CONFIG"), env)
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

    sys_tasks = {
        "list",
    }
    ### match user `verb` against config
    if verb in sys_tasks:
        for name in tasks:
            sys.stdout.write(f"{name}: ``\n")
        return 0
    elif verb not in {i for i in tasks}:
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

    return runner(task, env)

    # pre-task -> status code
    # task -> status code
    # on-success -> status code
    # on-failure -> status code
    # post-task -> status code


if __name__ == "__main__":
    raise SystemExit(main())
