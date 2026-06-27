import time

import requests


def get_token(nfclient):
    token = "1111111111111111111111111111111111111111111"
    nfclient.run_job(
        "fastapi", "bearer_token_store", kwargs={"token": token, "username": "pytest"}
    )
    return token


def wait_for_endpoint(nfclient, endpoint, timeout=30):
    # wait forfastapi to discover endpoints
    token = get_token(nfclient)
    start_time = time.time()
    while not time.time() - start_time > timeout:
        openapi_spec = requests.get(
            url="http://127.0.0.1:8000/openapi.json",
            headers={"Authorization": f"Bearer {token}"},
        )
        spec = openapi_spec.json()
        # pprint.pprint(list(spec["paths"].keys()))
        if not any(endpoint in k for k in spec["paths"]):
            time.sleep(1)
        else:
            break
