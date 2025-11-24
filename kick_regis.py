from browser_forge_tmp import BrowserClient, Chrome119
import requests
client = BrowserClient(
    Chrome119,
    proxy="http://127.0.0.1:7890",
)

headers = Chrome119.headers.to_dict()
headers.pop("order")
headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Cookie": ""
})

resp = client.post("https://kick.com/api/v1/signup/send/email", json={"email":"hcssaw55154j@outlook.com"}, )

print(resp.status_code)


