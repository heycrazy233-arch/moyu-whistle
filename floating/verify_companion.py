"""Isolated UI checks: no agent events or production data are written."""
import tempfile
from pathlib import Path
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtTest import QTest
from companion import Companion, aggregate


app = QApplication([])
app.setQuitOnLastWindowClosed(False)
owner = QWidget()
owner.resize(420, 76)
owner.move(300, 250)
owner.show()
opened = []
pet = Companion(owner, opened.append)
pet.show()
assert aggregate([{'event': s} for s in ('idle', 'working', 'error', 'waiting')], True) == ('waiting', 1)
assert aggregate([{'event':'working', 'status_known':False}], True) == (None, 0)
assert aggregate([], True) == ('idle', 0)
for state in ('working', 'idle', 'error', 'waiting'):
    pet.update_snapshot([{'agent_key':'isolated', 'event':state}], True)
    QTest.qWait(160)
    assert pet.state == state
    if (pet.root / pet.assets.get(state, 'missing')).is_file():
        assert pet.asset_ok, f'{state}: asset failed'
    pet.grab().save(str(Path(tempfile.gettempdir()) / f'moyu-whistle-pet-{state}.png'))
    if pet.movie:
        frame = pet.movie.currentFrameNumber()
        movie = pet.movie
        pet.update_snapshot([{'event':state}], True)
        assert pet.movie is movie, 'Same-state refresh reloaded animation'
        QTest.qWait(140)
        assert pet.movie.currentFrameNumber() != frame, 'Animation did not advance'
print('PASS: four states, optional assets, animation playback and stable refresh', flush=True)
position = pet.pos()
owner.resize(420, 590)
QTest.qWait(100)
assert pet.pos() == position, 'Pet jumped on panel expansion'
owner.move(owner.pos() + QPoint(30, 20))
QTest.qWait(100)
assert pet.pos() == position + QPoint(30, 20)
QTest.mouseClick(pet, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(75, 90))
assert opened == ['waiting'], 'Click did not request existing waiting view'
pet.update_snapshot([], False)
assert pet.state == 'waiting'
assert not pet.movie or pet.movie.state() == QMovie.MovieState.Paused
pet.update_snapshot([{'event':'waiting'}], True)
pet.hide()
assert not pet.movie or pet.movie.state() == QMovie.MovieState.Paused
pet.show()
assert not pet.movie or pet.movie.state() == QMovie.MovieState.Running
pet.set_reduced_motion(True)
assert not pet.movie or pet.movie.state() == QMovie.MovieState.Paused
pet.set_reduced_motion(False)
pet.move(-10000, -10000)
pet.constrain()
assert pet.screen().availableGeometry().contains(pet.frameGeometry())
pet.assets['error'] = 'missing.gif'
pet.update_snapshot([{'event':'error'}], True)
assert not pet.asset_ok and pet.isVisible()
print('PASS: click callback, resize stability, owner movement, stale/hidden/pause, offscreen recovery, missing asset fallback', flush=True)
pet.hide()
owner.hide()
