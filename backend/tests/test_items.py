def test_item_crud(client):
    res = client.post("/api/v1/items", json={"name": "pen", "description": "blue"})
    assert res.status_code == 201
    item_id = res.json()["id"]

    assert client.get(f"/api/v1/items/{item_id}").json()["name"] == "pen"
    assert [i["id"] for i in client.get("/api/v1/items").json()] == [item_id]

    body = client.patch(f"/api/v1/items/{item_id}", json={"name": "pencil"}).json()
    assert (body["name"], body["description"]) == ("pencil", "blue")

    assert client.delete(f"/api/v1/items/{item_id}").status_code == 204
    res = client.get(f"/api/v1/items/{item_id}")
    assert res.status_code == 404
    assert res.json()["code"] == "not_found"


def test_validation_error_hides_input(client):
    secret = "s3cret-" + "x" * 200  # max_length 초과로 422 유도
    res = client.post("/api/v1/items", json={"name": secret})
    assert res.status_code == 422
    assert res.json()["code"] == "validation_failed"
    assert secret not in res.text
