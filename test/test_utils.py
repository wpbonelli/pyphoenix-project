from flopy4.utils import tree


def test_tree():
    t = tree()
    t.a.b.c = "d"
    assert t.a.b.c == t["a"]["b"]["c"] == "d"
