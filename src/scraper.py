import requests
import re
import os
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
import threading

# Kleurenpalet (Moderne SoundCloud-stijl)
BG_COLOR = "#181818"
CARD_BG = "#242424"
INPUT_BG = "#2D2D2D"
TEXT_COLOR = "#F5F5F5"
TEXT_MUTED = "#A0A0A0"
ACCENT_COLOR = "#FF5500"
ACCENT_HOVER = "#FF6A22"
BTN_SECONDARY = "#333333"
BTN_SECONDARY_HOVER = "#444444"
STATUS_INFO = "#FF5500"
STATUS_SUCCESS = "#00E676"
STATUS_ERROR = "#FF5252"


def update_status(text, fg=STATUS_INFO):
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
    def _update():
        if enabled:
            download_knop.config(state="normal", bg=ACCENT_COLOR, cursor="hand2")
            plak_knop.config(state="normal", cursor="hand2")
        else:
            download_knop.config(state="disabled", bg="#555555", cursor="watch")
            plak_knop.config(state="disabled", cursor="watch")
    venster.after(0, _update)


def clear_input():
    venster.after(0, lambda: invoerveld.delete(0, tk.END))


def paste_from_clipboard():
    try:
        content = venster.clipboard_get().strip()
        invoerveld.delete(0, tk.END)
        invoerveld.insert(0, content)
    except tk.TclError:
        pass


def update_track_preview(title, artist):
    def _update():
        preview_title_val.config(text=title)
        preview_artist_val.config(text=artist)
    venster.after(0, _update)


def reset_track_preview():
    def _reset():
        preview_title_val.config(text="Nog geen nummer geladen")
        preview_artist_val.config(text="-")
    venster.after(0, _reset)


def update_progress(percent, text=""):
    def _update():
        progress_bar["value"] = percent
        if text:
            progress_detail_label.config(text=text)
    venster.after(0, _update)


