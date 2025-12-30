import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import tkinter as tk
from tkinter import messagebox
import threading
import queue
import re
import requests
from pathlib import Path
import os, platform, subprocess
import httpx
import asyncio
from bs4 import BeautifulSoup
import json

# ---------------------------
# Utility: Open a file with the system default application
# ---------------------------
def open_file(file_path):
    try:
        if platform.system() == "Windows":
            os.startfile(file_path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", file_path])
        else:
            subprocess.call(["xdg-open", file_path])
    except Exception as e:
        print(f"Error opening file: {e}")
        
async def download_tab_meta(url, log_queue):
    """Utility: get source_url and songId from tab page"""
    log_queue.put(f"Downloading Songsterr tab: {url.strip()}\n")
    async with httpx.AsyncClient() as client:
        tab = await client.get(url.strip())
    if tab.status_code != 200:
        log_queue.put(f"Error downloading Songsterr tab: {tab.status_code} - {tab.reason_phrase}\n")
        return (None, None)
    log_queue.put(f"Parsing Songsterr tab\n")
    soup = BeautifulSoup(tab.text, "html.parser")
    log_queue.put(f"Extracting Songsterr tab metadata\n")
    tag = soup.find(id="state")
    if len(tag) == 0:
        log_queue.put(f"Error: no metadata found in Songsterr tab\n")
        return (None, None)
    state = json.loads(tag.contents[0])
    if "meta" in state and "current" in state["meta"] and "source" in state["meta"]["current"]:
        source_url = state["meta"]["current"]["source"]
    else:
        source_url = None
    if "meta" in state and "songId" in state["meta"]:
        song_id = state["meta"]["songId"]
    else:
        song_id = None
    return (source_url, song_id)

# ---------------------------
# Tab 1: Songsterr Downloader
# ---------------------------
def download_songsterr_gui(songsterr_link, download_dir, log_queue):
    (source_url, song_id) = asyncio.run(download_tab_meta(songsterr_link, log_queue))
    
    if (source_url, song_id) == (None, None):
        return

    if source_url ==  None:
        log_queue.put(f"No 'source' found in the tab page for song ID {song_id}\n")
        return

    download_dir_path = Path(download_dir).expanduser()
    download_dir_path.mkdir(parents=True, exist_ok=True)
    extension = source_url.rsplit('.', 1)[-1]
    gp_filename = download_dir_path / f"Song_{song_id}.{extension}"
    log_queue.put(f"Found tab for Songsterr ID {song_id} — saving as {gp_filename}\n")

    try:
        file_resp = requests.get(source_url, stream=True)
    except Exception as e:
        log_queue.put(f"Error downloading file from {source_url}: {e}\n")
        return

    if file_resp.status_code != 200:
        log_queue.put(f"Failed to download {source_url}, status code {file_resp.status_code}\n")
        return

    total_size = int(file_resp.headers.get('content-length', 0))
    downloaded = 0
    chunk_size = 4096
    with open(gp_filename, 'wb') as f:
        for chunk in file_resp.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size:
                    progress = (downloaded / total_size) * 100
                    log_queue.put(f"Downloading... {progress:.1f}% complete\n")
    log_queue.put(f"Download complete: {gp_filename}\n")

# ---------------------------
# Tab 2: Drum MIDI Downloader
# ---------------------------
def download_drum_midi(songsterr_link, download_dir, log_queue):
    # Download the Guitar Pro file (same as in Tab 1)
    (source_url, song_id) = asyncio.run(download_tab_meta(songsterr_link, log_queue))
    
    if (source_url, song_id) == (None, None):
        return

    if source_url ==  None:
        log_queue.put(f"No 'source' found in the tab page for song ID {song_id}\n")
        return

    download_dir_path = Path(download_dir).expanduser()
    download_dir_path.mkdir(parents=True, exist_ok=True)
    extension = source_url.rsplit('.', 1)[-1]
    gp_filename = download_dir_path / f"Song_{song_id}.{extension}"
    log_queue.put(f"Found tab for Songsterr ID {song_id} — saving as {gp_filename}\n")

    try:
        file_resp = requests.get(source_url, stream=True)
    except Exception as e:
        log_queue.put(f"Error downloading file from {source_url}: {e}\n")
        return

    if file_resp.status_code != 200:
        log_queue.put(f"Failed to download {source_url}, status code {file_resp.status_code}\n")
        return

    total_size = int(file_resp.headers.get('content-length', 0))
    downloaded = 0
    chunk_size = 4096
    with open(gp_filename, 'wb') as f:
        for chunk in file_resp.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size:
                    progress = (downloaded / total_size) * 100
                    log_queue.put(f"Downloading... {progress:.1f}% complete\n")
    log_queue.put(f"Download complete: {gp_filename}\n")

    try:
        import guitarpro
    except ImportError:
        log_queue.put("pyguitarpro library is not installed. Please install it to extract drum tracks.\n")
        return

    try:
        song = guitarpro.parse(str(gp_filename))
    except Exception as e:
        log_queue.put(f"Error parsing Guitar Pro file: {e}\n")
        log_queue.put("The downloaded file may be in an unsupported format. Please check for updates or try a different revision.\n")
        return

    drum_track = None
    for track in song.tracks:
        if (track.name and "drum" in track.name.lower()) or (hasattr(track, 'channel') and track.channel == 10):
            drum_track = track
            break
    if not drum_track:
        log_queue.put("No drum track found in the downloaded file.\n")
        return
    log_queue.put(f"Drum track found: {drum_track.name}\n")

    try:
        import mido
    except ImportError:
        log_queue.put("mido library is not installed. Please install it to convert drum track to MIDI.\n")
        return

    midi_output_path = download_dir_path / f"Song_{song_id}_drum.mid"
    log_queue.put(f"Converting drum track to MIDI: {midi_output_path}\n")

    mid = mido.MidiFile()
    midi_track = mido.MidiTrack()
    mid.tracks.append(midi_track)

    for measure in drum_track.measures:
        for voice in measure.voices:
            for beat in voice.beats:
                for note in beat.notes:
                    midi_track.append(mido.Message('note_on', channel=9, note=note.value, velocity=64, time=0))
                    midi_track.append(mido.Message('note_off', channel=9, note=note.value, velocity=0, time=480))
    try:
        mid.save(str(midi_output_path))
    except Exception as e:
        log_queue.put(f"Error saving MIDI file: {e}\n")
        return

    log_queue.put(f"Drum MIDI conversion complete: {midi_output_path}\n")

def start_songsterr_download(url, log_queue):
    download_dir = "~/Tabs"
    download_songsterr_gui(url, download_dir, log_queue)

def start_drum_midi_download(url, log_queue):
    download_dir = "~/Tabs"
    download_drum_midi(url, download_dir, log_queue)

def get_downloaded_files(download_dir):
    download_dir_path = Path(download_dir).expanduser()
    download_dir_path.mkdir(parents=True, exist_ok=True)
    files = list(download_dir_path.glob("*"))
    return [str(f) for f in files if f.is_file()]

def main():
    log_queue_songsterr = queue.Queue()
    log_queue_drum = queue.Queue()

    root = ttk.Window(themename="darkly")
    root.title("TabRiPP")
    root.geometry("1500x1200")


    try:
        icon = tk.PhotoImage(file="images/logo.png")
        root.iconphoto(False, icon)
    except Exception as e:
        print(f"Icon load failed: {e}")


    style = ttk.Style()
    style.configure("TButton", font=("Helvetica", 12, "bold"))

    
    notebook = ttk.Notebook(root)
    notebook.pack(expand=TRUE, fill='both', padx=20, pady=20)


    tab1 = ttk.Frame(notebook)
    notebook.add(tab1, text="Songsterr Downloader")
    lbl_url1 = ttk.Label(tab1, text="Enter Song URL or ID:", font=("Helvetica", 14))
    lbl_url1.pack(pady=10)
    entry_url1 = ttk.Entry(tab1, width=50, font=("Helvetica", 14))
    entry_url1.pack(pady=10)
    btn_download1 = ttk.Button(tab1, text="Download Tab", bootstyle="danger",
                               command=lambda: threading.Thread(
                                   target=start_songsterr_download,
                                   args=(entry_url1.get().strip(), log_queue_songsterr),
                                   daemon=True).start())
    btn_download1.pack(pady=10)
    text_widget1 = tk.Text(tab1, height=15, width=80, bg="#1a1a1a", fg="#ff4d4d",
                             insertbackground="#ff4d4d", font=("Consolas", 12))
    text_widget1.pack(pady=10)

    tab2 = ttk.Frame(notebook)
    notebook.add(tab2, text="Drum MIDI Downloader")
    lbl_url2 = ttk.Label(tab2, text="Enter Song URL or ID:", font=("Helvetica", 14))
    lbl_url2.pack(pady=10)
    entry_url2 = ttk.Entry(tab2, width=50, font=("Helvetica", 14))
    entry_url2.pack(pady=10)
    btn_download2 = ttk.Button(tab2, text="Download Drum MIDI", bootstyle="danger",
                               command=lambda: threading.Thread(
                                   target=start_drum_midi_download,
                                   args=(entry_url2.get().strip(), log_queue_drum),
                                   daemon=True).start())
    btn_download2.pack(pady=10)
    text_widget2 = tk.Text(tab2, height=15, width=80, bg="#1a1a1a", fg="#ff4d4d",
                             insertbackground="#ff4d4d", font=("Consolas", 12))
    text_widget2.pack(pady=10)

    tab3 = ttk.Frame(notebook)
    notebook.add(tab3, text="Audio-to-Tab AI")
    lbl_audio = ttk.Label(tab3, text="Audio-to-Tab AI Feature", font=("Helvetica", 16, "bold"))
    lbl_audio.pack(pady=20)
    lbl_info = ttk.Label(tab3, text="This feature is coming soon!", font=("Helvetica", 14))
    lbl_info.pack(pady=10)
    btn_audio = ttk.Button(tab3, text="Process Audio", bootstyle="outline-danger",
                           state=DISABLED,
                           command=lambda: messagebox.showinfo("Coming Soon", "Audio-to-Tab AI feature is coming soon!"))
    btn_audio.pack(pady=10)

    tab4 = ttk.Frame(notebook)
    notebook.add(tab4, text="GPro Preview Player")
    lbl_file = ttk.Label(tab4, text="Downloaded Files:", font=("Helvetica", 14))
    lbl_file.pack(pady=10)
    listbox_files = tk.Listbox(tab4, width=80, height=15, font=("Helvetica", 12))
    listbox_files.pack(pady=10)
    btn_frame = ttk.Frame(tab4)
    btn_frame.pack(pady=10)
    btn_refresh = ttk.Button(btn_frame, text="Refresh List", bootstyle="primary",
                             command=lambda: refresh_file_list(listbox_files))
    btn_refresh.pack(side=LEFT, padx=10)
    btn_preview = ttk.Button(btn_frame, text="Preview", bootstyle="primary",
                             command=lambda: preview_selected_file(listbox_files))
    btn_preview.pack(side=LEFT, padx=10)

    def refresh_file_list(listbox):
        listbox.delete(0, tk.END)
        files = get_downloaded_files("~/Tabs")
        for f in files:
            listbox.insert(tk.END, f)

    def preview_selected_file(listbox):
        selection = listbox.curselection()
        if not selection:
            messagebox.showerror("Selection Error", "Please select a file to preview.")
            return
        file_path = listbox.get(selection[0])
        open_file(file_path)

    def process_queue(q, text_widget):
        try:
            while True:
                msg = q.get_nowait()
                text_widget.insert(tk.END, msg)
                text_widget.see(tk.END)
        except queue.Empty:
            pass
        root.after(100, lambda: process_queue(q, text_widget))

    process_queue(log_queue_songsterr, text_widget1)
    process_queue(log_queue_drum, text_widget2)

    root.mainloop()

if __name__ == "__main__":
    main()
