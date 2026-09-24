"""Deterministic dependency ordering that breaks cycles."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter


@dataclass(frozen=True, slots=True)
class DependencyOrder:
    """Nodes in dependency order, and the dependencies ignored to get there."""

    order: tuple[str, ...]
    broken: frozenset[tuple[str, str]]
    """``(dependent, dependency)`` pairs that had to be ignored to break cycles."""


def order_by_dependencies(dependencies: Mapping[str, Iterable[str]]) -> DependencyOrder:
    """Order the nodes so that each one comes after the nodes it depends on.

    ``dependencies`` maps every node to the nodes it depends on; dependencies on the node
    itself or on nodes outside the mapping are ignored. When nodes depend on each other in
    a cycle, one dependency of that cycle is ignored (the first one in alphabetical order)
    and ordering starts again, so only as many dependencies are broken as the cycles need.
    Nodes that could come in any order are sorted by name, making the result stable.
    """
    graph = {
        node: {other for other in required if other != node and other in dependencies}
        for node, required in dependencies.items()
    }
    broken: set[tuple[str, str]] = set()
    while True:
        sorter = TopologicalSorter({node: sorted(graph[node]) for node in sorted(graph)})
        try:
            sorter.prepare()
        except CycleError as error:
            cycle: list[str] = error.args[1]
            # graphlib lists each node of the cycle right before a node that depends on it.
            dependent, dependency = min(zip(cycle[1:], cycle, strict=False))
            graph[dependent].discard(dependency)
            broken.add((dependent, dependency))
            continue
        order: list[str] = []
        while sorter.is_active():
            ready = sorted(sorter.get_ready())
            order.extend(ready)
            sorter.done(*ready)
        return DependencyOrder(tuple(order), frozenset(broken))
