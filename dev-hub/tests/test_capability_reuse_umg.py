
import ast
from pathlib import Path

def test_reuse_requires_umg():
    source = Path(__file__).resolve().parents[1] / "bin/capability-foundry.py"
    tree = ast.parse(source.read_text())
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            fields = {
                k.value: v
                for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            if "materialization_gate_required" in fields:
                matches.append(fields)

    assert len(matches) == 1
    for key in ("required", "materialization_gate_required"):
        value = matches[0][key]
        assert isinstance(value, ast.Constant)
        assert value.value is True

if __name__ == "__main__":
    test_reuse_requires_umg()
    print("CAPABILITY_REUSE_UMG_INVARIANT=PASS")
