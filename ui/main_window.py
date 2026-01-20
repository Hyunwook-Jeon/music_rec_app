from __future__ import annotations
import os
import csv
from datetime import datetime

from PySide6.QtCore import Qt, QObject, Signal, Slot, QThread, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QTextBrowser,
    QSlider, QSplitter, QFileDialog, QListWidget, QListWidgetItem, QCheckBox
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import QAbstractItemView

from core.recommend_service import RecommendService
from models.dto import RecommendResult, TrackRecommendation
from utils.favorites import FavoritesStore, normalize_key
from utils.history import SearchHistoryStore


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
        self.resize(1320, 740)

        self.service = RecommendService()

        # Data
        self._items: list[TrackRecommendation] = []
        self._result: RecommendResult | None = None
        self._all_items_cache: list[TrackRecommendation] = []  # to restore after filters

        # Paths
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")

        # Favorites
        self.favs = FavoritesStore(os.path.join(data_dir, "favorites.json"))
        self._fav_map = self.favs.to_map()

        # History
        self.history = SearchHistoryStore(os.path.join(data_dir, "history.json"), max_items=50)

        self._setup_ui()
        self._setup_player()
        self._refresh_history_ui()

    # =========================
    # UI
    # =========================
    def _setup_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        # Top bar
        top = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("예: Bad Guy - Billie Eilish  /  The Weeknd")
        self.btn_search = QPushButton("추천 받기")
        self.mode = QComboBox()
        self.mode.addItems(["Auto"])

        top.addWidget(QLabel("입력"))
        top.addWidget(self.input, 1)
        top.addWidget(self.mode)
        top.addWidget(self.btn_search)
        outer.addLayout(top)

        self.status = QLabel("Ready")
        self.status.setStyleSheet("color: gray;")
        outer.addWidget(self.status)

        # Main splitter: left sidebar | table | detail
        main_split = QSplitter(Qt.Horizontal)

        # Sidebar
        sidebar = QWidget()
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(6, 6, 6, 6)

        sb.addWidget(QLabel("<b>History</b>"))
        self.list_history = QListWidget()
        self.list_history.setMinimumWidth(220)
        sb.addWidget(self.list_history, 1)

        self.btn_clear_history = QPushButton("히스토리 비우기")
        sb.addWidget(self.btn_clear_history)

        sb.addSpacing(10)
        sb.addWidget(QLabel("<b>View</b>"))
        self.chk_favs_only = QCheckBox("즐겨찾기만 보기")
        sb.addWidget(self.chk_favs_only)

        self.btn_show_favs_file = QPushButton("favorites.json 열기")
        sb.addWidget(self.btn_show_favs_file)

        self.btn_clear_favs = QPushButton("즐겨찾기 전체 삭제")
        sb.addWidget(self.btn_clear_favs)

        main_split.addWidget(sidebar)

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["#", "Track", "Artist", "Similarity", "Preview", "❤️", "Reason"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 320)
        self.table.setColumnWidth(2, 240)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 70)
        self.table.setColumnWidth(6, 360)

        main_split.addWidget(self.table)

        # Detail
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        self.detail.setHtml("<b>결과를 선택하면 상세가 표시됩니다.</b>")
        main_split.addWidget(self.detail)

        main_split.setSizes([240, 760, 320])
        outer.addWidget(main_split, 1)

        # Player bar
        player_bar = QHBoxLayout()
        self.btn_play_pause = QPushButton("Play")
        self.btn_open_lastfm = QPushButton("Last.fm")
        self.btn_open_itunes = QPushButton("iTunes")
        self.btn_open_preview = QPushButton("Preview 링크")

        self.btn_open_lastfm.setEnabled(False)
        self.btn_open_itunes.setEnabled(False)
        self.btn_open_preview.setEnabled(False)

        self.slider_pos = QSlider(Qt.Horizontal)
        self.slider_pos.setRange(0, 1000)

        self.slider_vol = QSlider(Qt.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(50)

        player_bar.addWidget(self.btn_play_pause)
        player_bar.addWidget(self.btn_open_lastfm)
        player_bar.addWidget(self.btn_open_itunes)
        player_bar.addWidget(self.btn_open_preview)
        player_bar.addWidget(QLabel("Position"))
        player_bar.addWidget(self.slider_pos, 1)
        player_bar.addWidget(QLabel("Volume"))
        player_bar.addWidget(self.slider_vol)
        outer.addLayout(player_bar)

        # Signals
        self.btn_search.clicked.connect(self.on_search_clicked)
        self.table.itemSelectionChanged.connect(self.on_row_selected)

        self.btn_play_pause.clicked.connect(self.on_play_pause)
        self.slider_vol.valueChanged.connect(self.on_volume_changed)
        self.slider_pos.sliderReleased.connect(self.on_seek_released)

        self.btn_open_lastfm.clicked.connect(self.on_open_lastfm)
        self.btn_open_itunes.clicked.connect(self.on_open_itunes)
        self.btn_open_preview.clicked.connect(self.on_open_preview)

        # Sidebar signals
        self.list_history.itemClicked.connect(self.on_history_item_clicked)
        self.btn_clear_history.clicked.connect(self.on_clear_history)
        self.chk_favs_only.stateChanged.connect(self.on_toggle_favs_only)
        self.btn_show_favs_file.clicked.connect(self.open_favorites_file)
        self.btn_clear_favs.clicked.connect(self.clear_favorites)

        # Menu
        self._setup_menu()

    def _setup_menu(self):
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self.close)

        act_export_csv = QAction("Export CSV", self)
        act_export_csv.triggered.connect(self.export_csv)

        act_export_txt = QAction("Export TXT", self)
        act_export_txt.triggered.connect(self.export_txt)

        self.menuBar().addAction(act_export_csv)
        self.menuBar().addAction(act_export_txt)
        self.menuBar().addAction(act_quit)

    # =========================
    # Player
    # =========================
    def _setup_player(self):
        self.audio = QAudioOutput()
        self.audio.setVolume(0.5)

        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio)

        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.playbackStateChanged.connect(self.on_state_changed)

        self._duration = 0

    # =========================
    # History UI
    # =========================
    def _refresh_history_ui(self):
        self.list_history.clear()
        items = self.history.load()
        for it in items:
            q = str(it.get("q", "")).strip()
            ts = str(it.get("ts", "")).strip()
            if not q:
                continue
            item = QListWidgetItem(f"{q}\n{ts}")
            item.setData(Qt.UserRole, q)
            self.list_history.addItem(item)

    @Slot(QListWidgetItem)
    def on_history_item_clicked(self, item: QListWidgetItem):
        q = item.data(Qt.UserRole)
        if not q:
            return
        self.input.setText(q)
        self.on_search_clicked()

    @Slot()
    def on_clear_history(self):
        reply = QMessageBox.question(self, "Confirm", "검색 히스토리를 모두 삭제할까요?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.history.clear()
        self._refresh_history_ui()

    # =========================
    # Search flow (QThread)
    # =========================
    @Slot()
    def on_search_clicked(self):
        text = self.input.text().strip()
        if not text:
            QMessageBox.information(self, "Info", "입력값을 넣어주세요.")
            return

        # Persist history
        self.history.add(text)
        self._refresh_history_ui()

        # refresh favorites cache
        self._fav_map = self.favs.to_map()

        # UI lock
        self.btn_search.setEnabled(False)
        self.status.setText("검색/추천 중... (네트워크)")
        self.table.setRowCount(0)
        self.detail.setHtml("<i>Loading...</i>")
        self._items = []
        self._all_items_cache = []
        self._result = None

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

        self._result = res
        items = res.items or []

        # Personalization rerank
        items = self._personalized_rerank(items)

        # Update rank after rerank
        for i, it in enumerate(items, start=1):
            it.rank = i

        self._all_items_cache = items[:]  # keep full list
        self._items = items

        # Apply filter (favorites only) if toggled
        if self.chk_favs_only.isChecked():
            self._items = [x for x in self._all_items_cache if self._is_favorite(x)]
            for i, it in enumerate(self._items, start=1):
                it.rank = i

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

    # =========================
    # Table
    # =========================
    def _fill_table(self, items: list[TrackRecommendation]):
        self.table.setRowCount(len(items))

        for row, it in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(str(it.rank)))
            self.table.setItem(row, 1, QTableWidgetItem(it.track))
            self.table.setItem(row, 2, QTableWidgetItem(it.artist))

            sim_txt = f"{it.similarity:.2f}" if isinstance(it.similarity, float) else "-"
            self.table.setItem(row, 3, QTableWidgetItem(sim_txt))

            btn_preview = QPushButton("Play" if it.preview_url else "N/A")
            btn_preview.setEnabled(bool(it.preview_url))
            btn_preview.clicked.connect(lambda checked=False, r=row: self.play_row(r))
            self.table.setCellWidget(row, 4, btn_preview)

            fav_btn = QPushButton("♥" if self._is_favorite(it) else "♡")
            fav_btn.setToolTip("즐겨찾기 추가/해제")
            fav_btn.clicked.connect(lambda checked=False, r=row: self.toggle_favorite(r))
            self.table.setCellWidget(row, 5, fav_btn)

            reason = getattr(it, "reason", "") or ""
            self.table.setItem(row, 6, QTableWidgetItem(reason))

        self.table.resizeRowsToContents()

    # =========================
    # Selection & detail
    # =========================
    @Slot()
    def on_row_selected(self):
        row = self._selected_row()
        if row is None:
            self._set_link_buttons(None)
            return

        it = self._items[row]
        self._show_detail(it)
        self._set_link_buttons(it)

    def _show_detail(self, it: TrackRecommendation):
        tags = ", ".join(it.tags) if it.tags else "-"
        lastfm = f'<a href="{it.lastfm_url}">Last.fm</a>' if it.lastfm_url else "-"
        itunes = f'<a href="{it.itunes_url}">iTunes</a>' if it.itunes_url else "-"
        preview = it.preview_url or "-"
        reason = getattr(it, "reason", "") or "-"

        # Cover image (use artwork_url if present)
        cover_html = ""
        if getattr(it, "artwork_url", None):
            cover_html = f'<p><img src="{it.artwork_url}" width="160" height="160"/></p>'

        html = f"""
        {cover_html}
        <h3>{it.track}</h3>
        <p><b>Artist:</b> {it.artist}</p>
        <p><b>Reason:</b> {reason}</p>
        <p><b>Tags:</b> {tags}</p>
        <p><b>Links:</b> {lastfm} | {itunes}</p>
        <p><b>Preview:</b> {preview}</p>
        """
        self.detail.setHtml(html)

    def _set_link_buttons(self, it: TrackRecommendation | None):
        if not it:
            self.btn_open_lastfm.setEnabled(False)
            self.btn_open_itunes.setEnabled(False)
            self.btn_open_preview.setEnabled(False)
            return
        self.btn_open_lastfm.setEnabled(bool(it.lastfm_url))
        self.btn_open_itunes.setEnabled(bool(it.itunes_url))
        self.btn_open_preview.setEnabled(bool(it.preview_url or it.itunes_url))

    def _selected_row(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return None
        return sel[0].row()

    # =========================
    # Favorites
    # =========================
    def _is_favorite(self, it: TrackRecommendation) -> bool:
        key = normalize_key(it.track, it.artist)
        return key in self._fav_map

    def toggle_favorite(self, row: int):
        if row < 0 or row >= len(self._items):
            return
        it = self._items[row]
        key = normalize_key(it.track, it.artist)

        if key in self._fav_map:
            self.favs.remove(it.track, it.artist)
            self._fav_map.pop(key, None)
        else:
            snap = self.favs.export_snapshot_from_reco(it)
            self.favs.upsert(snap)
            self._fav_map[key] = snap

        # Update fav button
        w = self.table.cellWidget(row, 5)
        if isinstance(w, QPushButton):
            w.setText("♥" if key in self._fav_map else "♡")

        # Re-rank immediately
        self._all_items_cache = self._personalized_rerank(self._all_items_cache)
        # Apply filter if toggled
        if self.chk_favs_only.isChecked():
            self._items = [x for x in self._all_items_cache if self._is_favorite(x)]
        else:
            self._items = self._all_items_cache[:]

        for i, x in enumerate(self._items, start=1):
            x.rank = i

        self._fill_table(self._items)

    def open_favorites_file(self):
        path = self.favs.filepath
        if not os.path.exists(path):
            self.favs.save([])
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def clear_favorites(self):
        reply = QMessageBox.question(self, "Confirm", "즐겨찾기를 모두 삭제할까요?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.favs.clear()
        self._fav_map = {}
        if self._all_items_cache:
            self._fill_table(self._items)

    @Slot(int)
    def on_toggle_favs_only(self, state: int):
        if not self._all_items_cache:
            return
        if self.chk_favs_only.isChecked():
            self._items = [x for x in self._all_items_cache if self._is_favorite(x)]
        else:
            self._items = self._all_items_cache[:]
        for i, it in enumerate(self._items, start=1):
            it.rank = i
        self._fill_table(self._items)

    # =========================
    # Personalization / Rerank
    # =========================
    def _personalized_rerank(self, items: list[TrackRecommendation]) -> list[TrackRecommendation]:
        if not items:
            return items

        fav_artists = self.favs.favorite_artists()
        fav_tags = self.favs.favorite_tags()

        def score(it: TrackRecommendation) -> float:
            s = 0.0
            if it.preview_url:
                s += 1000.0
            if isinstance(it.similarity, float):
                s += it.similarity * 100.0
            if (it.artist or "").strip().lower() in fav_artists:
                s += 60.0
            if it.tags and fav_tags:
                overlap = {t.strip().lower() for t in it.tags if t} & fav_tags
                s += 10.0 * len(overlap)
            if self._is_favorite(it):
                s += 80.0
            return s

        return sorted(items, key=score, reverse=True)

    # =========================
    # Export
    # =========================
    def export_csv(self):
        if not self._items:
            QMessageBox.information(self, "Info", "내보낼 추천 결과가 없습니다.")
            return

        default_name = f"recommendations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["rank", "track", "artist", "similarity", "preview_url", "lastfm_url", "itunes_url", "tags", "reason"])
                for it in self._items:
                    tags = ";".join(it.tags) if it.tags else ""
                    reason = getattr(it, "reason", "") or ""
                    w.writerow([
                        it.rank,
                        it.track,
                        it.artist,
                        "" if it.similarity is None else it.similarity,
                        it.preview_url or "",
                        it.lastfm_url or "",
                        it.itunes_url or "",
                        tags,
                        reason,
                    ])
            self.status.setText(f"CSV 저장 완료: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"CSV 저장 실패: {e}")

    def export_txt(self):
        if not self._items:
            QMessageBox.information(self, "Info", "내보낼 추천 결과가 없습니다.")
            return

        default_name = f"recommendations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Save TXT", default_name, "Text Files (*.txt)")
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                for it in self._items:
                    f.write(f"{it.track} - {it.artist}\n")
            self.status.setText(f"TXT 저장 완료: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"TXT 저장 실패: {e}")

    # =========================
    # External links
    # =========================
    def on_open_lastfm(self):
        it = self._current_item()
        if it and it.lastfm_url:
            QDesktopServices.openUrl(QUrl(it.lastfm_url))

    def on_open_itunes(self):
        it = self._current_item()
        if it and it.itunes_url:
            QDesktopServices.openUrl(QUrl(it.itunes_url))

    def on_open_preview(self):
        it = self._current_item()
        if not it:
            return
        url = it.preview_url or it.itunes_url
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _current_item(self) -> TrackRecommendation | None:
        row = self._selected_row()
        if row is None:
            return None
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row]

    # =========================
    # Player controls
    # =========================
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
