import requests
import re

def get_client_id():

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    response = requests.get("https://soundcloud.com", headers=headers)

    script__urls = re.findall(r'<script crossorigin src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"></script>', response.text)

    if not script__urls:
        print("niets gevonden")
        return None

    for url in script__urls:
        js_content = requests.get(url, headers=headers).text
        match = re.search(r'client_id:"([a-zA-Z0-9]{32})"', js_content)

        if match:
            client_id = match.group(1)
            return client_id


    return None


if __name__ == "__main__":
    client_id = get_client_id()
    if client_id:
        print(f"succesvol gevonden: {client_id}")
    else:
        print("script is gefaald")

