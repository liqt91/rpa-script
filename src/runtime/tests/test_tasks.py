"""Tasks router: create / pending atomic claim / status update."""


def _create(client, headers, **overrides):
    body = {"job_type": "hello_world", "urls": ["https://x.com"]}
    body.update(overrides)
    return client.post("/api/tasks", json=body, headers=headers)


def test_create_multiple(client, auth_headers):
    r = _create(
        client, auth_headers,
        urls=["https://a.com", "https://b.com"],
        params={"name": "open_source"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["count"] == 2
    assert len(body["ids"]) == 2


def test_params_round_trip(client, auth_headers):
    r = _create(client, auth_headers, urls=["https://a.com"],
                params={"name": "round_trip"})
    tid = r.json()["ids"][0]

    pending = client.get(
        "/api/tasks/pending", params={"client_id": "c1"}, headers=auth_headers,
    ).json()["tasks"]

    matched = next(t for t in pending if t["id"] == tid)
    assert matched["params"] == {"name": "round_trip"}


def test_pending_atomic_claim(client, auth_headers):
    _create(client, auth_headers, urls=["u1", "u2"])
    first = client.get(
        "/api/tasks/pending", params={"client_id": "c1"}, headers=auth_headers,
    ).json()["tasks"]
    assert len(first) == 2

    # Second call: tasks were flipped to running, so nothing pending.
    second = client.get(
        "/api/tasks/pending", params={"client_id": "c1"}, headers=auth_headers,
    ).json()["tasks"]
    assert second == []


def test_pending_assignment_filter(client, auth_headers):
    _create(client, auth_headers, urls=["u_a"], client_id="client_a")
    _create(client, auth_headers, urls=["u_open"])  # client_id=None → anyone
    _create(client, auth_headers, urls=["u_b"], client_id="client_b")

    r = client.get(
        "/api/tasks/pending", params={"client_id": "client_a"},
        headers=auth_headers,
    )
    urls = {t["url"] for t in r.json()["tasks"]}
    assert "u_a" in urls
    assert "u_open" in urls
    assert "u_b" not in urls


def test_update_status(client, auth_headers):
    tid = _create(client, auth_headers).json()["ids"][0]
    r = client.put(
        f"/api/tasks/{tid}/status",
        params={"status": "failed"},
        headers=auth_headers,
    )
    assert r.status_code == 200


def test_update_status_404(client, auth_headers):
    r = client.put(
        "/api/tasks/999999/status",
        params={"status": "failed"},
        headers=auth_headers,
    )
    assert r.status_code == 404
