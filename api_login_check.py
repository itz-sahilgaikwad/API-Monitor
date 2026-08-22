import urllib.request
import urllib.error
import json
import sys
import socket


try:
    print("Sending POST request to /api/users/login/...")

    payload = json.dumps({
        "identifier": "sahilpgaikwad0407@gmail.com",
        "password": "somepassword"
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/users/login/",
        data=payload,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=10) as response:
        print(f"Status Code: {response.getcode()}")
        print(f"Response: {response.read().decode('utf-8')}")
        sys.exit(0)

except urllib.error.URLError as e:
    if isinstance(e.reason, socket.timeout):
        print("ERROR: Request timed out. Backend is hung.")
    else:
        print(f"ERROR URLError: {e.reason}")

    sys.exit(1)

except urllib.error.HTTPError as e:
    print(f"HTTPError: {e.code}")
    print(e.read().decode("utf-8"))
    sys.exit(0)

except socket.timeout:
    print("ERROR: Timeout. Backend is hung.")
    sys.exit(1)

except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)