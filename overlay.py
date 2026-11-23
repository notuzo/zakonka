import json
import os
import sys
import threading
import traceback
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
BASE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
DATA = Path(getattr(sys, "_MEIPASS", BASE))
STATE = (
    Path(os.environ.get("LOCALAPPDATA", str(BASE))) / "Zakonka"
    if FROZEN
    else BASE
)
STATE.mkdir(parents=True, exist_ok=True)
LOG = STATE / "overlay.log"
UI_STATE = STATE / "overlay_ui.json"
LOGO = DATA / "logo_icon.png"
LOGO_BUTTON = DATA / "logo_button.png"

try:
    from PyQt5.QtCore import QLockFile, QObject, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
    from PyQt5.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap
    from PyQt5.QtWebChannel import QWebChannel
    from PyQt5.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView
    from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu, QWidget

    import ask
except Exception:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(traceback.format_exc() + "\n")
    raise


class Bridge(QObject):
    answerReady = pyqtSignal(str)
    deepseekReady = pyqtSignal(str)
    searchReady = pyqtSignal(str)
    articleReady = pyqtSignal(str)
    copyReady = pyqtSignal(str)

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.closing = False

    @pyqtSlot(str, bool)
    def ask(self, q: str, use_templates: bool = True) -> None:
        threading.Thread(target=self._work, args=(q, use_templates), daemon=True).start()

    def _work(self, q: str, use_templates: bool = True) -> None:
        try:
            r = ask.respond(q, use_templates=use_templates)
        except Exception as e:
            r = {
                "type": "error",
                "error": f"{type(e).__name__}: {e}",
                "hits": [],
                "time": 0,
            }
        if not self.closing:
            self.answerReady.emit(json.dumps(r, ensure_ascii=False))

    @pyqtSlot(str, bool)
    def search(self, q: str, typing: bool = False) -> None:
        threading.Thread(
            target=self._search, args=(q, typing), daemon=True
        ).start()

    def _search(self, q: str, typing: bool) -> None:
        try:
            r = ask.search_articles(q, typing=typing)
        except Exception as e:
            r = {
                "query": q,
                "typing": typing,
                "terms": [],
                "forms": [],
                "prefixes": [],
                "items": [],
                "total": 0,
                "error": f"{type(e).__name__}: {e}",
            }
        if not self.closing:
            self.searchReady.emit(json.dumps(r, ensure_ascii=False))

    @pyqtSlot(int)
    def article(self, idx: int) -> None:
        try:
            a = ask.articles[int(idx)]
            payload = {"idx": int(idx), "text": ask.article_body(a)}
        except Exception as e:
            payload = {"idx": int(idx), "error": f"{type(e).__name__}: {e}"}
        if not self.closing:
            self.articleReady.emit(json.dumps(payload, ensure_ascii=False))

    @pyqtSlot(int)
    def copy_article(self, idx: int) -> None:
        try:
            a = ask.articles[int(idx)]
            head = a["doc_short"]
            if a["article"] != "0":
                head += f' ст. {a["article"]}'
            if a["article_title"].strip():
                head += f' — {a["article_title"].strip()}'
            QApplication.clipboard().setText(head + "\n\n" + ask.article_body(a))
            payload = {"ok": True}
        except Exception as e:
            payload = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        self.copyReady.emit(json.dumps(payload, ensure_ascii=False))

    @pyqtSlot(str)
    def deepseek(self, q: str) -> None:
        try:
            prompt, hits = ask.deepseek_prompt(q)
            QApplication.clipboard().setText(prompt)
            payload = {"ok": True, "chars": len(prompt), "hits": hits}
        except Exception as e:
            payload = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        self.deepseekReady.emit(json.dumps(payload, ensure_ascii=False))

    @pyqtSlot()
    def minimize(self) -> None:
        self.window.hide()

    @pyqtSlot()
    def close(self) -> None:
        self.window.hide()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Законка")
        if LOGO.exists():
            self.setWindowIcon(QIcon(str(LOGO)))
        self.setWindowFlags(
            Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint
        )
        self.resize(860, 480)
        self.setWindowOpacity(0.93)

        self.view = QWebEngineView(self)
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.setCentralWidget(self.view)

        self.bridge = Bridge(self)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("api", self.bridge)
        self.view.page().setWebChannel(self.channel)

        html = (DATA / "overlay.html").read_text(encoding="utf-8")
        self.view.setHtml(html, QUrl.fromLocalFile(str(DATA) + "/"))

    def show_near(self, button: QWidget) -> None:
        screen = QApplication.screenAt(button.pos()) or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = button.x() - self.width() - 12
        if x < geo.left():
            x = button.x() + button.width() + 12
        y = button.y() - 20
        x = max(geo.left() + 8, min(x, geo.right() - self.width() - 8))
        y = max(geo.top() + 8, min(y, geo.bottom() - self.height() - 8))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.view.setFocus()
        QTimer.singleShot(
            80,
            lambda: self.view.page().runJavaScript(
                "document.getElementById('q').focus();"
            ),
        )

    def closeEvent(self, event) -> None:
        self.hide()
        event.ignore()


