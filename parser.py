import pathlib
import json
from typing import Any, Optional
import os
import ipdb
import collections

import yaml


class ValidationError(Exception):
    ...


YamlNode = yaml.nodes.ScalarNode | yaml.nodes.MappingNode | yaml.nodes.SequenceNode


class Env:
    def __init__(self):
        self._registry: dict[str, Any] = {k: v for k, v in os.environ.items()}
        if "JK_LIBDIR" not in self._registry:
            self._registry.update({"JK_LIBDIR": pathlib.Path(__file__).parent})
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


def pprint(d: dict[Any, Any]) -> str:
    try:
        return json.dumps(d, indent=4)
    except json.JSONDecodeError:
        return str(d)


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


def include(loader, node):
    fields = loader.construct_mapping(node)
    print(fields)
    return fields


env = Env()
yaml.CLoader.add_constructor("!include", include)

with open(".jk.yml") as f:
    root = yaml.compose(f, yaml.CLoader)
    tags = visit(root)
    for parent, node in tags:
        if not os.path.exists(env.libdir / parent.value):
            raise ValidationError(f"invalid path: {env.libdir / parent.value!s}")
