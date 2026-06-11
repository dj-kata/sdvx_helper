"""
SDVX Helper - cx_Freeze build settings.
"""

import sys
import shutil
from pathlib import Path

from cx_Freeze import Executable, setup
from cx_Freeze.command.build_exe import build_exe as cx_build_exe


PROJECT_NAME = "sdvx_helper"
ENTRY_POINT = "sdvx_helper.pyw"
EXE_NAME = "sdvx_helper.exe" if sys.platform == "win32" else "sdvx_helper"
BUILD_DIR = "sdvx_helper"
FREEZE_BUILD_DIR = "build/sdvx_helper_freeze"
ICON_FILE = Path("src/icon.ico")
INFNOTEBOOK_CANDIDATES = [
    Path("infnotebook"),
    Path("../inf_daken_counter_obsw/infnotebook"),
]


def add_if_exists(include_files: list[tuple[str, str]], src: str, dst: str) -> None:
    path = Path(src)
    if path.exists():
        include_files.append((str(path), dst))


include_files: list[tuple[str, str]] = []

# PySide6 needs the Qt plugin tree next to the frozen executable.
try:
    import PySide6

    pyside6_path = Path(PySide6.__file__).parent

    add_if_exists(include_files, str(pyside6_path / "plugins"), "lib/PySide6/plugins")
    add_if_exists(
        include_files,
        str(pyside6_path / "translations"),
        "lib/PySide6/translations",
    )

    qt_conf = Path("build/qt.conf")
    qt_conf.parent.mkdir(parents=True, exist_ok=True)
    qt_conf.write_text(
        "[Paths]\n"
        "Prefix = .\n"
        "Binaries = .\n"
        "Plugins = lib/PySide6/plugins\n",
        encoding="utf-8",
    )
    include_files.append((str(qt_conf), "qt.conf"))
except ImportError:
    print("Warning: PySide6 not found. Build may not work correctly.")


add_if_exists(include_files, "resources", "resources")
add_if_exists(include_files, "template", "template")
add_if_exists(include_files, "version.txt", "version.txt")
add_if_exists(include_files, "LICENSE", "LICENSE")
add_if_exists(include_files, "README.md", "README.md")
add_if_exists(include_files, "en_README.md", "en_README.md")
add_if_exists(include_files, str(ICON_FILE), str(ICON_FILE))

for infnotebook_dir in INFNOTEBOOK_CANDIDATES:
    if not infnotebook_dir.exists():
        continue
    add_if_exists(
        include_files,
        str(infnotebook_dir / "screenshot.py"),
        "infnotebook/screenshot.py",
    )
    add_if_exists(include_files, str(infnotebook_dir / "define.py"), "infnotebook/define.py")
    add_if_exists(include_files, str(infnotebook_dir / "result.py"), "infnotebook/result.py")
    add_if_exists(include_files, str(infnotebook_dir / "resources"), "infnotebook/resources")
    break


build_exe_options = {
    "packages": [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PIL",
        "bs4",
        "google.cloud.storage",
        "imagehash",
        "keyboard",
        "numpy",
        "obsws_python",
        "requests",
        "websocket",
        "websockets",
    ],
    "includes": [
        "src.classes",
        "src.config",
        "src.config_dialog",
        "src.credentials_loader",
        "src.database_sqlite",
        "src.define",
        "src.direct_window_capture",
        "src.funcs",
        "src.logger",
        "src.main_window",
        "src.obs_control",
        "src.obs_dialog",
        "src.obs_websocket_manager",
        "src.portal_manager",
        "src.portal_uploaded_scores",
        "src.result",
        "src.result_database",
        "src.result_stats_writer",
        "src.rival_data",
        "src.score_viewer",
        "src.screen_reader",
        "src.songinfo",
        "src.storage",
        "src.summary_generator",
        "src.ui_en",
        "src.ui_jp",
        "src.update",
        "src.volforce",
        "src.websocket_server",
    ],
    "excludes": [
        "matplotlib",
        "pandas",
        "pip",
        "setuptools",
        "test",
        "unittest",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtOpenGL",
        "PySide6.QtPrintSupport",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
    ],
    "include_files": include_files,
    "include_msvcr": True,
    "zip_include_packages": [],
    "zip_exclude_packages": ["obsws_python", "PySide6"],
    "optimize": 2,
    "build_exe": FREEZE_BUILD_DIR,
}


base = "gui" if sys.platform == "win32" else None


class build_exe(cx_build_exe):
    """Build in a clean staging directory, then copy into sdvx_helper/."""

    def run(self) -> None:
        super().run()
        src = Path(FREEZE_BUILD_DIR)
        dst = Path(BUILD_DIR)
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)


executables = [
    Executable(
        script=ENTRY_POINT,
        base=base,
        target_name=EXE_NAME,
        icon=str(ICON_FILE) if ICON_FILE.exists() else None,
        shortcut_name=PROJECT_NAME,
        shortcut_dir="DesktopFolder",
    )
]


setup(
    name=PROJECT_NAME,
    version="2.0.0",
    description="SOUND VOLTEX play log helper",
    options={"build_exe": build_exe_options},
    executables=executables,
    cmdclass={"build_exe": build_exe},
)
