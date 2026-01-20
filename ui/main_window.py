from __future__ import annotations
import os

from PySide6.QtCore import Qt, QObject, Signal, Slot, QThread, QUrl
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QTextBrowser,
    QSlider, QSplitter
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import QAbstractItemView

from core.recommend_service import RecommendService
from models.dto import RecommendResult, TrackRecommendation


class RecommendWorker(QObject):
    finished = Signal(RecommendResult)
    error = Signal(str)

    def __init__(self, service: RecommendService, text: str):
        super().__init__()
        self.service = service
        self.text = text

    @Slot()
    def run(self):
        try:
            res = self.service.recommend(self.text, limit_tracks=20)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Rec App (PySide6)")
        self.resize(1100, 650)

        self.service = RecommendService()

        self._items: list[TrackRecommendation] = []

        self._setup_ui()
        self._setup_player()

    def _setup_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)

        # Top bar
        top = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("예: Bad Guy - Billie Eilish  /  The Weeknd")
        self.btn_search = QPushButton("추천 받기")
        self.mode = QComboBox()
        self.mode.addItems(["Auto"])  # 지금은 Auto만 쓰되, 확장 가능

        top.addWidget(QLabel("입력"))
        top.addWidget(self.input, 1)
        top.addWidget(self.mode)
        top.addWidget(self.btn_search)
        main.addLayout(top)

        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: gray;")
        main.addWidget(self.status)

        # Splitter: table + detail
        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Track", "Artist", "Similarity", "Preview"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 320)
        self.table.setColumnWidth(2, 240)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 90)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        self.detail.setHtml("<b>결과를 선택하면 상세가 표시됩니다.</b>")

        splitter.addWidget(self.table)
        splitter.addWidget(self.detail)
        splitter.setSizes([750, 350])

        main.addWidget(splitter, 1)

        # Player bar
        player_bar = QHBoxLayout()
        self.btn_play_pause = QPushButton("Play")
        self.slider_pos = QSlider(Qt.Horizontal)
        self.slider_pos.setRange(0, 1000)
        self.slider_vol = QSlider(Qt.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(50)

        player_bar.addWidget(self.btn_play_pause)
        player_bar.addWidget(QLabel("Position"))
        player_bar.addWidget(self.slider_pos, 1)
        player_bar.addWidget(QLabel("Volume"))
        player_bar.addWidget(self.slider_vol)
        main.addLayout(player_bar)

        # Signals
        self.btn_search.clicked.connect(self.on_search_clicked)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        self.btn_play_pause.clicked.connect(self.on_play_pause)
        self.slider_vol.valueChanged.connect(self.on_volume_changed)
        self.slider_pos.sliderReleased.connect(self.on_seek_released)

        # Menu (optional)
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self.close)
        self.menuBar().addAction(act_quit)

    def _setup_player(self):
        self.audio = QAudioOutput()
        self.audio.setVolume(0.5)

        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio)

        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.playbackStateChanged.connect(self.on_state_changed)

        self._duration = 0
        self._seeking = False

    # -------- Search flow (QThread) --------
    @Slot()
    def on_search_clicked(self):
        text = self.input.text().strip()
        if not text:
            QMessageBox.information(self, "Info", "입력값을 넣어주세요.")
            return

        # UI lock
        self.btn_search.setEnabled(False)
        self.status.setText("검색/추천 중... (네트워크)")
        self.table.setRowCount(0)
        self.detail.setHtml("<i>Loading...</i>")
        self._items = []

        self.thread = QThread()
        self.worker = RecommendWorker(self.service, text)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_recommend_finished)
        self.worker.error.connect(self.on_recommend_error)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.worker.error.connect(self.thread.quit)
        self.worker.error.connect(self.worker.deleteLater)

        self.thread.start()

    @Slot(RecommendResult)
    def on_recommend_finished(self, res: RecommendResult):
        self.btn_search.setEnabled(True)
        self.status.setText(res.message or "Done")

        self._items = res.items or []
        self._fill_table(self._items)

        if not self._items:
            self.detail.setHtml("<b>추천 결과가 없습니다.</b><br/>입력을 조금 더 구체적으로 해보세요.")
        else:
            self.detail.setHtml("<b>왼쪽에서 곡을 선택하면 상세/미리듣기가 가능합니다.</b>")

    @Slot(str)
    def on_recommend_error(self, msg: str):
        self.btn_search.setEnabled(True)
        self.status.setText("Error")
        QMessageBox.critical(self, "Error", msg)

    def _fill_table(self, items: list[TrackRecommendation]):
        self.table.setRowCount(len(items))
        for row, it in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(str(it.rank)))
            self.table.setItem(row, 1, QTableWidgetItem(it.track))
            self.table.setItem(row, 2, QTableWidgetItem(it.artist))
            sim_txt = f"{it.similarity:.2f}" if isinstance(it.similarity, float) else "-"
            self.table.setItem(row, 3, QTableWidgetItem(sim_txt))

            btn = QPushButton("Play" if it.preview_url else "N/A")
            btn.setEnabled(bool(it.preview_url))
            btn.clicked.connect(lambda checked=False, r=row: self.play_row(r))
            self.table.setCellWidget(row, 4, btn)

        self.table.resizeRowsToContents()

    # -------- Selection & detail --------
    @Slot()
    def on_row_selected(self):
        row = self._selected_row()
        if row is None:
            return
        it = self._items[row]
        self._show_detail(it)

    def _show_detail(self, it: TrackRecommendation):
        tags = ", ".join(it.tags) if it.tags else "-"
        lastfm = f'<a href="{it.lastfm_url}">Last.fm</a>' if it.lastfm_url else "-"
        itunes = f'<a href="{it.itunes_url}">iTunes</a>' if it.itunes_url else "-"
        preview = it.preview_url or "-"

        html = f"""
        <h3>{it.track}</h3>
        <p><b>Artist:</b> {it.artist}</p>
        <p><b>Tags:</b> {tags}</p>
        <p><b>Links:</b> {lastfm} | {itunes}</p>
        <p><b>Preview:</b> {preview}</p>
        """
        self.detail.setHtml(html)

    def _selected_row(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return None
        return sel[0].row()

    # -------- Player controls --------
    def play_row(self, row: int):
        if row < 0 or row >= len(self._items):
            return
        it = self._items[row]
        if not it.preview_url:
            return

        self.player.setSource(QUrl(it.preview_url))
        self.player.play()

    @Slot()
    def on_play_pause(self):
        state = self.player.playbackState()
        if state == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            # 재생할 소스가 없으면 선택된 row 재생 시도
            if self.player.source().isEmpty():
                row = self._selected_row()
                if row is not None:
                    self.play_row(row)
                    return
            self.player.play()

    @Slot(int)
    def on_volume_changed(self, v: int):
        self.audio.setVolume(max(0.0, min(1.0, v / 100.0)))

    @Slot()
    def on_seek_released(self):
        if self._duration <= 0:
            return
        val = self.slider_pos.value() / 1000.0
        new_pos = int(self._duration * val)
        self.player.setPosition(new_pos)

    @Slot(int)
    def on_position_changed(self, pos: int):
        if self._duration <= 0:
            return
        # 슬라이더 드래그 중엔 업데이트 최소화
        val = int((pos / self._duration) * 1000)
        self.slider_pos.blockSignals(True)
        self.slider_pos.setValue(max(0, min(1000, val)))
        self.slider_pos.blockSignals(False)

    @Slot(int)
    def on_duration_changed(self, dur: int):
        self._duration = dur

    @Slot()
    def on_state_changed(self):
        state = self.player.playbackState()
        self.btn_play_pause.setText("Pause" if state == QMediaPlayer.PlayingState else "Play")
