import requests
import re
import os
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
import threading


def update_status(text, fg="blue"):
    venster.after(0, lambda: status_label.config(text=text, fg=fg))


def show_ui_message(kind, title, message):
    def _show():
        if kind == "error":
            messagebox.showerror(title, message, parent=venster)
        elif kind == "warning":
            messagebox.showwarning(title, message, parent=venster)
        elif kind == "info":
            messagebox.showinfo(title, message, parent=venster)
    venster.after(0, _show)


def set_download_state(enabled):
    state = "normal" if enabled else "disabled"
    venster.after(0, lambda: download_knop.config(state=state))


def clear_input():
    venster.after(0, lambda: invoerveld.delete(0, tk.END))


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

def download_track(track_url, client_id, savemap):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    update_status("Gegevens ophalen...", "blue")

    resolve_url = f"https://api-v2.soundcloud.com/resolve?url={track_url}&client_id={client_id}"
    response = requests.get(resolve_url, headers=headers)

    if response.status_code != 200:
        show_ui_message("error", "Fout", "Kan de track niet vinden.")
        update_status("")
        set_download_state(True)
        return

    track_info = response.json()
    title = track_info.get('title', 'onbekende_track')
    print(f"Nummer gevonden: {title}")

    stream_url = None
    for transcoding in track_info.get('media', {}).get('transcodings', []):
        if transcoding.get('format', {}).get('protocol') == 'progressive':
            stream_url = transcoding.get('url')
            break

    if not stream_url:
        show_ui_message("error", "Fout", "Kan geen MP3 vinden voor dit liedje.")
        update_status("")
        set_download_state(True)
        return

    update_status("Downloadlink genereren...", "blue")
    stream_url_with_auth = f"{stream_url}?client_id={client_id}"
    media_response = requests.get(stream_url_with_auth, headers=headers).json()
    download_url = media_response.get('url')

    update_status("Audiobestand downloaden (dit kan even duren)...", "blue")
    audio_data = requests.get(download_url, headers=headers).content

    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "track"
    filename = f"{safe_title}.mp3"
    full_path = os.path.join(savemap, filename)

    with open(full_path, 'wb') as file:
        file.write(audio_data)

    update_status("Download succesvol afgerond!", "green")
    clear_input()
    show_ui_message("info", "Succes", f"'{title}' is succesvol opgeslagen!")
    set_download_state(True)


def start_download():
    url = invoerveld.get().strip()

    if not url:
        messagebox.showwarning("Oeps!", "Voer eerst een geldige SoundCloud URL in.", parent=venster)
        return

    savemap = filedialog.askdirectory(parent=venster, title="Kies een map om het bestand in op te slaan")
    if not savemap:
        return

    set_download_state(False)
    update_status("Starten met downloaden...", "blue")

    download_thread = threading.Thread(
        target=download_track,
        args=(url, applicatie_client_id, savemap),
        daemon=True
    )
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

        download_knop = tk.Button(venster, text="Download MP3", command=start_download)
        download_knop.pack(pady=20)

        status_label = tk.Label(venster, text="", fg="blue")
        status_label.pack(pady=5)

        venster.mainloop()