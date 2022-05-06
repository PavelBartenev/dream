import requests

def test_respond():
    url = "http://0.0.0.0:8125/respond"

    text = ["/src/example.jpg", "/src/example.jpg"]

    request_data = {"text": text}

    result = requests.post(url, json=request_data).json()
    print(result)


if __name__ == "__main__":
    test_respond()
