"""
Split content.js handler registrations into individual files under extension/handlers/.
Also generates the base file (utilities + message listener) without handlers.

Usage: python scripts/split_handlers.py
"""
import re, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "extension", "content.js")
HANDLERS_DIR = os.path.join(ROOT, "extension", "handlers")
BASE_FILE = os.path.join(ROOT, "extension", "content_base.js")
BUILD_SCRIPT = os.path.join(ROOT, "scripts", "build_content_js.py")

# Curated subset — only these keep .js suffix; rest get .js.curated_removed
CURATED = {
    # extension
    "clickElement", "inputText", "hover", "scrollIntoView", "scrollToBottom",
    "getText", "getAttribute", "getValue", "waitForElement",
    "navigate", "newTab", "closeBrowser",
    "pressKey", "takeScreenshot", "executeJs", "checkElementExists",
    # legacy wrappers (routed via elementAction, kept for backward compat)
    "click", "input", "extract", "scroll",
    "elementAction",
    # internal helpers
    "findElements",
}

CUT = {
    "doubleClick", "rightClick", "clickIfExists", "unhover", "clearInput",
    "selectOption", "getHtml", "getElementCount", "getPageTitle", "getCurrentUrl",
    "checkElementVisible", "waitForElementHide", "waitForLoad", "waitForUrl",
    "waitForText", "keyCombo", "scrollToTop", "scrollOneScreen", "scrollBy",
    "inputAndPressEnter", "getElementText",
}


def main():
    with open(CONTENT, encoding="utf-8") as f:
        source = f.read()

    # Find the handler section boundaries
    lines = source.split("\n")
    handler_start = None
    handler_end = None
    msg_listener_start = None

    for i, line in enumerate(lines):
        if "// ─── Step handlers ───" in line:
            handler_start = i
        if "// ─── Message listener ───" in line:
            handler_end = i
            msg_listener_start = i

    if handler_start is None or handler_end is None:
        print("ERROR: could not locate handler section")
        return

    base_lines = lines[:handler_start] + lines[msg_listener_start:]

    os.makedirs(HANDLERS_DIR, exist_ok=True)

    # Extract individual handler registrations
    handler_section = "\n".join(lines[handler_start:handler_end])
    # Match each registerHandler(...) block
    pattern = re.compile(
        r"(//.*\n)*"  # optional section comment
        r"\s*registerHandler\(\s*'([^']+)'[^)]*\)\s*;",
        re.DOTALL
    )

    # Find all registerHandler calls with their full text
    # Better approach: find each registerHandler start and match to its closing );
    handlers_found = {}
    pos = 0
    while True:
        m = re.search(r"registerHandler\s*\(\s*'([^']+)'", handler_section[pos:])
        if not m:
            break
        name = m.group(1)
        start = pos + m.start()
        # Find matching closing ); by counting parens
        depth = 0
        i = start
        while i < len(handler_section):
            c = handler_section[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    # Check if next char is ;
                    if i + 1 < len(handler_section) and handler_section[i + 1] == ";":
                        i += 1  # include ;
                        break
            i += 1

        if depth != 0:
            print(f"WARN: unmatched parens for {name}")
            break

        full_block = handler_section[start:i + 1].strip()
        # Also grab preceding section comment lines
        block_lines = handler_section[:start].split("\n")
        comment_prefix = []
        for bl in reversed(block_lines):
            bls = bl.strip()
            if bls.startswith("// ───") or bls == "":
                comment_prefix.insert(0, bl)
            else:
                break
        full_block = "\n".join(comment_prefix).strip() + "\n\n" + full_block if comment_prefix else full_block

        handlers_found[name] = full_block
        pos = i + 1

    # Write handler files
    curated_count = 0
    cut_count = 0
    for name, code in sorted(handlers_found.items()):
        is_curated = name in CURATED
        ext = ".js" if is_curated else ".js.curated_removed"
        fpath = os.path.join(HANDLERS_DIR, f"{name}{ext}")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(code + "\n")
        if is_curated:
            curated_count += 1
        else:
            cut_count += 1

    # Write base file (utilities + message listener — no handler registrations)
    with open(BASE_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(base_lines))
        f.write("\n")

    # Write build script
    build_script = '''"""
Build content.js by concatenating base utilities + enabled handler files.
Run during development to keep extension/content.js and dist/ in sync.
"""
import os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDLERS_DIR = os.path.join(ROOT, "extension", "handlers")
BASE_FILE = os.path.join(ROOT, "extension", "content_base.js")
OUTPUT_PATHS = [
    os.path.join(ROOT, "extension", "content.js"),
    os.path.join(ROOT, "dist", "desktop", "extension", "content.js"),
]

def main():
    with open(BASE_FILE, encoding="utf-8") as f:
        content = f.read()

    # Load enabled handlers (*.js only, skip *.curated_removed)
    handler_files = sorted(glob.glob(os.path.join(HANDLERS_DIR, "*.js")))
    handler_code = ""
    for fp in handler_files:
        name = os.path.splitext(os.path.basename(fp))[0]
        with open(fp, encoding="utf-8") as f:
            handler_code += f"\\n  // ── {name} ──\\n"
            handler_code += f.read() + "\\n"

    # Insert handlers before the Message listener section
    marker = "  // ─── Message listener"
    if marker in content:
        content = content.replace(marker, handler_code + "\\n" + marker)
    else:
        content += "\\n" + handler_code

    for out_path in OUTPUT_PATHS:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {out_path} ({len(content)} bytes)")

if __name__ == "__main__":
    main()
'''
    with open(BUILD_SCRIPT, "w", encoding="utf-8") as f:
        f.write(build_script)

    print(f"Split complete:")
    print(f"  Handlers dir: {HANDLERS_DIR}")
    print(f"  Base file:    {BASE_FILE}")
    print(f"  Curated:      {curated_count}")
    print(f"  Cut:          {cut_count}")
    print(f"  Total:        {curated_count + cut_count}")
    print()
    print(f"Next: python scripts/build_content_js.py")


if __name__ == "__main__":
    main()
