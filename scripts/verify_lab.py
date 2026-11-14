import json
import os
from urllib.request import Request, urlopen

from sentrix.lab import Scenario

base = "http://127.0.0.1:8000/api"
creds = {"login": "admin", "password": os.environ["DEMO_PASSWORD"]}
with urlopen(
    Request(
        base + "/auth/login",
        data=json.dumps(creds).encode(),
        headers={"Content-Type": "application/json"},
    )
) as reply:
    token = json.load(reply)["token"]
for scenario in Scenario:
    with urlopen(
        Request(
            base + f"/lab/{scenario}",
            method="POST",
            headers={"Authorization": "Bearer " + token},
        ),
        timeout=45,
    ) as reply:
        data = json.load(reply)
        assert data["passed"], (scenario, data["checks"])
        assert len(data["traffic"]) > 0
        print(f"{scenario}: {len(data['checks'])} checks")
print(f"{len(Scenario)} Sentrix Lab scenarios passed over HTTP and PostgreSQL")
