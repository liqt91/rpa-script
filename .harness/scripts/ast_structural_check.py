import ast
import os
import sys

# Layer order: lower index = lower layer (can be imported by higher layers)
LAYER_ORDER = ["dtypes", "config", "repo", "service", "runtime"]


def get_file_layer(path: str) -> str | None:
    """Extract the layer name from a file path under src/."""
    parts = path.replace("\\", "/").split("/")
    if "src" not in parts:
        return None
    src_idx = parts.index("src")
    if src_idx + 1 < len(parts):
        layer = parts[src_idx + 1]
        if layer in LAYER_ORDER:
            return layer
    return None


def get_target_layer(module_name: str | None) -> str | None:
    """Extract target layer from an absolute module name."""
    if not module_name:
        return None
    parts = module_name.split(".")
    if parts[0] == "src" and len(parts) > 1:
        target = parts[1]
    else:
        target = parts[0]
    return target if target in LAYER_ORDER else None


def check_file(path: str, file_layer: str) -> list[str]:
    errors = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        return [f"{path}:{e.lineno or 0} SyntaxError: {e.msg}"]
    except Exception as e:
        return [f"{path}: Error reading file: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # Skip relative imports (from . import X, from .. import X)
            if getattr(node, "level", 0) > 0:
                continue
            module = node.module
            target_layer = get_target_layer(module)
            if target_layer and file_layer:
                if LAYER_ORDER.index(file_layer) < LAYER_ORDER.index(target_layer):
                    line = getattr(node, "lineno", 0)
                    errors.append(
                        f"{path}:{line} [{file_layer}] imports '{module}' [{target_layer}] — backward dependency"
                    )

        elif isinstance(node, ast.Import):
            for alias in node.names:
                target_layer = get_target_layer(alias.name)
                if target_layer and file_layer:
                    if LAYER_ORDER.index(file_layer) < LAYER_ORDER.index(target_layer):
                        line = getattr(node, "lineno", 0)
                        errors.append(
                            f"{path}:{line} [{file_layer}] imports "
                            f"'{alias.name}' [{target_layer}] — backward dependency"
                        )

    return errors


def main() -> int:
    src_dir = "src"
    if not os.path.isdir(src_dir):
        print(f"ERROR: {src_dir}/ directory not found")
        return 1

    errors = []
    for root, _dirs, files in os.walk(src_dir):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(root, filename)
            file_layer = get_file_layer(path)
            if file_layer is None:
                continue
            errors.extend(check_file(path, file_layer))

    if errors:
        print("STRUCTURAL TEST FAILED")
        for e in errors:
            print(f"  {e}")
        return 1
    else:
        print("STRUCTURAL TEST PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
