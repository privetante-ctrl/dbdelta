from dbdelta.plan.graph import order_by_dependencies


def test_nodes_follow_their_dependencies() -> None:
    result = order_by_dependencies({"orders": ["users", "products"], "users": [], "products": []})

    assert result.order == ("products", "users", "orders")
    assert result.broken == frozenset()


def test_chains_are_ordered_regardless_of_names() -> None:
    result = order_by_dependencies({"a": ["b"], "b": ["c"], "c": []})

    assert result.order == ("c", "b", "a")


def test_self_and_unknown_dependencies_are_ignored() -> None:
    result = order_by_dependencies({"tree": ["tree", "elsewhere"]})

    assert result.order == ("tree",)
    assert result.broken == frozenset()


def test_two_node_cycle_breaks_one_dependency() -> None:
    result = order_by_dependencies({"a": ["b"], "b": ["a"]})

    assert result.broken == {("a", "b")}
    assert result.order == ("a", "b")


def test_three_node_cycle_breaks_one_dependency() -> None:
    result = order_by_dependencies({"a": ["c"], "b": ["a"], "c": ["b"]})

    assert result.broken == {("a", "c")}
    assert result.order == ("a", "b", "c")


def test_each_independent_cycle_is_broken_once() -> None:
    result = order_by_dependencies({"a": ["b"], "b": ["a"], "x": ["y"], "y": ["x"], "z": ["a"]})

    assert result.broken == {("a", "b"), ("x", "y")}
    assert result.order.index("a") < result.order.index("z")


def test_result_does_not_depend_on_input_order() -> None:
    forward = {"a": ["b", "c"], "b": ["c"], "c": ["a"], "d": []}
    backward = {node: list(reversed(deps)) for node, deps in reversed(forward.items())}

    assert order_by_dependencies(forward) == order_by_dependencies(backward)
