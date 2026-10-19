# Nightfall

An offline desktop tool for Halloween house projection mapping on Linux and Windows. Align polygon contours to a house, preview animated effects, and export matching 800 × 1280 portrait videos. The interface and documentation are in English.

| Day reference | Night reference |
| --- | --- |
| ![Generated example house in daylight](examples/house-day.png) | ![The same generated example house at night](examples/house-night.png) |

These are AI-generated examples based on the example configuration's polygon layout. The night example uses a real night photograph only as a reference for lighting, exposure and phone-camera quality; its fictional house and composition come from the generated example, and the streetlight is omitted. The example preserves the configured roof, windows, bay and foreground tree; it still needs alignment on a real projector.

## Run a downloaded executable

Download the Linux or Windows archive from **Releases**, or from a **build** run under **Actions**, and extract the entire `nightfall` folder. Keep the executable and `_internal` folder together.

- **Windows:** open `nightfall.exe`.
- **Linux:** run `./nightfall`. The `.tar.gz` archive preserves its executable permission.

The **Windows 11 64-bit package is self-contained**: Python, Qt, NumPy, FFmpeg, FFprobe, the effects and the example configuration are included. Extract the ZIP and double-click `nightfall.exe`. No Python installation, codec installation, administrator access or internet connection is needed to use it. Keep the complete extracted folder together.

The Linux build requires **FFmpeg with libx264** on your system for video export and MP4 playback. Live previews work without it. Alternatively, place `ffmpeg` and `ffprobe` in a `bin` folder alongside the executable.

On Ubuntu/Debian, install `ffmpeg libegl1 libopengl0 libxcb-cursor0`. On Fedora, use an FFmpeg package with the libx264 encoder and install `mesa-libEGL`, `libglvnd-opengl` and `xcb-util-cursor` if needed.

## Run from source

Use Python 3.14 and install FFmpeg for video export and playback:

```bash
python -m venv .venv
# Linux:
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m nightfall
# Windows:
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m nightfall
```

`./start.sh` and `start-windows.bat` provide shortcuts. Open your own configuration by passing its path:

```bash
.venv/bin/python -m nightfall path/to/house.json
```

`calibrate.py` remains a compatibility launcher. Personal configurations can contain embedded photographs: store them in `private/` and keep them out of Git.

## Align and play

Set the projector's extended desktop to **800 × 1280**, portrait, at **100%** scaling. Open a mapping with **Open**, select a corner or contour, and drag to adjust it. The reference image stays on the laptop. The projector receives only the masked output.

On Windows, use **Win+P → Extend** and choose the projector in **Projector display** in Nightfall. With one external display, Nightfall selects it automatically. The output covers the complete selected screen, including when it is rotated or uses a different display scale from the laptop. Windows handles the display rotation; no extra rotation is needed in Nightfall. Changing the display selection also moves an active projection to that screen.

