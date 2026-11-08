import sys
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

class AppTests(unittest.TestCase):
    def test_render_optimize_reset(self):
        directory=Path(__file__).resolve().parent
        sys.path.insert(0,str(directory))
        app=AppTest.from_file(str(directory/'streamlit_app.py'),default_timeout=60).run()
        self.assertFalse(app.exception)
        next(b for b in app.button if b.label=='Optimize schedule').click().run()
        self.assertFalse(app.exception)
        self.assertIsNotNone(app.session_state['result'])
        next(b for b in app.button if b.label=='Generate scenario').click().run()
        self.assertFalse(app.exception)
        self.assertIsNone(app.session_state['result'])
