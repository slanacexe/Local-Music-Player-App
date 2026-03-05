import sys
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem,
    QLabel, QPushButton, QSlider,
    QFileDialog, QLineEdit, QMessageBox, QToolButton,
    QStackedWidget
)

from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from mutagen import File as MutagenFile
from PIL import Image
from io import BytesIO


APP_VERSION = "1.3"
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


@dataclass
class Track:
    path: Path
    title: str
    artist: str


def ms_to_mmss(ms: int):
    s = ms // 1000
    m = s // 60
    s = s % 60
    return f"{m:02d}:{s:02d}"


def read_tags(path: Path):
    title = path.stem
    artist = ""
    cover = None

    try:
        audio = MutagenFile(path)

        if audio:
            if audio.tags:

                if "TIT2" in audio.tags:
                    title = str(audio.tags["TIT2"])

                if "TPE1" in audio.tags:
                    artist = str(audio.tags["TPE1"])

                for k in audio.tags.keys():
                    if str(k).startswith("APIC"):
                        cover = audio.tags[k].data

    except Exception:
        pass

    return title, artist, cover


class PlayerWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Local Music Player")
        self.resize(720, 520)

        self.tracks: List[Track] = []
        self.current_index = -1

        self.shuffle = False
        self.repeat = False

        self.audio_out = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_out)

        self.audio_out.setVolume(0.85)

        self._build_ui()
        self._build_menu()
        self._wire_events()

    # ---------------- UI ----------------

    def _build_ui(self):

        self.stack = QStackedWidget()

        self.full_ui = self._build_full_player()
        self.mini_ui = self._build_mini_player()

        self.stack.addWidget(self.full_ui)
        self.stack.addWidget(self.mini_ui)

        self.setCentralWidget(self.stack)

    # ---------------- FULL PLAYER ----------------

    def _build_full_player(self):

        root = QWidget()
        layout = QVBoxLayout(root)

        top = QHBoxLayout()

        self.btn_select_folder = QPushButton("Select Folder")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")

        top.addWidget(self.btn_select_folder)
        top.addWidget(self.search_box)

        self.track_list = QListWidget()

        self.cover = QLabel()
        self.cover.setFixedSize(120, 120)

        self.lbl_title = QLabel("—")
        self.lbl_artist = QLabel("—")

        controls = QHBoxLayout()

        self.btn_prev = QPushButton("⏮")
        self.btn_play = QPushButton("▶")
        self.btn_next = QPushButton("⏭")

        self.btn_shuffle = QToolButton()
        self.btn_shuffle.setText("Shuffle")
        self.btn_shuffle.setCheckable(True)

        self.btn_repeat = QToolButton()
        self.btn_repeat.setText("Repeat")
        self.btn_repeat.setCheckable(True)

        controls.addWidget(self.btn_prev)
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_next)
        controls.addWidget(self.btn_shuffle)
        controls.addWidget(self.btn_repeat)

        self.slider = QSlider(Qt.Horizontal)

        time_row = QHBoxLayout()

        self.lbl_time = QLabel("00:00")
        self.lbl_time_total = QLabel("00:00")

        time_row.addWidget(self.lbl_time)
        time_row.addWidget(self.slider)
        time_row.addWidget(self.lbl_time_total)

        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(85)

        layout.addLayout(top)
        layout.addWidget(self.track_list)
        layout.addWidget(self.cover)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_artist)
        layout.addLayout(controls)
        layout.addWidget(self.volume)
        layout.addLayout(time_row)

        return root

    # ---------------- MINI PLAYER ----------------

    def _build_mini_player(self):

        root = QWidget()
        layout = QHBoxLayout(root)

        self.mini_cover = QLabel()
        self.mini_cover.setFixedSize(60, 60)

        info = QVBoxLayout()

        self.mini_title = QLabel("—")
        self.mini_artist = QLabel("—")

        info.addWidget(self.mini_title)
        info.addWidget(self.mini_artist)

        buttons = QHBoxLayout()

        self.mini_prev = QPushButton("⏮")
        self.mini_play = QPushButton("▶")
        self.mini_next = QPushButton("⏭")

        buttons.addWidget(self.mini_prev)
        buttons.addWidget(self.mini_play)
        buttons.addWidget(self.mini_next)

        right = QVBoxLayout()

        self.mini_slider = QSlider(Qt.Horizontal)

        right.addLayout(info)
        right.addLayout(buttons)
        right.addWidget(self.mini_slider)

        layout.addWidget(self.mini_cover)
        layout.addLayout(right)

        return root

    # ---------------- MENU ----------------

    def _build_menu(self):

        menu = self.menuBar()

        file_menu = menu.addMenu("File")

        act_folder = QAction("Select Folder…", self)
        act_folder.triggered.connect(self.select_folder)

        file_menu.addAction(act_folder)

        playback_menu = menu.addMenu("Playback")

        act_play_pause = QAction("Play / Pause", self)
        act_play_pause.setShortcut(Qt.Key_Space)
        act_play_pause.triggered.connect(self.toggle_play)

        playback_menu.addAction(act_play_pause)

        mini_action = QAction("Toggle Mini Player", self)
        mini_action.triggered.connect(self.toggle_mini_player)

        playback_menu.addAction(mini_action)

        help_menu = menu.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)

        help_menu.addAction(about_action)

    # ---------------- EVENTS ----------------

    def _wire_events(self):

        self.btn_select_folder.clicked.connect(self.select_folder)

        self.track_list.itemDoubleClicked.connect(
            lambda item: self.play_index(item.data(Qt.UserRole))
        )

        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next.clicked.connect(self.next_track)
        self.btn_prev.clicked.connect(self.prev_track)

        self.mini_play.clicked.connect(self.toggle_play)
        self.mini_next.clicked.connect(self.next_track)
        self.mini_prev.clicked.connect(self.prev_track)

        self.volume.valueChanged.connect(
            lambda v: self.audio_out.setVolume(v / 100)
        )

        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)

        self.slider.sliderMoved.connect(self.player.setPosition)
        self.mini_slider.sliderMoved.connect(self.player.setPosition)

    # ---------------- MINI MODE ----------------

    def toggle_mini_player(self):

        if self.stack.currentIndex() == 0:
            self.stack.setCurrentIndex(1)
            self.setFixedSize(360, 120)
        else:
            self.stack.setCurrentIndex(0)
            self.setMinimumSize(720, 520)
            self.resize(720, 520)

    # ---------------- PLAYBACK ----------------

    def play_index(self, index):

        self.current_index = index
        track = self.tracks[index]

        self.player.setSource(QUrl.fromLocalFile(str(track.path)))
        self.player.play()

        title, artist, cover = read_tags(track.path)

        self.lbl_title.setText(title)
        self.lbl_artist.setText(artist)

        self.mini_title.setText(title)
        self.mini_artist.setText(artist)

        if cover:

            image = Image.open(BytesIO(cover))
            image = image.resize((120, 120))

            data = BytesIO()
            image.save(data, format="PNG")

            pix = QPixmap()
            pix.loadFromData(data.getvalue())

            self.cover.setPixmap(pix)

            mini = pix.scaled(60, 60)
            self.mini_cover.setPixmap(mini)

    def toggle_play(self):

        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.btn_play.setText("▶")
            self.mini_play.setText("▶")
        else:
            self.player.play()
            self.btn_play.setText("⏸")
            self.mini_play.setText("⏸")

    def next_track(self):

        if not self.tracks:
            return

        i = (self.current_index + 1) % len(self.tracks)
        self.play_index(i)

    def prev_track(self):

        if not self.tracks:
            return

        i = (self.current_index - 1) % len(self.tracks)
        self.play_index(i)

    # ---------------- TIMER ----------------

    def update_position(self, pos):

        self.slider.blockSignals(True)
        self.mini_slider.blockSignals(True)

        self.slider.setValue(pos)
        self.mini_slider.setValue(pos)

        self.slider.blockSignals(False)
        self.mini_slider.blockSignals(False)

        self.lbl_time.setText(ms_to_mmss(pos))

    def update_duration(self, dur):

        self.slider.setRange(0, dur)
        self.mini_slider.setRange(0, dur)

        self.lbl_time_total.setText(ms_to_mmss(dur))

    # ---------------- FILE SCAN ----------------

    def select_folder(self):

        folder = QFileDialog.getExistingDirectory(self, "Select music folder")

        if not folder:
            return

        base = Path(folder)

        tracks = []

        for p in base.rglob("*"):

            if p.suffix.lower() in AUDIO_EXTS:

                title, artist, _ = read_tags(p)

                tracks.append(Track(p, title, artist))

        self.tracks = tracks

        self.track_list.clear()

        for i, t in enumerate(self.tracks):

            item = QListWidgetItem(f"{t.artist} — {t.title}")
            item.setData(Qt.UserRole, i)

            self.track_list.addItem(item)

    # ---------------- ABOUT ----------------

    def show_about(self):

        QMessageBox.about(
            self,
            "About",
            f"Local Music Player v{APP_VERSION}\n\nPython + Qt music player."
        )


def main():

    app = QApplication(sys.argv)

    window = PlayerWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()