- Arrow keys move by 1 pixel; Shift moves by 10 pixels; Ctrl moves by ¼ pixel.
- Tab selects the next corner. Ctrl+Z undoes an edit; Ctrl+S saves.
- The wheel zooms, the middle button pans, and `0` fits the view.
- **Reference: day/night** switches reference images without changing projector geometry.
- **Projector on** enables output; clicking it again blacks out the projector. Esc hides the output.
- **Video → Open video file…** plays an existing MP4. **Preview on this screen only** keeps playback and the FPS readout on the main screen without opening fullscreen projector output. The large readout reports frames actually painted by the app over a two-second window; it does not measure the monitor refresh rate.
- Choose **Video player → VLC · projector** to play finished MP4s directly in VLC. Windows packages select VLC by default. Nightfall finds installed or portable VLC; **Choose VLC…** locates another copy. VLC is a separate optional installation, available from [VideoLAN](https://www.videolan.org/vlc/).
- VLC opens on the selected **Projector display**, fullscreen and looping, with titles and controls hidden. Windows supplies portrait rotation; the video keeps its aspect ratio. Nightfall's FPS counter applies to internal playback and previews; it does not measure external VLC.
- **Stop video**, closing Nightfall, or disconnecting the projector stops the VLC instance that Nightfall started. Other VLC sessions keep running. **Projector off** stops VLC and leaves a black output; **Projector on** restarts the video from the beginning. Changing the projector display also restarts playback on that display.
- **Video** also starts an effect or the Halloween tour. The tour changes from the children's show to the braver visitors' show at the configured local time.
- **Render video** exports both two-minute shows from the current mapping. It becomes **Stop render** while rendering. Completed videos remain intact when a render is cancelled.

Smoke uses a fixed 50% strength. The old lamp-post placeholder is removed when older projects are opened because the street light is outside the projector coverage.

Glass, the bay front and exclusion masks stay black as configured. A window needs a reflective screen before it can receive projection. Save your aligned mapping and matching `.alignment.png` together. Reference images are embedded when a loaded project is saved, so personal projects remain portable.

Packaged builds keep render caches in `%LOCALAPPDATA%/Nightfall/renders` on Windows and `${XDG_DATA_HOME:-~/.local/share}/Nightfall/renders` on Linux. Source runs use `renders/` in the project directory.

Completed shows can also travel in a `videos/` folder beside the saved house mapping. Keep their `render-manifest.json`: Nightfall automatically uses these videos, including for the scheduled tour, when the geometry, effects, source code and assets match. Editing the map invalidates that match.

## Test playback on this computer

Open an existing video directly, with a visible main-screen FPS counter:

```bash
./start.sh --preview-only --video path/to/video.mp4
```

On Windows, use `nightfall.exe --preview-only --video path\to\video.mp4`. The player preserves the source video's cadence; it does not generate extra frames to turn 30 fps video into 60 fps. Live preview renders effects on demand and is measured separately from video playback.

Rendering defaults to one or two CPU workers, drops to one when available memory is low or cannot be measured, and limits encoder threads. No dedicated GPU is required. An older computer may render slower than real time: render the shows first, then play the completed videos. A 60 fps file does not guarantee 60 displayed frames per second on every computer; use the FPS counter to check the target machine.

## Characters and architectural animation

Both two-minute exports contain changing scenes with one-second background dissolves. The 4–8 show includes the original friendly young skeleton and cloth ghost, pumpkins, will-o-the-wisps, owls, light waves and a breathing house. The 8–12 show adds mysterious spirits, bats, a large spider, local flicker, clockwork windows, fire and Cheshire. **Video** also offers all twelve new scenes separately, plus a twelve-scene complete show.

Each performer gets a separate clear patch of brickwork with enough room for its complete pose, tilt and movement. Large silhouettes, fixed proportions and broad bright architectural accents suit distant projection on dim brickwork. A cramped wall omits additional performers; the background tree is subdued. Window, tree and exclusion clearance are checked throughout the motion. During a scene change, the outgoing cast fades out before the next cast appears, while background colours dissolve smoothly. Loose horizontal light bands are removed.

The children's opening is a small play using the actual house: a skeleton greets visitors from the bay ledge, simple ivory and mint ghosts follow closed routes around the attic and right window, candles flicker on the reflective curtain strips, and two pumpkins take turns hopping on the bay ledge. The later owl perches on that ledge too. Actor feet and pumpkin bases are anchored to the measured support line. Window orbits check the whole silhouette against masonry, glass, tree and exclusion masks; a blocked passage omits that flight. The spiders hang on threads from the actual gable edge, and the old line-drawn bats are replaced by textured, articulated bats with mirrored wings.

Character motion uses full five-second cycles evaluated at 60 fps: **300 rendered frames per cycle**. The image-generated textures supply the detail; articulated bones, shoulders and legs, squash, turns and ribbon deformation supply continuous in-between motion. The source images and exact prompts are documented in [character animation assets](assets/ANIMATION-PROMPTS.md).

The saved mapping stays fixed. Breathing contours, traveling waves, rotating light and flickering chases are clipped inside the actual window frames, roof edge and bay trim. Rotating patterns on reflective paper or curtains also stay inside their mapped surfaces; untreated glass and exclusion masks remain black.

To inspect the character loops outside the app:

```bash
python tools/preview_animations.py --frames
```

This creates a five-second 60 fps video contact sheet, eight sets of 300 transparent PNGs and a ZIP under `dist/previews/expanded-effects/`.

## Offline export

```bash
.venv/bin/python -m nightfall --render examples/house.json --out videos --show both
```

Use `--seconds 2` for a short preview, `--workers 2` to limit CPU workers, or `--patterns-only` to export alignment patterns without FFmpeg. Outputs include the mapping snapshot and a manifest with geometry, source and asset hashes. Existing files require an explicit `--overwrite`.

For a packaged build, use `./nightfall --render ...` or `nightfall.exe --render ...`.

## Development and builds

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python tools/build.py
```

On Windows, set `QT_QPA_PLATFORM=offscreen` before running tests. Tests require both `ffmpeg` and `ffprobe`; they generate their own test video and use only synthetic reference images.

On Windows, run `python tools/fetch_windows_ffmpeg.py` before `python tools/build.py`. This downloads a pinned static FFmpeg essentials package, verifies its SHA-256, and retains the provider notices. Windows packaging fails if either media tool or the libx264 encoder is missing. The packaged Windows test extracts the ZIP into a path containing spaces, clears `PATH`, renders 60 fps videos with multiple workers, probes them and decodes video back into the GUI.

The build produces `dist/nightfall/` and a Linux `.tar.gz` or Windows `.zip`. From a different working directory, run the executable with `--smoke-test` to exercise its references, effects, GUI and renderer subprocess, including multiple render workers when FFmpeg is available. Add `--require-bundled-media` for the Windows standalone check.

The GitHub Actions workflow follows Laterna's folder-based PyInstaller build: Linux and Windows builds on `main`, pull requests, or manual dispatch; downloadable archives; a `v*` tag publishes both archives as release downloads. Public-file checks and regression tests run before packaging.

## Project layout

```text
nightfall/             Desktop editor, effects, video playback and exporter
assets/                Runtime character sprites and atmosphere textures
examples/              Sanitized configuration and generated reference images
tests/                 Regression tests and sanitized geometry fixtures
tools/                 Build and public-file audit utilities
.github/workflows/     Linux/Windows builds and tagged releases
private/               Local-only projects, photographs and archived research (ignored)
```

The public tree contains the resulting tool and its examples. Local photographs, calibration observations, research scripts, old renders, packages and personal project files belong in the ignored `private/` directory. See [asset provenance](assets/README.md) for generation details.

Nightfall opens older Nachtwerk mapping files as well as its own project format.

## License

MIT: use it for whatever you like. © 2026 Bram Stoeller
<bram.stoeller@brainbuilders.nl>