class FloatingButton(QWidget):
    def __init__(self, window: Window):
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.window = window
        self.setWindowTitle("Законка")
        self.setWindowIcon(QIcon(str(LOGO)) if LOGO.exists() else QIcon())
        self.setFixedSize(46, 46)
        self._pix = QPixmap(str(LOGO_BUTTON)) if LOGO_BUTTON.exists() else QPixmap()
        self.setToolTip("ЛКМ — открыть/свернуть, ПКМ — выход")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._press = None
        self._start = None
        self._moved = False

        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x, y = geo.right() - 80, geo.top() + 120
        try:
            state = json.loads(UI_STATE.read_text(encoding="utf-8"))
            x, y = int(state["x"]), int(state["y"])
        except Exception:
            pass
        x = max(geo.left(), min(x, geo.right() - self.width()))
        y = max(geo.top(), min(y, geo.bottom() - self.height()))
        self.move(x, y)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if not self._pix.isNull():
            p.drawPixmap(self.rect(), self._pix)
            return
        p.setBrush(QColor("#f6f2e9"))
        p.setPen(QPen(QColor("#1b1a17"), 1))
        p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        p.setPen(QColor("#1b1a17"))
        p.setFont(QFont("Georgia", 18, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter, "З")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press = event.globalPos()
            self._start = self.pos()
            self._moved = False
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._press is not None and event.buttons() & Qt.LeftButton:
            delta = event.globalPos() - self._press
            if delta.manhattanLength() > 4:
                self._moved = True
            if self._moved:
                self.move(self._start + delta)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._press is not None:
            moved = self._moved
            self._press = None
            if moved:
                self.save_pos()
            else:
                self.toggle()
            event.accept()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        act = menu.addAction("Свернуть" if self.window.isVisible() else "Открыть")
        act.triggered.connect(self.toggle)
        menu.addSeparator()
        quit_act = menu.addAction("Выход")
        quit_act.triggered.connect(QApplication.quit)
        menu.exec_(event.globalPos())

    def toggle(self) -> None:
        if self.window.isVisible():
            self.window.hide()
        else:
            self.window.show_near(self)

    def save_pos(self) -> None:
        try:
            UI_STATE.write_text(
                json.dumps({"x": self.x(), "y": self.y()}), encoding="utf-8"
            )
        except Exception:
            pass


def main() -> None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    lock = QLockFile(str(STATE / "overlay.lock"))
    if not lock.tryLock(100):
        with LOG.open("a", encoding="utf-8") as f:
            f.write("already running\n")
        return
    threading.Thread(target=ask.get_lemma_index, daemon=True).start()
    window = Window()
    button = FloatingButton(window)
    button.show()

    def shutdown() -> None:
        window.bridge.closing = True
        lock.unlock()

    app.aboutToQuit.connect(shutdown)
    if "--selftest" in sys.argv:
        window.show_near(button)
        QTimer.singleShot(
            2500,
            lambda: window.view.page().runJavaScript(
                "const q=document.getElementById('q');"
                "q.value='20тк';requestSearch(q.value,false);"
            ),
        )
        QTimer.singleShot(
            3600,
            lambda: window.view.page().runJavaScript(
                "const h=document.querySelector('.hit');if(h){h.open=true;}"
            ),
        )
    else:
        window.hide()
    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
        raise
