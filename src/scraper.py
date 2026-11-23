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
    try:
        response = requests.get("https://soundcloud.com", headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Fout bij openen van SoundCloud homepage: {e}")
        return None

    script__urls = re.findall(r'<script crossorigin src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"></script>', response.text)

    if not script__urls:
        print("Geen script URLs gevonden op SoundCloud homepage.")
        return None

    for url in script__urls:
        try:
            js_response = requests.get(url, headers=headers, timeout=10)
            if js_response.status_code == 200:
                match = re.search(r'client_id:"([a-zA-Z0-9]{32})"', js_response.text)
                if match:
                    return match.group(1)
        except requests.RequestException:
            continue

    return None

def download_track(track_url, client_id, savemap):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    update_status("Gegevens ophalen...", "blue")

    resolve_url = f"https://api-v2.soundcloud.com/resolve?url={track_url}&client_id={client_id}"
    try:
        response = requests.get(resolve_url, headers=headers, timeout=10)
    except requests.RequestException as e:
        show_ui_message("error", "Netwerkfout", f"Kan geen verbinding maken met SoundCloud:\n{e}")
        update_status("Netwerkfout", "red")
        set_download_state(True)
        return

    if response.status_code != 200:
        show_ui_message("error", "Fout", "Kan de track niet vinden of de link is ongeldig.")
        update_status("Track niet gevonden", "red")
        set_download_state(True)
        return

    try:
        track_info = response.json()
    except ValueError:
        show_ui_message("error", "Fout", "Ongeldig antwoord ontvangen van SoundCloud.")
        update_status("Fout bij verwerken van data", "red")
        set_download_state(True)
        return

    title = track_info.get('title', 'onbekende_track')
    print(f"Nummer gevonden: {title}")

    stream_url = None
    for transcoding in track_info.get('media', {}).get('transcodings', []):
        if transcoding.get('format', {}).get('protocol') == 'progressive':
            stream_url = transcoding.get('url')
            break

    if not stream_url:
        show_ui_message("error", "Fout", "Kan geen MP3 vinden voor dit liedje.")
        update_status("Geen MP3 beschikbaar", "red")
        set_download_state(True)
        return

    update_status("Downloadlink genereren...", "blue")
    stream_url_with_auth = f"{stream_url}?client_id={client_id}"
    try:
        media_response = requests.get(stream_url_with_auth, headers=headers, timeout=10)
        if media_response.status_code != 200:
            show_ui_message("error", "Fout", "Kon downloadlink niet ophalen van SoundCloud.")
            update_status("Fout bij downloadlink", "red")
            set_download_state(True)
            return
        download_url = media_response.json().get('url')
        if not download_url:
            show_ui_message("error", "Fout", "Geen geldige downloadlocatie gevonden in SoundCloud antwoord.")
            update_status("Geen downloadlocatie", "red")
            set_download_state(True)
            return
    except (requests.RequestException, ValueError) as e:
        show_ui_message("error", "Netwerkfout", f"Fout bij ophalen downloadlink:\n{e}")
        update_status("Fout bij downloadlink", "red")
        set_download_state(True)
        return

    update_status("Audiobestand downloaden (dit kan even duren)...", "blue")
    try:
        audio_response = requests.get(download_url, headers=headers, timeout=10)
        if audio_response.status_code != 200:
            show_ui_message("error", "Fout", f"Download mislukt met statuscode {audio_response.status_code}.")
            update_status("Download mislukt", "red")
            set_download_state(True)
            return
        audio_data = audio_response.content
    except requests.RequestException as e:
        show_ui_message("error", "Netwerkfout", f"Fout tijdens het downloaden van audio:\n{e}")
        update_status("Download mislukt", "red")
        set_download_state(True)
        return

    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "track"
    filename = f"{safe_title}.mp3"
    full_path = os.path.join(savemap, filename)

    try:
        with open(full_path, 'wb') as file:
            file.write(audio_data)
    except OSError as e:
        show_ui_message("error", "Bestandsfout", f"Kon het bestand niet opslaan:\n{e}")
        update_status("Fout bij opslaan", "red")
        set_download_state(True)
        return

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
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Fout bij opstarten",
            "Kon geen geldige client_id ophalen van SoundCloud.\nControleer je internetverbinding en probeer het opnieuw."
        )
        root.destroy()
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