def reset_progress():
    def _reset():
        progress_bar["value"] = 0
        progress_detail_label.config(text="Wachten op download...")
    venster.after(0, _reset)


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

    update_status("Gegevens ophalen...", STATUS_INFO)

    resolve_url = f"https://api-v2.soundcloud.com/resolve?url={track_url}&client_id={client_id}"
    try:
        response = requests.get(resolve_url, headers=headers, timeout=10)
    except requests.RequestException as e:
        show_ui_message("error", "Netwerkfout", f"Kan geen verbinding maken met SoundCloud:\n{e}")
        update_status("Netwerkfout", STATUS_ERROR)
        set_download_state(True)
        return

    if response.status_code != 200:
        show_ui_message("error", "Fout", "Kan de track niet vinden of de link is ongeldig.")
        update_status("Track niet gevonden", STATUS_ERROR)
        update_track_preview("Niet gevonden", "-")
        set_download_state(True)
        return

    try:
        track_info = response.json()
    except ValueError:
        show_ui_message("error", "Fout", "Ongeldig antwoord ontvangen van SoundCloud.")
        update_status("Fout bij verwerken van data", STATUS_ERROR)
        set_download_state(True)
        return

    title = track_info.get('title', 'Onbekende titel')
    artist = (
        track_info.get('user', {}).get('username')
        or track_info.get('publisher_metadata', {}).get('artist')
        or "Onbekende artiest"
    )
    print(f"Nummer gevonden: {title} van {artist}")

    # Direct tonen in de interface vóórdat het downloaden begint
    update_track_preview(title, artist)

    stream_url = None
    for transcoding in track_info.get('media', {}).get('transcodings', []):
        if transcoding.get('format', {}).get('protocol') == 'progressive':
            stream_url = transcoding.get('url')
            break

    if not stream_url:
        show_ui_message("error", "Fout", "Kan geen MP3 vinden voor dit liedje.")
        update_status("Geen MP3 beschikbaar", STATUS_ERROR)
        set_download_state(True)
        return

    update_status("Downloadlink genereren...", STATUS_INFO)
    stream_url_with_auth = f"{stream_url}?client_id={client_id}"
    try:
        media_response = requests.get(stream_url_with_auth, headers=headers, timeout=10)
        if media_response.status_code != 200:
            show_ui_message("error", "Fout", "Kon downloadlink niet ophalen van SoundCloud.")
            update_status("Fout bij downloadlink", STATUS_ERROR)
            set_download_state(True)
            return
        download_url = media_response.json().get('url')
        if not download_url:
            show_ui_message("error", "Fout", "Geen geldige downloadlocatie gevonden in SoundCloud antwoord.")
            update_status("Geen downloadlocatie", STATUS_ERROR)
            set_download_state(True)
            return
    except (requests.RequestException, ValueError) as e:
        show_ui_message("error", "Netwerkfout", f"Fout bij ophalen downloadlink:\n{e}")
        update_status("Fout bij downloadlink", STATUS_ERROR)
        set_download_state(True)
        return

    update_status("Audiobestand downloaden...", STATUS_INFO)
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "track"
    filename = f"{safe_title}.mp3"
    full_path = os.path.join(savemap, filename)

    try:
        with requests.get(download_url, headers=headers, stream=True, timeout=10) as audio_response:
            if audio_response.status_code != 200:
                show_ui_message("error", "Fout", f"Download mislukt met statuscode {audio_response.status_code}.")
                update_status("Download mislukt", STATUS_ERROR)
                set_download_state(True)
                return

            content_length = audio_response.headers.get('content-length')
            total_size = int(content_length) if content_length and content_length.isdigit() else 0
            downloaded = 0

            with open(full_path, 'wb') as file:
                for chunk in audio_response.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        file.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = min(100.0, (downloaded / total_size) * 100)
                            mb_done = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            update_progress(percent, f"{mb_done:.1f} MB / {mb_total:.1f} MB ({int(percent)}%)")
                        else:
                            mb_done = downloaded / (1024 * 1024)
                            update_progress(0, f"{mb_done:.1f} MB gedownload...")

            if total_size > 0:
                update_progress(100.0, f"{total_size / (1024 * 1024):.1f} MB / {total_size / (1024 * 1024):.1f} MB (100%)")
    except requests.RequestException as e:
        show_ui_message("error", "Netwerkfout", f"Fout tijdens het downloaden van audio:\n{e}")
        update_status("Download mislukt", STATUS_ERROR)
        set_download_state(True)
        return
    except OSError as e:
        show_ui_message("error", "Bestandsfout", f"Kon het bestand niet opslaan:\n{e}")
        update_status("Fout bij opslaan", STATUS_ERROR)
        set_download_state(True)
        return

    update_status("Download succesvol afgerond!", STATUS_SUCCESS)
    clear_input()
    show_ui_message("info", "Succes", f"'{title}' van {artist} is succesvol opgeslagen!")
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
    reset_progress()
    update_track_preview("Laden...", "Laden...")
    update_status("Starten met downloaden...", STATUS_INFO)

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
        venster.title("SoundCloud Downloader")
        venster.geometry("600x520")
        venster.minsize(560, 480)
        venster.configure(bg=BG_COLOR)

        # Style voor ttk widgets (zoals de voortgangsbalk)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "SoundCloud.Horizontal.TProgressbar",
            troughcolor=INPUT_BG,
            background=ACCENT_COLOR,
            darkcolor=ACCENT_COLOR,
            lightcolor=ACCENT_HOVER,
            bordercolor=CARD_BG,
            thickness=10
        )

        # Header sectie
        header_frame = tk.Frame(venster, bg=BG_COLOR)
        header_frame.pack(fill="x", padx=30, pady=(25, 12))

        titel_label = tk.Label(
            header_frame,
            text="🎵 SoundCloud Downloader",
            font=("Segoe UI", 16, "bold"),
            fg=TEXT_COLOR,
            bg=BG_COLOR
        )
        titel_label.pack(anchor="w")

        subtitel_label = tk.Label(
            header_frame,
            text="Plak een SoundCloud link om de track direct als MP3 te downloaden",
            font=("Segoe UI", 9),
            fg=TEXT_MUTED,
            bg=BG_COLOR
        )
        subtitel_label.pack(anchor="w", pady=(3, 0))

        # Invoerkaart
        card_frame = tk.Frame(venster, bg=CARD_BG, padx=20, pady=16, relief="flat")
        card_frame.pack(fill="x", padx=30, pady=(0, 10))

        invoer_label = tk.Label(
            card_frame,
            text="SoundCloud Track URL",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT_COLOR,
            bg=CARD_BG
        )
        invoer_label.pack(anchor="w", pady=(0, 8))

        invoer_rij = tk.Frame(card_frame, bg=CARD_BG)
        invoer_rij.pack(fill="x")

        invoerveld = tk.Entry(
            invoer_rij,
            font=("Segoe UI", 10),
            bg=INPUT_BG,
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#3D3D3D",
            highlightcolor=ACCENT_COLOR
        )
        invoerveld.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        plak_knop = tk.Button(
            invoer_rij,
            text="📋 Plakken",
            font=("Segoe UI", 9, "bold"),
            bg=BTN_SECONDARY,
            fg=TEXT_COLOR,
            activebackground=BTN_SECONDARY_HOVER,
            activeforeground=TEXT_COLOR,
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=4,
            command=paste_from_clipboard
        )
        plak_knop.pack(side="right")

        plak_knop.bind("<Enter>", lambda e: plak_knop.config(bg=BTN_SECONDARY_HOVER))
        plak_knop.bind("<Leave>", lambda e: plak_knop.config(bg=BTN_SECONDARY))

        # Track Preview Kaart
        preview_frame = tk.Frame(venster, bg=CARD_BG, padx=20, pady=12, relief="flat")
        preview_frame.pack(fill="x", padx=30, pady=(0, 10))

        preview_header = tk.Label(
            preview_frame,
            text="TRACK PREVIEW",
            font=("Segoe UI", 8, "bold"),
            fg=ACCENT_COLOR,
            bg=CARD_BG
        )
        preview_header.pack(anchor="w", pady=(0, 4))

        preview_title_row = tk.Frame(preview_frame, bg=CARD_BG)
        preview_title_row.pack(fill="x", pady=1)
        tk.Label(
            preview_title_row,
            text="Titel:",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_MUTED,
            bg=CARD_BG,
            width=8,
            anchor="w"
        ).pack(side="left")
        preview_title_val = tk.Label(
            preview_title_row,
            text="Nog geen nummer geladen",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_COLOR,
            bg=CARD_BG,
            anchor="w"
        )
        preview_title_val.pack(side="left", fill="x", expand=True)

        preview_artist_row = tk.Frame(preview_frame, bg=CARD_BG)
        preview_artist_row.pack(fill="x", pady=1)
        tk.Label(
            preview_artist_row,
            text="Artiest:",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_MUTED,
            bg=CARD_BG,
            width=8,
            anchor="w"
        ).pack(side="left")
        preview_artist_val = tk.Label(
            preview_artist_row,
            text="-",
            font=("Segoe UI", 9),
            fg=TEXT_COLOR,
            bg=CARD_BG,
            anchor="w"
        )
        preview_artist_val.pack(side="left", fill="x", expand=True)

        # Voortgangskaart
        progress_frame = tk.Frame(venster, bg=CARD_BG, padx=20, pady=12, relief="flat")
        progress_frame.pack(fill="x", padx=30, pady=(0, 10))

        progress_header_row = tk.Frame(progress_frame, bg=CARD_BG)
        progress_header_row.pack(fill="x", pady=(0, 6))

        tk.Label(
            progress_header_row,
            text="VOORTGANG",
            font=("Segoe UI", 8, "bold"),
            fg=ACCENT_COLOR,
            bg=CARD_BG
        ).pack(side="left")

        progress_detail_label = tk.Label(
            progress_header_row,
            text="Wachten op download...",
            font=("Segoe UI", 8),
            fg=TEXT_MUTED,
            bg=CARD_BG
        )
        progress_detail_label.pack(side="right")

        progress_bar = ttk.Progressbar(
            progress_frame,
            style="SoundCloud.Horizontal.TProgressbar",
            orient="horizontal",
            mode="determinate"
        )
        progress_bar.pack(fill="x")

        # Actieknoppen & Status sectie
        actie_frame = tk.Frame(venster, bg=BG_COLOR)
        actie_frame.pack(fill="x", padx=30, pady=(5, 15))

        download_knop = tk.Button(
            actie_frame,
            text="Download MP3",
            font=("Segoe UI", 11, "bold"),
            bg=ACCENT_COLOR,
            fg="#FFFFFF",
            activebackground="#E04A00",
            activeforeground="#FFFFFF",
            relief="flat",
            cursor="hand2",
            pady=8,
            command=start_download
        )
        download_knop.pack(fill="x")

        def on_download_hover(e):
            if download_knop["state"] == "normal":
                download_knop.config(bg=ACCENT_HOVER)

        def on_download_leave(e):
            if download_knop["state"] == "normal":
                download_knop.config(bg=ACCENT_COLOR)

        download_knop.bind("<Enter>", on_download_hover)
        download_knop.bind("<Leave>", on_download_leave)

        status_label = tk.Label(
            actie_frame,
            text="",
            font=("Segoe UI", 9),
            bg=BG_COLOR,
            fg=STATUS_INFO
        )
        status_label.pack(pady=(12, 0))

        venster.mainloop()