"""Scripts router: version + script listing + zip download."""

import io
import zipfile


def test_version(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    body = r.json()
    # Repo-root VERSION file is currently '0.2.3'.
    assert body["version"] == "0.2.3"
    assert body["min_python"] == "3.10"


def test_list_scripts(client):
    r = client.get("/api/scripts")
    assert r.status_code == 200
    scripts = r.json()["scripts"]
    names = [s["name"] for s in scripts]
    # Open-source example job shipped with the repo.
    assert "hello_world" in names


def test_download_zip_contains_job(client):
    r = client.get("/api/script/download")
    assert r.status_code == 200
    cd = r.headers.get("Content-Disposition", "")
    assert "attachment" in cd
    assert "scripts.zip" in cd

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    # Forward slashes are how zipfile records arcnames regardless of platform.
    assert "jobs/hello_world/main.py" in names
    assert "jobs/hello_world/job.yaml" in names
    assert "shared/chrome_utils.py" in names
    assert "shared/extraction_engine.py" in names
    # client.py / requirements.txt / VERSION 从项目根目录打包（如存在）
    # assert "client.py" in names  # 当前项目根目录无此文件
