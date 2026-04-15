"""
Platform-specific backends for screenshot, cursor tracking, and input monitoring.
Supports: Windows, macOS, Linux (X11), Linux (Wayland/GNOME)
"""
import os
import sys
import re
import time
import platform
import subprocess
import shutil
import threading
from typing import Tuple, Optional, Dict, Callable

# ============================================================
# Platform Detection
# ============================================================

def detect_platform() -> Tuple[str, str]:
    """Returns (os_name, session_type)."""
    system = platform.system().lower()
    if system == 'windows':
        return 'windows', 'windows'
    elif system == 'darwin':
        return 'macos', 'macos'
    elif system == 'linux':
        session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
        if session_type == 'wayland':
            desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
            if 'gnome' in desktop:
                return 'linux', 'wayland-gnome'
            elif 'kde' in desktop:
                return 'linux', 'wayland-kde'
            elif 'sway' in desktop:
                return 'linux', 'wayland-sway'
            return 'linux', 'wayland'
        return 'linux', 'x11'
    return system, 'unknown'


OS_NAME, SESSION_TYPE = detect_platform()


def get_screen_resolution() -> Tuple[int, int]:
    """Get the resolution of the current/primary monitor (not the combined virtual desktop).

    On multi-monitor setups the combined virtual desktop (e.g. 9840x3840) differs
    from the individual monitor resolution (e.g. 3840x2400).  Since screenshots
    and cursor coordinates are relative to a single monitor, we need the latter.
    """
    try:
        if SESSION_TYPE in ('windows', 'macos', 'x11'):
            import mss
            with mss.mss() as sct:
                # monitors[0] is the combined virtual screen; monitors[1] is the primary
                if len(sct.monitors) > 1:
                    m = sct.monitors[1]  # primary monitor
                else:
                    m = sct.monitors[0]
                return (m['width'], m['height'])
    except Exception:
        pass

    # Wayland: try multiple methods to get the primary monitor resolution
    # Method 1: Parse individual monitor outputs from xrandr
    try:
        r = subprocess.run(['xrandr', '--current'], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            best_res = None
            in_connected_output = False
            is_primary = False
            for line in r.stdout.splitlines():
                if ' connected' in line:
                    in_connected_output = True
                    is_primary = 'primary' in line
                    header_match = re.search(r'(\d{3,5})x(\d{3,5})\+', line)
                    if header_match:
                        res = (int(header_match.group(1)), int(header_match.group(2)))
                        if is_primary or best_res is None:
                            best_res = res
                            if is_primary:
                                break
                elif ' disconnected' in line:
                    in_connected_output = False
                    is_primary = False
                elif in_connected_output and '*' in line:
                    mode_match = re.match(r'\s+(\d{3,5})x(\d{3,5})', line)
                    if mode_match:
                        res = (int(mode_match.group(1)), int(mode_match.group(2)))
                        if is_primary or best_res is None:
                            best_res = res
                            if is_primary:
                                break
            if best_res:
                return best_res
    except Exception:
        pass

    # Method 2: Try gnome-randr (available on some GNOME Wayland setups)
    try:
        r = subprocess.run(['gnome-randr'], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            # Look for active mode line, e.g. "  3840x2400@60.000  *"
            for line in r.stdout.splitlines():
                if '*' in line:
                    m = re.search(r'(\d{3,5})x(\d{3,5})', line)
                    if m:
                        return (int(m.group(1)), int(m.group(2)))
    except Exception:
        pass

    # Method 3: Try wlr-randr (wlroots compositors like Sway)
    try:
        r = subprocess.run(['wlr-randr'], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if 'current' in line.lower():
                    m = re.search(r'(\d{3,5})x(\d{3,5})', line)
                    if m:
                        return (int(m.group(1)), int(m.group(2)))
    except Exception:
        pass

    return (1920, 1080)


# ============================================================
# Screenshot Backend
# ============================================================

class Screenshotter:
    """Cross-platform screenshot utility with automatic backend selection."""

    def __init__(self):
        self._wayland_backend = None
        self.method = self._detect_method()
        print(f"  📷 Screenshot backend: {self.method}")

    def _detect_method(self) -> str:
        if SESSION_TYPE in ('windows', 'macos', 'x11'):
            return 'mss'
        # Wayland: use PipeWire screencast (one-time approval, then free capture)
        if SESSION_TYPE.startswith('wayland'):
            return 'pipewire'
        # Fallback
        if shutil.which('grim'):
            return 'grim'
        return 'mss'

    def init_wayland(self):
        """Initialize Wayland screenshot backend. Call after startup banner."""
        if self.method == 'pipewire':
            from screenshot_wayland import create_wayland_screenshotter
            self._wayland_backend = create_wayland_screenshotter()
            self.method = 'pipewire' if self._wayland_backend else 'mss'

    def capture(self, output_path: str) -> bool:
        """Take a screenshot and save to output_path. Returns True on success."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            if self.method == 'pipewire' and self._wayland_backend:
                return self._wayland_backend.capture(output_path)
            elif self.method == 'mss':
                return self._capture_mss(output_path)
            elif self.method == 'grim':
                return subprocess.run(['grim', output_path], capture_output=True, timeout=10).returncode == 0
            elif self.method == 'gnome-screenshot-cli':
                return subprocess.run(['gnome-screenshot', '-f', output_path], capture_output=True, timeout=10).returncode == 0
        except Exception as e:
            print(f"  ❌ Screenshot error ({self.method}): {e}")
        return False

    def stop(self):
        """Clean up screenshot resources."""
        if self._wayland_backend:
            self._wayland_backend.stop()

    def _capture_mss(self, output_path: str) -> bool:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            img.save(output_path, "PNG")
        return True


# ============================================================
# Cursor Position Backend
# ============================================================

class CursorTracker:
    """Cross-platform cursor position tracking.

    On Wayland GNOME, cursor coordinates from global.get_pointer() are in the
    global *logical* coordinate space spanning all monitors.  Screenshots are
    captured at the monitor's *native pixel* resolution.

    With the v2 CUA extension (GetPositionPixel), coordinates are already
    converted to monitor-relative pixel space.  For fallback methods (gnome-eval,
    v1 extension), we read the primary monitor's offset and scale from
    monitors.xml and transform coordinates in Python.

    Detection order on Wayland:
      1. cursor-tracker@cua extension v2 (GetPositionPixel – best)
      2. cursor-tracker@cua extension v1 (GetPosition + Python transform)
      3. org.gnome.Shell.Eval            (+ Python transform)
      4. pynput                          (broken on Wayland, last resort)
    """

    def __init__(self):
        self._pixel_method = False  # True if using GetPositionPixel
        self._monitor_native_res = None  # (w, h) in native pixels
        # Monitor geometry for coordinate transform (v1 fallback)
        self._monitor_offset = (0, 0)  # (x, y) logical offset in compositor
        self._monitor_logical_size = None  # (w, h) logical size
        self._monitor_scale = 1.0  # scale factor (native / logical)
        self._load_monitor_geometry()

        self.method = self._detect_method()
        print(f"  🖱️  Cursor tracking: {self.method}"
              + (" (pixel coords)" if self._pixel_method else ""))
        if not self._pixel_method and self._monitor_scale != 1.0:
            print(f"  📐 Monitor offset: {self._monitor_offset}, "
                  f"scale: {self._monitor_scale}x "
                  f"(native: {self._monitor_native_res})")
        if self.method == 'pynput' and SESSION_TYPE.startswith('wayland'):
            print("  ⚠️  pynput cursor tracking is unreliable on Wayland!")
            print("     Install the CUA extension: see README or run setup_extension.sh")

    def _load_monitor_geometry(self):
        """Detect primary monitor geometry from the running GNOME compositor.

        Uses org.gnome.Mutter.DisplayConfig.GetCurrentState D-Bus API which
        returns the live monitor layout, including:
         - logical offset (x, y) of each monitor in compositor space
         - scale factor (e.g. 2.0 for HiDPI)
         - primary flag
         - connected output names

        Falls back to parsing monitors.xml if D-Bus is unavailable.
        """
        if not SESSION_TYPE.startswith('wayland'):
            return

        # Try live D-Bus query first (most reliable)
        if self._load_from_mutter_dbus():
            return

        # Fallback: parse monitors.xml
        self._load_from_monitors_xml()

    def _load_from_mutter_dbus(self) -> bool:
        """Load monitor geometry from org.gnome.Mutter.DisplayConfig.GetCurrentState."""
        try:
            r = subprocess.run([
                'gdbus', 'call', '--session',
                '--dest', 'org.gnome.Mutter.DisplayConfig',
                '--object-path', '/org/gnome/Mutter/DisplayConfig',
                '--method', 'org.gnome.Mutter.DisplayConfig.GetCurrentState',
            ], capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                return False

            text = r.stdout

            # Parse logical monitors section: [(x, y, scale, transform, primary, [(connector, vendor, product, serial)], props), ...]
            # We look for the primary monitor (has 'true' after the transform uint32)
            # Pattern: (x, y, scale, uint32 N, true, [('connector', ...
            primary_match = re.search(
                r'\((\d+),\s*(\d+),\s*([\d.]+),\s*(?:uint32\s+)?\d+,\s*true,\s*\[\(\'([^\']+)\'',
                text
            )
            if not primary_match:
                return False

            offset_x = int(primary_match.group(1))
            offset_y = int(primary_match.group(2))
            scale = float(primary_match.group(3))
            connector = primary_match.group(4)

            self._monitor_offset = (offset_x, offset_y)
            self._monitor_scale = scale

            # Now find the monitor mode resolution for this connector
            # Monitors section has: ('connector', 'vendor', 'product', 'serial'), [modes...], properties
            # Find the active mode for this connector by looking for a mode with 'is-current' property
            # For simplicity, parse the connector's mode width/height from the output
            # The mode entries look like: ('WxH@rate', W, H, rate, preferred_scale, ...)
            # Find the connector section and its first (native) mode
            connector_pattern = rf"'{re.escape(connector)}'"
            conn_idx = text.find(connector_pattern)
            if conn_idx > 0:
                # Find modes after this connector - look for WxH patterns
                # The first mode after 'is-builtin' property is usually the list
                # Find active mode width/height - look for resolution modes
                modes_text = text[conn_idx:]
                # Find the first mode entry: ('3840x2400@60.002', 3840, 2400, ...)
                mode_match = re.search(r"\('(\d+)x(\d+)@[\d.]+',\s*\d+,\s*\d+", modes_text)
                if mode_match:
                    native_w = int(mode_match.group(1))
                    native_h = int(mode_match.group(2))
                    self._monitor_native_res = (native_w, native_h)

            # If we couldn't parse native resolution from modes, compute it from scale
            if not self._monitor_native_res and scale > 1.0:
                # We need the logical size - try to compute from scale
                # Look at xrandr for the mode if available
                native = self._get_native_resolution_xrandr(connector)
                if native:
                    self._monitor_native_res = native
                    # Recalculate scale based on native vs logical
                    # logical_width = native_width / scale
                else:
                    # Can't determine native, but we have offset and scale
                    pass

            print(f"  📐 Primary monitor ({connector}): "
                  f"offset=({offset_x},{offset_y}), scale={scale}x"
                  + (f", native={self._monitor_native_res[0]}×{self._monitor_native_res[1]}"
                     if self._monitor_native_res else ""))
            return True

        except Exception as e:
            print(f"  ⚠️  Mutter D-Bus query failed: {e}")
            return False

    def _load_from_monitors_xml(self):
        """Fallback: parse monitors.xml to get primary monitor geometry."""
        import xml.etree.ElementTree as ET
        monitors_xml = os.path.expanduser('~/.config/monitors.xml')
        if not os.path.isfile(monitors_xml):
            return

        try:
            tree = ET.parse(monitors_xml)
            root = tree.getroot()

            # Get currently connected monitors from sysfs
            connected = set()
            drm_dir = '/sys/class/drm'
            if os.path.isdir(drm_dir):
                for entry in os.listdir(drm_dir):
                    status_file = os.path.join(drm_dir, entry, 'status')
                    if os.path.isfile(status_file):
                        try:
                            with open(status_file) as f:
                                if 'connected' == f.read().strip():
                                    # Extract connector name: card0-DP-1 -> DP-1
                                    parts = entry.split('-', 1)
                                    if len(parts) > 1:
                                        connected.add(parts[1])
                        except Exception:
                            pass

            # Find the configuration matching currently connected monitors
            best_config = None
            for config in root.findall('configuration'):
                config_connectors = set()
                for lmon in config.findall('logicalmonitor'):
                    conn_el = lmon.find('monitor/monitorspec/connector')
                    if conn_el is not None:
                        config_connectors.add(conn_el.text)
                # Check for disabled monitors too
                for disabled in config.findall('disabled'):
                    conn_el = disabled.find('monitorspec/connector')
                    if conn_el is not None:
                        config_connectors.add(conn_el.text)

                if config_connectors == connected or (connected and config_connectors.issuperset(connected)):
                    best_config = config
                    break

            if not best_config:
                # Fall back to last config
                configs = root.findall('configuration')
                if configs:
                    best_config = configs[-1]

            if not best_config:
                return

            # Find the primary monitor
            for lmon in best_config.findall('logicalmonitor'):
                primary_el = lmon.find('primary')
                if primary_el is None or primary_el.text != 'yes':
                    continue

                x = int(lmon.find('x').text)
                y = int(lmon.find('y').text)
                self._monitor_offset = (x, y)

                scale_el = lmon.find('scale')
                config_scale = float(scale_el.text) if scale_el is not None else 1.0

                mode = lmon.find('monitor/mode')
                if mode is not None:
                    logical_w = int(mode.find('width').text)
                    logical_h = int(mode.find('height').text)
                    self._monitor_logical_size = (logical_w, logical_h)

                    connector = lmon.find('monitor/monitorspec/connector')
                    if connector is not None:
                        native = self._get_native_resolution_xrandr(connector.text)
                        if native:
                            self._monitor_native_res = native
                            self._monitor_scale = native[0] / logical_w
                        elif config_scale != 1.0:
                            self._monitor_scale = config_scale
                            self._monitor_native_res = (
                                int(logical_w * config_scale),
                                int(logical_h * config_scale),
                            )
                        else:
                            self._monitor_native_res = (logical_w, logical_h)
                break
        except Exception as e:
            print(f"  ⚠️  Could not parse monitors.xml: {e}")

    def _get_native_resolution_xrandr(self, connector: str) -> Optional[Tuple[int, int]]:
        """Try to get the native (max) resolution for a display connector via xrandr."""
        try:
            r = subprocess.run(['xrandr', '--current'], capture_output=True, text=True, timeout=3)
            if r.returncode != 0:
                return None
            in_connector = False
            for line in r.stdout.splitlines():
                if line.startswith(connector + ' '):
                    in_connector = True
                    continue
                elif not line.startswith(' ') and in_connector:
                    break
                elif in_connector:
                    m = re.match(r'\s+(\d+)x(\d+)', line)
                    if m:
                        return (int(m.group(1)), int(m.group(2)))
        except Exception:
            pass
        return None

    def _detect_method(self) -> str:
        if SESSION_TYPE in ('windows', 'macos', 'x11'):
            return 'pynput'
        # Wayland: try extension first, then gnome-eval, then pynput
        if 'gnome' in SESSION_TYPE:
            if self._test_cua_pixel():
                self._pixel_method = True
                return 'cua-extension'
            if self._test_cua_extension():
                return 'cua-extension'
            if self._test_gnome_eval():
                return 'gnome-eval'
        return 'pynput'

    def _test_cua_pixel(self) -> bool:
        """Test if the v2 extension with GetPositionPixel is available."""
        try:
            r = subprocess.run([
                'gdbus', 'call', '--session',
                '--dest', 'org.cua.CursorTracker',
                '--object-path', '/org/cua/CursorTracker',
                '--method', 'org.cua.CursorTracker.GetPositionPixel',
            ], capture_output=True, text=True, timeout=2)
            if r.returncode == 0 and '(' in r.stdout:
                # Parse the native monitor resolution from the response
                nums = re.findall(r'-?\d+', r.stdout)
                if len(nums) >= 4:
                    self._monitor_native_res = (int(nums[2]), int(nums[3]))
                    print(f"  📐 Monitor native resolution from extension: "
                          f"{self._monitor_native_res[0]}×{self._monitor_native_res[1]}")
                return True
        except Exception:
            pass
        return False

    def _test_cua_extension(self) -> bool:
        try:
            r = subprocess.run([
                'gdbus', 'call', '--session',
                '--dest', 'org.cua.CursorTracker',
                '--object-path', '/org/cua/CursorTracker',
                '--method', 'org.cua.CursorTracker.GetPosition',
            ], capture_output=True, text=True, timeout=2)
            return r.returncode == 0 and '(' in r.stdout
        except Exception:
            return False

    def _test_gnome_eval(self) -> bool:
        try:
            r = subprocess.run([
                'gdbus', 'call', '--session',
                '--dest', 'org.gnome.Shell',
                '--object-path', '/org/gnome/Shell',
                '--method', 'org.gnome.Shell.Eval',
                'let [x,y]=global.get_pointer(); x+","+y'
            ], capture_output=True, text=True, timeout=3)
            # Eval returns (true, 'x,y') on success, (false, '') on failure
            return r.returncode == 0 and "(true," in r.stdout
        except Exception:
            return False

    def get_monitor_native_resolution(self) -> Optional[Tuple[int, int]]:
        """Return the native pixel resolution detected, or None."""
        return self._monitor_native_res

    def _transform_to_pixel(self, global_x: int, global_y: int) -> Tuple[int, int]:
        """Transform global logical coordinates to monitor-relative pixel coordinates."""
        # Subtract monitor offset to get monitor-relative logical coords
        local_x = global_x - self._monitor_offset[0]
        local_y = global_y - self._monitor_offset[1]
        # Scale to native pixel coordinates
        pixel_x = int(round(local_x * self._monitor_scale))
        pixel_y = int(round(local_y * self._monitor_scale))
        return (pixel_x, pixel_y)

    def get_position(self) -> Tuple[int, int]:
        if self.method == 'cua-extension':
            if self._pixel_method:
                return self._get_cua_pixel()
            return self._get_cua_extension_transformed()
        if self.method == 'gnome-eval':
            return self._get_gnome_eval_transformed()
        return self._get_pynput()

    def _get_cua_pixel(self) -> Tuple[int, int]:
        """Get monitor-relative pixel coordinates from v2 extension."""
        try:
            r = subprocess.run([
                'gdbus', 'call', '--session',
                '--dest', 'org.cua.CursorTracker',
                '--object-path', '/org/cua/CursorTracker',
                '--method', 'org.cua.CursorTracker.GetPositionPixel',
            ], capture_output=True, text=True, timeout=1)
            if r.returncode == 0:
                nums = re.findall(r'-?\d+', r.stdout)
                if len(nums) >= 4:
                    # Update cached native resolution
                    self._monitor_native_res = (int(nums[2]), int(nums[3]))
                    return (int(nums[0]), int(nums[1]))
        except Exception:
            pass
        return (0, 0)

    def _get_cua_extension_transformed(self) -> Tuple[int, int]:
        """Get global coords from v1 extension, then transform to pixel coords."""
        try:
            r = subprocess.run([
                'gdbus', 'call', '--session',
                '--dest', 'org.cua.CursorTracker',
                '--object-path', '/org/cua/CursorTracker',
                '--method', 'org.cua.CursorTracker.GetPosition',
            ], capture_output=True, text=True, timeout=1)
            if r.returncode == 0:
                nums = re.findall(r'-?\d+', r.stdout)
                if len(nums) >= 2:
                    return self._transform_to_pixel(int(nums[0]), int(nums[1]))
        except Exception:
            pass
        return (0, 0)

    def _get_gnome_eval_transformed(self) -> Tuple[int, int]:
        """Get global coords from Shell.Eval, then transform to pixel coords."""
        try:
            r = subprocess.run([
                'gdbus', 'call', '--session',
                '--dest', 'org.gnome.Shell',
                '--object-path', '/org/gnome/Shell',
                '--method', 'org.gnome.Shell.Eval',
                'let [x,y]=global.get_pointer(); x+","+y'
            ], capture_output=True, text=True, timeout=2)
            if r.returncode == 0 and "(true," in r.stdout:
                # Output: (true, '1234,567')
                match = re.search(r"'(\d+),(\d+)'", r.stdout)
                if match:
                    return self._transform_to_pixel(
                        int(match.group(1)), int(match.group(2)))
        except Exception:
            pass
        return (0, 0)

    def _get_pynput(self) -> Tuple[int, int]:
        try:
            from pynput.mouse import Controller
            return Controller().position
        except Exception:
            return (0, 0)


# ============================================================
# Input Monitor - Wayland (evdev)
# ============================================================

class WaylandInputMonitor:
    """Monitor keyboard and mouse input via evdev on Wayland."""

    def __init__(self, callbacks: Dict[str, Callable]):
        self.callbacks = callbacks
        self._running = False
        self._threads = []
        self._ctrl_pressed = False
        self._devices = []

        # Modifier key codes (for hotkey detection and state tracking).
        self._modifier_codes = set()

        # All key codes to human-readable names.
        # Previously this was a restrictive allowlist that silently dropped
        # letters/numbers/symbols — breaking combos like Ctrl+A, Shift+1, etc.
        self._key_names = {}

        # Active key tracking for state-based combo recording.
        self._active_keys = {}   # scancode -> key_name

    def start(self):
        import evdev
        from evdev import ecodes
        self._running = True
        all_devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

        for dev in all_devices:
            caps = dev.capabilities(verbose=True)
            is_keyboard = False
            is_mouse = False

            for key, events in caps.items():
                key_name = key[0] if isinstance(key, tuple) else key
                event_strs = [str(e) for e in events]
                if key_name == 'EV_KEY':
                    if any('KEY_A' in s for s in event_strs):
                        is_keyboard = True
                    if any('BTN_LEFT' in s for s in event_strs):
                        is_mouse = True
                if key_name == 'EV_REL':
                    if any('REL_WHEEL' in s for s in event_strs):
                        is_mouse = True

            if is_keyboard or is_mouse:
                self._devices.append((dev, is_keyboard, is_mouse))
                kind = []
                if is_keyboard:
                    kind.append('kbd')
                if is_mouse:
                    kind.append('mouse')
                print(f"  📡 Monitoring: {dev.name} ({'+'.join(kind)})")

        for dev, is_kbd, is_mouse in self._devices:
            t = threading.Thread(target=self._monitor_device, args=(dev, is_kbd, is_mouse), daemon=True)
            t.start()
            self._threads.append(t)

    def _build_key_name(self, scancode: int, dev) -> str:
        """Map an evdev scancode to a human-readable key name.
        Covers all standard keys: modifiers, letters, numbers, punctuation,
        function keys, navigation, and special keys."""
        import evdev
        from evdev import ecodes

        # ── Modifiers ────────────────────────────────────────────
        if scancode == ecodes.KEY_LEFTCTRL:   return "ctrl_l"
        if scancode == ecodes.KEY_RIGHTCTRL:  return "ctrl_r"
        if scancode == ecodes.KEY_LEFTSHIFT:  return "shift_l"
        if scancode == ecodes.KEY_RIGHTSHIFT: return "shift_r"
        if scancode == ecodes.KEY_LEFTALT:    return "alt_l"
        if scancode == ecodes.KEY_RIGHTALT:   return "alt_r"
        if scancode == ecodes.KEY_LEFTMETA:   return "super_l"
        if scancode == ecodes.KEY_RIGHTMETA:  return "super_r"

        # ── Special keys ─────────────────────────────────────────
        if scancode == ecodes.KEY_ESC:        return "esc"
        if scancode == ecodes.KEY_BACKSPACE:  return "backspace"
        if scancode == ecodes.KEY_DELETE:     return "delete"
        if scancode == ecodes.KEY_ENTER:      return "enter"
        if scancode == ecodes.KEY_TAB:        return "tab"
        if scancode == ecodes.KEY_SPACE:      return "space"
        if scancode == ecodes.KEY_CAPSLOCK:   return "capslock"
        if scancode == ecodes.KEY_INSERT:     return "insert"
        if scancode == ecodes.KEY_HOME:       return "home"
        if scancode == ecodes.KEY_END:        return "end"
        if scancode == ecodes.KEY_PAGEUP:     return "pageup"
        if scancode == ecodes.KEY_PAGEDOWN:   return "pagedown"
        if scancode == ecodes.KEY_LINEFEED:   return "linefeed"
        if scancode == ecodes.KEY_CLEAR:      return "clear"
        if scancode == ecodes.KEY_SYSRQ:      return "sysrq"
        if scancode == ecodes.KEY_SCROLLLOCK: return "scrolllock"
        if scancode == ecodes.KEY_PAUSE:      return "pause"
        if scancode == ecodes.KEY_PRINT:      return "print"
        if scancode == ecodes.KEY_MENU:       return "menu"
        if scancode == ecodes.KEY_FN:         return "fn"

        # ── Navigation / Arrow keys ─────────────────────────────
        if scancode == ecodes.KEY_UP:         return "up"
        if scancode == ecodes.KEY_DOWN:       return "down"
        if scancode == ecodes.KEY_LEFT:       return "left"
        if scancode == ecodes.KEY_RIGHT:      return "right"

        # ── Letters ─────────────────────────────────────────────
        letter_map = {
            ecodes.KEY_A: 'a', ecodes.KEY_B: 'b', ecodes.KEY_C: 'c',
            ecodes.KEY_D: 'd', ecodes.KEY_E: 'e', ecodes.KEY_F: 'f',
            ecodes.KEY_G: 'g', ecodes.KEY_H: 'h', ecodes.KEY_I: 'i',
            ecodes.KEY_J: 'j', ecodes.KEY_K: 'k', ecodes.KEY_L: 'l',
            ecodes.KEY_M: 'm', ecodes.KEY_N: 'n', ecodes.KEY_O: 'o',
            ecodes.KEY_P: 'p', ecodes.KEY_Q: 'q', ecodes.KEY_R: 'r',
            ecodes.KEY_S: 's', ecodes.KEY_T: 't', ecodes.KEY_U: 'u',
            ecodes.KEY_V: 'v', ecodes.KEY_W: 'w', ecodes.KEY_X: 'x',
            ecodes.KEY_Y: 'y', ecodes.KEY_Z: 'z',
        }
        if scancode in letter_map:
            return letter_map[scancode]

        # ── Numbers (top row, no shift) ────────────────────────
        num_map = {
            ecodes.KEY_1: '1', ecodes.KEY_2: '2', ecodes.KEY_3: '3',
            ecodes.KEY_4: '4', ecodes.KEY_5: '5', ecodes.KEY_6: '6',
            ecodes.KEY_7: '7', ecodes.KEY_8: '8', ecodes.KEY_9: '9',
            ecodes.KEY_0: '0',
        }
        if scancode in num_map:
            return num_map[scancode]

        # ── Punctuation / Symbols ───────────────────────────────
        punct_map = {
            ecodes.KEY_GRAVE:      '`',
            ecodes.KEY_MINUS:      '-',
            ecodes.KEY_EQUAL:      '=',
            ecodes.KEY_LEFTBRACE:  '[',
            ecodes.KEY_RIGHTBRACE: ']',
            ecodes.KEY_BACKSLASH:  '\\',
            ecodes.KEY_SEMICOLON:  ';',
            ecodes.KEY_APOSTROPHE: "'",
            ecodes.KEY_COMMA:      ',',
            ecodes.KEY_DOT:        '.',
            ecodes.KEY_SLASH:      '/',
            ecodes.KEY_102ND:      '102nd',
        }
        if scancode in punct_map:
            return punct_map[scancode]

        # ── Numpad keys ────────────────────────────────────────
        kp_map = {
            ecodes.KEY_KP0: 'kp_0', ecodes.KEY_KP1: 'kp_1',
            ecodes.KEY_KP2: 'kp_2', ecodes.KEY_KP3: 'kp_3',
            ecodes.KEY_KP4: 'kp_4', ecodes.KEY_KP5: 'kp_5',
            ecodes.KEY_KP6: 'kp_6', ecodes.KEY_KP7: 'kp_7',
            ecodes.KEY_KP8: 'kp_8', ecodes.KEY_KP9: 'kp_9',
            ecodes.KEY_KPASTERISK: 'kp_*',
            ecodes.KEY_KPSLASH:    'kp_/',
            ecodes.KEY_KPPLUS:     'kp_+',
            ecodes.KEY_KPMINUS:   'kp_-',
            ecodes.KEY_KPDOT:     'kp_.',
            ecodes.KEY_KPEQUAL:   'kp_=',
            ecodes.KEY_KPLEFTPAREN:  'kp_(',
            ecodes.KEY_KPRIGHTPAREN: 'kp_)',
            ecodes.KEY_KPENTER:   'kp_enter',
            ecodes.KEY_NUMLOCK:   'numlock',
        }
        if scancode in kp_map:
            return kp_map[scancode]

        # ── Function keys ──────────────────────────────────────
        fn_map = {
            ecodes.KEY_F1: 'f1',  ecodes.KEY_F2: 'f2',
            ecodes.KEY_F3: 'f3',  ecodes.KEY_F4: 'f4',
            ecodes.KEY_F5: 'f5',  ecodes.KEY_F6: 'f6',
            ecodes.KEY_F7: 'f7',  ecodes.KEY_F8: 'f8',
            ecodes.KEY_F9: 'f9',  ecodes.KEY_F10: 'f10',
            ecodes.KEY_F11: 'f11', ecodes.KEY_F12: 'f12',
            ecodes.KEY_F13: 'f13', ecodes.KEY_F14: 'f14',
            ecodes.KEY_F15: 'f15', ecodes.KEY_F16: 'f16',
            ecodes.KEY_F17: 'f17', ecodes.KEY_F18: 'f18',
            ecodes.KEY_F19: 'f19', ecodes.KEY_F20: 'f20',
            ecodes.KEY_F21: 'f21', ecodes.KEY_F22: 'f22',
            ecodes.KEY_F23: 'f23', ecodes.KEY_F24: 'f24',
        }
        if scancode in fn_map:
            return fn_map[scancode]

        # ── Media / AC keys ────────────────────────────────────
        media_map = {
            ecodes.KEY_PLAYPAUSE:    'playpause',
            ecodes.KEY_STOP:         'stop',
            ecodes.KEY_NEXTSONG:     'nextsong',
            ecodes.KEY_PREVIOUSSONG: 'prevsong',
            ecodes.KEY_MUTE:         'mute',
            ecodes.KEY_VOLUMEUP:     'volumeup',
            ecodes.KEY_VOLUMEDOWN:   'volumedown',
            ecodes.KEY_POWER:        'power',
            ecodes.KEY_WAKEUP:       'wakeup',
            ecodes.KEY_SLEEP:        'sleep',
            ecodes.KEY_EJECTCD:      'ejectcd',
            ecodes.KEY_BRIGHTNESSDOWN:   'brightnessdown',
            ecodes.KEY_BRIGHTNESSUP:    'brightnessup',
            ecodes.KEY_MICMUTE:      'micmute',
            ecodes.KEY_WWW:          'www',
            ecodes.KEY_MAIL:         'mail',
            ecodes.KEY_CALC:         'calc',
            ecodes.KEY_SEARCH:       'search',
            ecodes.KEY_HOMEPAGE:     'homepage',
            ecodes.KEY_BACK:         'browser_back',
            ecodes.KEY_FORWARD:      'browser_forward',
            ecodes.KEY_REFRESH:      'browser_refresh',
            ecodes.KEY_BOOKMARKS:    'browser_bookmarks',
            ecodes.KEY_ZOOMIN:       'zoom_in',
            ecodes.KEY_ZOOMOUT:      'zoom_out',
        }
        if scancode in media_map:
            return media_map[scancode]

        # Try evdev's built-in key name lookup as fallback
        try:
            name = dev.device.keycode(scancode)
            if isinstance(name, list) and name:
                return name[0].lower()
        except Exception:
            pass

        return ""  # Unknown — skip

    def _is_modifier(self, scancode: int) -> bool:
        import evdev
        from evdev import ecodes
        return scancode in (
            ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL,
            ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT,
            ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT,
            ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA,
        )

    def _monitor_device(self, device, is_keyboard: bool, is_mouse: bool):
        import evdev
        from evdev import ecodes

        try:
            for event in device.read_loop():
                if not self._running:
                    break

                if event.type == ecodes.EV_KEY:
                    key_event = evdev.categorize(event)
                    scancode = key_event.scancode
                    is_down = key_event.keystate == 1
                    is_up = key_event.keystate == 0

                    # Track Ctrl for hotkey detection
                    if scancode in (ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL):
                        self._ctrl_pressed = is_down

                    # Hotkeys on key-down
                    if is_down and self._ctrl_pressed:
                        if scancode == ecodes.KEY_F8:
                            threading.Thread(target=self.callbacks['on_hotkey_start_task'], daemon=True).start()
                        elif scancode == ecodes.KEY_F9:
                            threading.Thread(target=self.callbacks['on_hotkey_screenshot'], daemon=True).start()
                        elif scancode == ecodes.KEY_F12:
                            threading.Thread(target=self.callbacks['on_hotkey_end_task'], daemon=True).start()

                    # ESC (no Ctrl needed) to drop current action
                    if is_down and scancode == ecodes.KEY_ESC:
                        threading.Thread(target=self.callbacks['on_hotkey_drop_action'], daemon=True).start()

                    # ── ALL key events (no restrictive allowlist) ──
                    # Previously only modifiers were tracked, dropping letters/numbers.
                    if is_keyboard and (is_down or is_up):
                        name = self._build_key_name(scancode, device)
                        if name:
                            if is_down:
                                self._active_keys[scancode] = name
                            else:
                                self._active_keys.pop(scancode, None)

                            if 'on_key_event' in self.callbacks:
                                threading.Thread(
                                    target=self.callbacks['on_key_event'],
                                    args=(name, is_down),
                                    daemon=True
                                ).start()

                    # Mouse button press/release
                    if is_mouse:
                        btn_map = {
                            ecodes.BTN_LEFT: 'left',
                            ecodes.BTN_RIGHT: 'right',
                            ecodes.BTN_MIDDLE: 'middle',
                        }
                        if scancode in btn_map and (is_down or is_up):
                            if 'on_mouse_button' in self.callbacks:
                                threading.Thread(
                                    target=self.callbacks['on_mouse_button'],
                                    args=(btn_map[scancode], is_down),
                                    daemon=True
                                ).start()

                elif event.type == ecodes.EV_REL and is_mouse:
                    if event.code in (ecodes.REL_WHEEL, getattr(ecodes, 'REL_WHEEL_HI_RES', 11)):
                        self.callbacks['on_mouse_scroll'](0, event.value)
                    elif event.code in (ecodes.REL_HWHEEL, getattr(ecodes, 'REL_HWHEEL_HI_RES', 12)):
                        self.callbacks['on_mouse_scroll'](event.value, 0)

        except Exception as e:
            if self._running:
                print(f"  ⚠️  Device error ({device.name}): {e}")

    def stop(self):
        self._running = False


# ============================================================
# Input Monitor - pynput (X11 / Windows / macOS)
# ============================================================

class PynputInputMonitor:
    """Monitor keyboard and mouse input via pynput."""

    def __init__(self, callbacks: Dict[str, Callable]):
        self.callbacks = callbacks
        self._ctrl_pressed = False
        self._keyboard_listener = None
        self._mouse_listener = None

    def start(self):
        from pynput import mouse, keyboard

        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll
        )
        self._keyboard_listener.start()
        self._mouse_listener.start()
        print("  📡 Monitoring via pynput (keyboard + mouse)")

    def _on_key_press(self, key):
        from pynput import keyboard
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self._ctrl_pressed = True
        if self._ctrl_pressed:
            if key == keyboard.Key.f8:
                threading.Thread(target=self.callbacks['on_hotkey_start_task'], daemon=True).start()
            elif key == keyboard.Key.f9:
                threading.Thread(target=self.callbacks['on_hotkey_screenshot'], daemon=True).start()
            elif key == keyboard.Key.f12:
                threading.Thread(target=self.callbacks['on_hotkey_end_task'], daemon=True).start()
        # ESC (no Ctrl needed) to drop current action
        if getattr(key, 'name', '') == 'esc':
            threading.Thread(target=self.callbacks['on_hotkey_drop_action'], daemon=True).start()

        key_name = self._map_pynput_key(key)
        if key_name and 'on_key_event' in self.callbacks:
            threading.Thread(target=self.callbacks['on_key_event'], args=(key_name, True), daemon=True).start()

    def _on_key_release(self, key):
        from pynput import keyboard
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self._ctrl_pressed = False
            
        key_name = self._map_pynput_key(key)
        if key_name and 'on_key_event' in self.callbacks:
            threading.Thread(target=self.callbacks['on_key_event'], args=(key_name, False), daemon=True).start()

    def _map_pynput_key(self, key):
        """Map a pynput key to a human-readable key name.
        Previously this only handled modifiers + a few special keys,
        silently dropping all letters/numbers/symbols — breaking combos."""
        from pynput import keyboard

        MODIFIER_KEYS = {
            keyboard.Key.ctrl_l:    'ctrl_l',
            keyboard.Key.ctrl_r:    'ctrl_r',
            keyboard.Key.shift_l:   'shift_l',
            keyboard.Key.shift_r:   'shift_r',
            keyboard.Key.alt_l:     'alt_l',
            keyboard.Key.alt_r:     'alt_r',
            keyboard.Key.cmd_l:     'super_l',
            keyboard.Key.cmd_r:     'super_r',
        }

        SPECIAL_KEYS = {
            keyboard.Key.esc:         'esc',
            keyboard.Key.backspace:   'backspace',
            keyboard.Key.enter:       'enter',
            keyboard.Key.tab:         'tab',
            keyboard.Key.space:       'space',
            keyboard.Key.caps_lock:   'capslock',
            keyboard.Key.delete:      'delete',
            keyboard.Key.insert:      'insert',
            keyboard.Key.home:        'home',
            keyboard.Key.end:         'end',
            keyboard.Key.page_up:     'pageup',
            keyboard.Key.page_down:   'pagedown',
            keyboard.Key.up:          'up',
            keyboard.Key.down:        'down',
            keyboard.Key.left:        'left',
            keyboard.Key.right:       'right',
            keyboard.Key.num_lock:    'numlock',
            keyboard.Key.print_screen: 'print',
            keyboard.Key.scroll_lock:  'scrolllock',
            keyboard.Key.pause:       'pause',
            keyboard.Key.menu:        'menu',
        }

        # Try modifier keys
        if key in MODIFIER_KEYS:
            return MODIFIER_KEYS[key]
        # Try special/function keys
        if key in SPECIAL_KEYS:
            return SPECIAL_KEYS[key]

        # Function keys f1–f24
        fn = getattr(keyboard.Key, 'f1', None)
        if fn is not None:
            for i in range(1, 25):
                fkey = getattr(keyboard.Key, f'f{i}', None)
                if fkey is not None and key == fkey:
                    return f'f{i}'

        # Alphanumeric character keys (e.g. 'a', '1', '`', '-', etc.)
        # pynput returns these as char strings for printable characters.
        if hasattr(key, 'char') and key.char is not None:
            return key.char

        # Named keys that pynput exposes as .name (e.g. 'ctrl', 'shift', etc.)
        if hasattr(key, 'name'):
            name = key.name
            # Handle platform-specific extra keys
            if name in ('ctrl', 'shift', 'alt', 'cmd', 'fn'):
                return name  # These are non-directional modifier names
            return name

        return None

    def _on_click(self, x, y, button, pressed):
        btn_name = button.name if hasattr(button, 'name') else str(button)
        if 'on_mouse_button' in self.callbacks:
            threading.Thread(target=self.callbacks['on_mouse_button'], args=(btn_name, pressed), daemon=True).start()

    def _on_scroll(self, x, y, dx, dy):
        self.callbacks['on_mouse_scroll'](dx, dy)

    def stop(self):
        if self._keyboard_listener:
            self._keyboard_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()
