"""
Build content.js by concatenating base utilities + enabled handler files.
Run during development to keep extension/content.js and dist/ in sync.
"""
import os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDLERS_DIR = os.path.join(ROOT, "extension", "handlers")
HANDLERS_NEW_DIR = os.path.join(ROOT, "extension", "handlers_new")
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
    handler_files += sorted(glob.glob(os.path.join(HANDLERS_NEW_DIR, "*.js")))
    handler_code = ""
    for fp in handler_files:
        name = os.path.splitext(os.path.basename(fp))[0]
        with open(fp, encoding="utf-8") as f:
            handler_code += f"\n  // ── {name} ──\n"
            handler_code += f.read() + "\n"

    # Insert handlers before the Message listener section
    marker = "  // ─── Message listener"
    if marker in content:
        content = content.replace(marker, handler_code + "\n" + marker)
    else:
        content += "\n" + handler_code

    for out_path in OUTPUT_PATHS:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {out_path} ({len(content)} bytes)")

if __name__ == "__main__":
    main()
