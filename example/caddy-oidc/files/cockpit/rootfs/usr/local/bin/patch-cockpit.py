import sys
from pathlib import Path


def patch(path, old, new, label):
    text = path.read_text()
    if old not in text:
        print(f"FATAL: patch failed to match in {path}: {label}", file=sys.stderr)
        sys.exit(1)
    path.write_text(text.replace(old, new))


def insert_before_head(path, snippet, marker):
    text = path.read_text()
    if marker not in text:
        text = text.replace("</head>", snippet + "</head>")
        path.write_text(text)


login_html = Path("/usr/share/cockpit/static/login.html")
login_html.write_text(Path("/usr/local/share/atomixos-cockpit/login.html").read_text())

bootloader = next(Path("/usr/lib").glob("python*/site-packages/cockpit/_vendor/bei/bootloader.py"))
patch(
    bootloader,
    "        import lzma\n        import sys\n",
    "        import lzma\n        import os\n        import sys\n",
    "bootloader: add os import",
)
patch(
    bootloader,
    "            src = lzma.decompress(src_xz)\n",
    "            os.environ['LD_LIBRARY_PATH'] = '/run/current-system/sw/lib:' "
    "+ os.environ.get('LD_LIBRARY_PATH', '')\n"
    "            src = lzma.decompress(src_xz)\n",
    "bootloader: inject LD_LIBRARY_PATH",
)

libsystemd = next(Path("/usr/lib").glob("python*/site-packages/cockpit/_vendor/systemd_ctypes/libsystemd.py"))
patch(
    libsystemd,
    'libsystemd = ctypes.CDLL("libsystemd.so.0")',
    'try:\n'
    '    libsystemd = ctypes.CDLL("libsystemd.so.0")\n'
    'except OSError:\n'
    '    libsystemd = ctypes.CDLL("/run/current-system/sw/lib/libsystemd.so.0")',
    "libsystemd: fallback CDLL path",
)

superuser = next(Path("/usr/lib").glob("python*/site-packages/cockpit/superuser.py"))
patch(
    superuser,
    '                ("ExecStart", {"t": "a(sasb)", "v": [(shutil.which(args[0]), args, False)]}),\n',
    '                ("Environment", {"t": "as", "v": [\n'
    '                    "PATH=/run/current-system/sw/bin:/run/wrappers/bin:'
    '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",\n'
    '                    "LD_LIBRARY_PATH=/run/current-system/sw/lib",\n'
    '                    "XDG_DATA_DIRS=/data/cockpit/share:/usr/local/share:/usr/share",\n'
    '                ]}),\n'
    '                ("ExecStart", {"t": "a(sasb)", "v": [(shutil.which(args[0]), args, False)]}),\n',
    "superuser: inject NixOS environment",
)

beipack_files = list(Path("/usr/lib").glob("python*/site-packages/cockpit/data/cockpit-bridge.beipack.xz"))
if not beipack_files:
    print("WARNING: no beipack files found to remove; bridge may use stale beipack", file=sys.stderr)
for beipack in beipack_files:
    beipack.unlink()

podman_manifest = Path("/usr/share/cockpit/podman/manifest.json")
patch(
    podman_manifest,
    '    "conditions": [\n        {"path-exists": "/lib/systemd/system/podman.socket"}\n    ],\n',
    "",
    "podman manifest: remove socket condition",
)
patch(
    podman_manifest,
    ',\n    "capabilities": ["service-filtering"]',
    "",
    "podman manifest: remove service-filtering capability",
)

# Some Cockpit app entrypoints do not load the documented branding.css file.
# Keep this targeted to app HTML; the shell itself is selected by Shell=.
branding_css = '<link href="../../static/branding.css" rel="stylesheet">\n'
for html in Path("/usr/share/cockpit").glob("*/*.html"):
    if html.match("*/shell/index.html") or html.match("*/atomixos-shell/index.html"):
        continue
    insert_before_head(html, branding_css, "branding.css")
