# CUA_Collector

version 2.2 

![Demo](Demo.gif)
![WindowsDemo](WindowsDemo.gif)

Current root is the automated collector formerly developed under `V2/`.

Legacy manual collector is archived under [`V1/`](./V1) and deprecated.

## Root Layout

```text
.
├── collector.py          # current automated collector entrypoint
├── cross_platform_capture.py
│                         # V2 mss+pynput backend for X11/Windows/macOS
├── run.sh                # Ubuntu Wayland/GNOME launcher
├── run_x11.sh            # Linux Xorg/X11 launcher
├── run_win.sh            # Windows launcher (Git Bash/MSYS/Cygwin)
├── run_mac.sh            # macOS launcher
├── CMakeLists.txt        # native module build
├── include/ src/ tests/  # C++ capture engine
├── data/                 # current collector output
└── V1/                   # deprecated archived collector
```

## Quick Start

All launchers run the root V2 collector and keep the same usage style:

```bash
./run.sh
./run_x11.sh
./run_win.sh
./run_mac.sh
```

Extra collector arguments are passed through, for example:

```bash
./run_x11.sh --data-dir ./data_x11 --fps 5
```

### Ubuntu Wayland / GNOME

```bash
git clone https://github.com/Zdong104/CUA_Collector.git
cd CUA_Collector
bash setup.sh

# log out and log back in once

./run.sh
```

If you already installed dependencies manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cmake -S . -B build -DPython3_EXECUTABLE=$PWD/.venv/bin/python3
cmake --build build -j$(nproc)
bash setup_extension.sh

# log out and log back in once

./run.sh
```

This path uses the native V2 backend: PipeWire for screenshots and libevdev for
input events.

### Linux Xorg / X11

```bash
git clone https://github.com/Zdong104/CUA_Collector.git
cd CUA_Collector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

./run_x11.sh
```

This path uses the V2 cross-platform backend: `mss` for screenshots and
`pynput` for input events. It does not require the C++ `cua_capture` build.

### Windows

Use Git Bash/MSYS/Cygwin for the `.sh` launcher:

```bash
git clone https://github.com/Zdong104/CUA_Collector.git
cd CUA_Collector
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

./run_win.sh
```

Windows may require allowing Python/Terminal through privacy or security prompts
before global input monitoring works.

### macOS

```bash
git clone https://github.com/Zdong104/CUA_Collector.git
cd CUA_Collector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

./run_mac.sh
```

Grant Screen Recording and Accessibility permissions to the terminal app or
Python executable in System Settings. Restart the launcher after changing those
permissions.

## Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+F8` | Start a new task |
| `Ctrl+F12` | End current task |
| `Ctrl+C` | Quit |

The current collector captures actions automatically while a task is active.
On all V2 launchers, `Ctrl+F9` is not needed.

## Output

```text
data/
  index.json
  <task_id>/
    task.json
    screenshots/
      action_0001_before.png
      action_0001_after.png
```

## Legacy V1

The original manual collector, setup scripts, and its existing datasets live in
[`V1/`](./V1), but V1 is deprecated. New platform launchers use the root V2
collector instead.


## Citation

```bibtex
@misc{dong2026cuacollector,
  author = {Zihan Dong},
  title = {ComputerUseAgent_Collector},
  year = {2026},
  note = {Computer Use Agent behavior cloning tool}
}
```

## License

Commercial Use: let's discuss by puma122707@gmail.com.

Non-Commercial Use: free.

Research Use: free.
