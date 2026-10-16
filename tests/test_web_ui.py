"""Run JavaScript checks when Node is available; Python-only installs can skip."""
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js is optional for Python users")
class WebUITest(unittest.TestCase):
    def test_translation_state(self):
        subprocess.run(["node", str(ROOT/"tests/test_i18n.js")], check=True)

    def test_browser_scripts_parse(self):
        subprocess.run(["node", "--check", str(ROOT/"i18n.js")], check=True)
        with tempfile.TemporaryDirectory() as tmp:
            for page in ("library.html", "player.html"):
                text = (ROOT/page).read_text(encoding="utf-8")
                for i, script in enumerate(re.findall(r"<script>(.*?)</script>", text, re.S)):
                    file = pathlib.Path(tmp)/f"{page}-{i}.js"
                    file.write_text(script, encoding="utf-8")
                    subprocess.run(["node", "--check", str(file)], check=True)


if __name__ == "__main__":
    unittest.main()
