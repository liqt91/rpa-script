"""
Complete extension build — copies static files to dist, then builds JS bundles.
Run this instead of individually running build_background_js.py and build_content_js.py.
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "extension")
DST_DIR = os.path.join(ROOT, "dist", "desktop", "extension")

# Files/dirs to EXCLUDE from copy (source-only, not runtime)
EXCLUDE = {
    "background_base.js",
    "content_base.js",
    "dom_handlers",
    "dom_handlers_new",
    "dom_shared",
    "background_handlers",
    "_load_all.js",
}

def main():
    os.makedirs(DST_DIR, exist_ok=True)

    # Step 1: Copy all static files (manifest, icons, html, sidepanel.js, etc.)
    copied = 0
    for item in os.listdir(SRC_DIR):
        if item in EXCLUDE:
            continue
        src = os.path.join(SRC_DIR, item)
        dst = os.path.join(DST_DIR, item)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"  COPY dir  {item}/ → dist")
        else:
            shutil.copy2(src, dst)
            print(f"  COPY file {item} → dist")
        copied += 1
    print(f"Static files: {copied} copied")

    # Step 2: Build JS bundles
    for script in ["generate_commands.py", "build_background_js.py", "build_content_js.py"]:
        script_path = os.path.join(ROOT, "scripts", script)
        print(f"\n--- {script} ---")
        subprocess.run([sys.executable, script_path], check=True)

    print("\nOK - Extension build complete: " + DST_DIR)


if __name__ == "__main__":
    main()
