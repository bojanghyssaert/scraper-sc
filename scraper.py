import requests
import re
import os
import tkinter as tk
from tkinter import filedialog
import threading


def choose_save_map():
    root = tk.Tk()
    root.withdraw()

    root.attributes('-topmost', True)

    map_path = filedialog.askdirectory(title="choose a map to save the file in")
    return map_path


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

def download_track(track_url, client_id):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    resolve_url = f"https://api-v2.soundcloud.com/resolve?url={track_url}&client_id={client_id}"

    response = requests.get(resolve_url, headers=headers)

    if response.status_code != 200:
        print("kan de track niet vinden")
        return

    track_info = response.json()
    title = track_info.get('title', 'onbekende_track')
    print(f"nummer gevonden {title}")

    stream_url = None
    for transcoding in track_info.get('media', {}).get('transcodings', []):
        if transcoding.get('format', {}).get('protocol') == 'progressive':
            stream_url = transcoding.get('url')
            break

    if not stream_url:
        print("geen sample gevonden")
        return


    print("downloadlink genereren...")
    stream_url_with_auth = f"{stream_url}?client_id={client_id}"
    media_response = requests.get(stream_url_with_auth, headers=headers).json()
    download_url = media_response.get('url')

    print("Audiobestand downloaden (dit kan even duren)...")
    audio_data = requests.get(download_url, headers=headers).content

    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    filename = f"{safe_title}.mp3"

    print("\nSelecteer de opslagmap ")
    savemap = choose_save_map()

    if not savemap:
        print("Download geannuleerd: geen map geselecteerd")
        return

    full_path = os.path.join(savemap, filename)

    with open(full_path, 'wb') as file:
        file.write(audio_data)

    print(f"klaar, opgeslagen als {full_path}")



def start_download():
    url = invoerveld.get()

    if not url:
        print("voer eerst een URL in.")
        return

    print(f"starten met downloaden van: {url}")

    download_thread = threading.Thread(target=download_track, args=(url, applicatie_client_id))
    download_thread.start()



if __name__ == "__main__":
    applicatie_client_id = get_client_id()

    if not applicatie_client_id:
        print("kon geen client id ophalen, het programma stopt")

    else:
        print(f"client id succesvol gevonden: {applicatie_client_id}")

        venster = tk.Tk()
        venster.title("SoundCloud to mp3")
        venster.geometry("450x200")

        uitleg_label = tk.Label(venster, text="Plak hier je SoundCloud link: ")
        uitleg_label.pack(pady=10)

        invoerveld = tk.Entry(venster, width=50)
        invoerveld.pack(pady=5)

        download_knop = tk.Button(venster, text="Dowload MP3", command=start_download)
        download_knop.pack(pady=20)

        venster.mainloop()