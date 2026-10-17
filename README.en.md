# HSJ Converter

[中文](README.md) · English

Convert multi-layer **画世界Pro `.hsj`** drafts into **PSD / ORA** for desktop
drawing applications.

- **PSD**: Photoshop, Krita, Clip Studio Paint, SAI, etc.
- **ORA**: Krita, GIMP, MyPaint, and other OpenRaster applications.

Layer pixels, Chinese layer names, ordering, opacity, visibility, blend modes,
clipping masks, and the canvas background layer are preserved. A merged preview
is included. Everything runs locally; drafts are never uploaded.

This is an independent interoperability project, not affiliated with the
developers of 画世界Pro. No proprietary APK, sample artwork, or reverse-engineered
commercial binaries are included in this repository.

## Features

| Feature | Windows | Android |
| --- | :---: | :---: |
| PSD / ORA / both | ✅ | ✅ |
| Layer tree (groups, visibility, opacity, blend, clip, lock alpha) | ✅ | ✅ |
| Background layer / overwrite confirmation / logs | ✅ | ✅ |
| CLI | ✅ | — |
| Open or share `.hsj` from file managers | ✅ | ✅ (SAF) |
| Background conversion with progress and cancellation | ✅ | ✅ |
| 6000×6000 multi-layer drafts | ✅ | ✅ |

## Downloads

Source is provided in this repository. Windows installers and the Android APK
may be available under
[Releases](https://github.com/Yi-Fan-miau/change-.hsj-to-.psd-or-.ora-tools/releases).
If no assets are attached, build them with the instructions below.

## Quick start (Windows source)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
python tools/make_icons.py
python hsj2psd_gui.py
```

CLI:

```bash
python hsj2psd.py draft.hsj
python hsj2psd.py draft.hsj --format both -o output/draft
python hsj2psd.py draft.hsj --list
```

## Android

```bash
cd android
python tools/make_android_icons.py
gradle :app:assembleRelease
adb install -r app/build/outputs/apk/release/app-release.apk
```

Requires JDK 21, Android SDK 36, and Gradle 8.14.5. The Gradle wrapper jar is
not committed; install Gradle or run `gradle wrapper`. See
[android/README.md](android/README.md) for details.

## Build Windows exe / installer

```bash
pip install -r requirements.txt pyinstaller
python packaging/build_exe.py
python packaging/build_installer.py
```

Generated icons, installer art, the Gradle wrapper jar, sample drafts, and
build outputs are deliberately excluded from the repository. The scripts
recreate them.

## Format

See [docs/hsj-format.md](docs/hsj-format.md) for the reverse-engineered
container, protobuf, strip, and compression details.

## Verification

- Metadata, layer trees, and per-layer pixel SHA-256 values match the Python
  reference for all sample formats;
- PSD/ORA layer pixels match exactly; merged previews differ by at most 1–2 LSB;
- A 6000×6000 draft completes on Android in about 22 seconds and opens in
  Krita 5.2.13 and psd-tools;
- The release APK was verified end-to-end through SAF, including writing both
  formats to a user-selected folder.

## License

[Apache License 2.0](LICENSE). Third-party notices are in [NOTICE](NOTICE).

## Disclaimer

Use this tool only for drafts you created or are authorized to process.
The authors are not responsible for data loss, compatibility issues, or
license violations caused by misuse.
