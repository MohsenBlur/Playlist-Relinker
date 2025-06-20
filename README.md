# Playlist-Relinker
You moved your music or audio library around and now your playlists don't work?

## Smartly remap music paths in standard and foobar2000 playlists

**Playlist Relinker** is a small, cross-platform Python GUI that rescans your `.m3u`, `.m3u8`, or Foobar2000 `.fplite` playlists, groups the tracks by their drive/folder “root,” and lets you change those roots once—no regex wrangling or text editors required.

* Designed around Foobar2000 conventions, yet completely agnostic: it happily fixes any plain-text playlist.
* Handles bulk drive-letter moves, merged or renamed top-level music folders, and even mass drive-letter swaps across hundreds of playlists in seconds—always keeping a backup of the original.

### Just run the .py file, scan, select, edit.



![A screenshot of PlaylistRelinker](screenshot.jpg)
<br><br><br><br><br><br>
# Total beginner guide:
 
## 1-Minute Fix-Your-Playlists Guide (Windows)

1. **Check Python**
   \*Press *`Win + R` → type `cmd` → `python --version`.*
   • If a version appears, skip the next bullet.
   • **No Python?** Install from [https://python.org](https://www.python.org/downloads/), tick **“Add Python to PATH.”**

---

2. **Get the tool**
   *Download* `foobar_playlist_path_adjuster.py` and drop it **anywhere you like** (Desktop, Documents—location doesn’t matter).

---

3. **Run it**
   Double-click the file.
   *(If Windows asks, open with “Python”).*

---

4. **Scan**
   • **Browse…** to the folder that holds your playlists.
   • Keep **Include subfolders** checked.
   • Click **Scan**.

---

5. **Repair one playlist**
   • Double-click a playlist (it turns blue).
   • For each row, change only the part that moved (e.g. `S:\Music` → `D:\Audio`).
   • Live preview shows **before** / **after** on two lines.
   • Click **Save playlist** (a backup copy is auto-made).

---

6. **Fix drive letters in all playlists (optional)**
   • Hit **Mass-change drive letters…**.
   • Edit the single-letter boxes (no “:”).
   • **Apply** → every playlist is updated & backed up.

---

7. **Done**
   Load the playlist in foobar2000—tracks should play.
   Any time you move music again, just repeat steps 3-6.
