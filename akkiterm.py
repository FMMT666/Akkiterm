#!/usr/bin/env python3
"""
akkiterm.py - Akki's serial terminal Dingens for MCUs et al.

Dependencies:
    pip install pyserial

Controls:
    - On start   : select available COM ports
    - ESC        : open menu
    - Menu → q   : quit program
    Everything else is sent directly to the serial port

    Use your eyes and common sense to figure out the rest.
    It's not rocket science. Or is it? Who knows.
    Maybe it's a secret terminal for communicating with aliens.
    Or maybe it's just a simple serial terminal. You decide.

    Copilot wrote this docstring. It always takes itself way too seriously.
    I just wanted a quick and dirty terminal, but it insisted on making it
    "documented and user-friendly". Well, here we are. Enjoy the overkill docstring!
"""


AKKITERM_VERSION = "0.30"



import sys
import os
import fnmatch
import threading
import time
from datetime import datetime
import serial
import serial.tools.list_ports

# ----------------------------------------------------------------------
# --- Platform-specific keyboard handling (Windows vs. Unix)

if sys.platform == "win32":
    import msvcrt

    def _kbhit() -> bool:
        return msvcrt.kbhit()

    def _getch() -> bytes:
        ch = msvcrt.getch()
        # Function keys return 2 bytes; discard the second byte.
        if ch in (b'\x00', b'\xe0'):
            msvcrt.getch()
            return b''
        return ch

    def _set_raw(_enable: bool):
        pass  # not needed on Windows; msvcrt.getch() already behaves like raw input

else:
    import tty
    import termios
    import select

    _old_settings = None

    def _set_raw(enable: bool):
        global _old_settings
        fd = sys.stdin.fileno()
        if enable:
            _old_settings = termios.tcgetattr(fd)
            tty.setraw(fd)
        else:
            if _old_settings:
                termios.tcsetattr(fd, termios.TCSADRAIN, _old_settings)

    def _kbhit() -> bool:
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        return bool(dr)

    def _getch() -> bytes:
        return sys.stdin.buffer.read(1)


# ----------------------------------------------------------------------
# --- Defaults and constants
DEFAULT_BAUDRATE   = 115200
DEFAULT_BYTESIZE   = serial.EIGHTBITS       # 8
DEFAULT_PARITY     = serial.PARITY_NONE     # N
DEFAULT_STOPBITS   = serial.STOPBITS_ONE    # 1
DEFAULT_TIMEOUT    = 0.1                    # Seconds (read timeout)

AVAILABLE_BAUDRATES = [
    300, 600, 1200, 2400, 4800, 9600, 19200,
    38400, 57600, 115200, 230400, 460800, 921600
]

ESC = b'\x1b'
CR  = b'\r'
LF  = b'\n'

CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'akkiterm.cfg')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_SELECT_KEYS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

# ----------------------------------------------------------------------
# --- Helper functions
def clear_screen():
    os.system('cls' if sys.platform == 'win32' else 'clear')


def banner():
    print("╔═════════════════════════════════╗")
    print("║         Akkiterm  v" + AKKITERM_VERSION + "         ║")
    print("║   ESC = menu  |  type to comm   ║")
    print("╚═════════════════════════════════╝")
    print()


def list_ports() -> list:
    """Return a sorted list of available serial ports."""
    ports = sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)
    return ports


def select_port() -> str | None:
    """Interactive port selection. Return the selected port name."""
    ports = list_ports()
    if not ports:
        print("⚠  No serial ports found.")
        print("   Please connect a device and restart the program.\n")
        return None

    print("Available serial ports:")
    print("─" * 40)
    for i, p in enumerate(ports, 1):
        desc = p.description if p.description != "n/a" else ""
        print(f"  [{i}]  {p.device:<12}  {desc}")
    print("─" * 40)

    while True:
        try:
            choice = input(f"Select port [1-{len(ports)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                return ports[idx].device
            print(f"  Please enter a number between 1 and {len(ports)}.")
        except (ValueError, KeyboardInterrupt):
            print("\nCanceled.")
            return None


def select_baudrate(current: int) -> int:
    """Interactive baud-rate selection. Return the chosen baud rate."""
    print("\nAvailable baud rates:")
    print("─" * 30)
    for i, b in enumerate(AVAILABLE_BAUDRATES, 1):
        marker = " ◄" if b == current else ""
        print(f"  [{i:2}]  {b}{marker}")
    print("  [ 0]  Manual entry")
    print("─" * 30)

    while True:
        try:
            choice = input(f"Baud rate [Enter = keep ({current})]: ").strip()
            if choice == "":
                return current
            idx = int(choice)
            if idx == 0:
                manual = input("Enter baud rate: ").strip()
                return int(manual)
            if 1 <= idx <= len(AVAILABLE_BAUDRATES):
                return AVAILABLE_BAUDRATES[idx - 1]
            print("  Invalid selection.")
        except (ValueError, KeyboardInterrupt):
            return current


# ----------------------------------------------------------------------
# --- Main terminal class
class SerialTerminal:
    def __init__(self):
        self.ser: serial.Serial | None = None
        self.port     = ""
        self.baudrate = DEFAULT_BAUDRATE
        self.bytesize = DEFAULT_BYTESIZE
        self.parity   = DEFAULT_PARITY
        self.stopbits = DEFAULT_STOPBITS

        self._running        = False
        self._in_menu        = False
        self._hex_mode       = False
        self._dec_mode       = False
        self._hex_cols       = 16   # bytes per line in hex mode (0 = no wrap)
        self._hex_col_count  = 0    # running byte counter for current line
        self._line_send_mode = False
        self._line_send_format  = 'dec'
        self._line_input_buf = bytearray()
        self._echo_enabled   = False
        self._log_to_file    = False
        self._log_file       = None
        self._log_file_path  = ''
        self._log_lock       = threading.Lock()
        self._macros         = {}  # dict: char → (format_str, value_str), e.g. ('ASC', 'Hello')
        self._macros_enabled = False
        self._file_send_filter = '*.*'
        self._file_send_format = 'asc'
        self._file_send_asc_cr = False
        self._reader_thread: threading.Thread | None = None

    def _make_log_file_path(self) -> str:
        timestamp = datetime.now().strftime('%y%m%d%H%M%S')
        return os.path.join(BASE_DIR, f'akkiterm_{timestamp}.log')

    def _start_logging(self) -> bool:
        if self._log_file:
            return True
        path = self._make_log_file_path()
        try:
            self._log_file = open(path, 'w', encoding='utf-8', newline='')
            self._log_file_path = path
            return True
        except OSError as e:
            self._log_file = None
            self._log_file_path = ''
            print(f'  ✖  Could not open log file: {e}')
            return False

    def _stop_logging(self):
        with self._log_lock:
            if self._log_file:
                self._log_file.close()
            self._log_file = None
            self._log_file_path = ''

    def _set_logging(self, enabled: bool) -> bool:
        if enabled:
            if not self._start_logging():
                self._log_to_file = False
                return False
            self._log_to_file = True
            return True

        self._log_to_file = False
        self._stop_logging()
        return True

    def _write_log(self, text: str):
        if not self._log_to_file or not text:
            return
        with self._log_lock:
            if not self._log_file:
                return
            try:
                self._log_file.write(text)
                self._log_file.flush()
            except OSError as e:
                self._log_to_file = False
                print(f"\n✖  Log write error: {e}")
                self._stop_logging()

    # --- Config save / load
    def save_config(self):
        """Save current settings to akkiterm.cfg."""
        try:
            with open(CFG_FILE, 'w') as f:
                f.write('# akkiterm configuration\n')
                f.write(f'PORT={self.port}\n')
                f.write(f'BAUDRATE={self.baudrate}\n')
                f.write(f'BYTESIZE={self.bytesize}\n')
                f.write(f'PARITY={self.parity}\n')
                f.write(f'STOPBITS={self.stopbits}\n')
                f.write(f'HEX_MODE={str(self._hex_mode).lower()}\n')
                f.write(f'DEC_MODE={str(self._dec_mode).lower()}\n')
                f.write(f'HEX_COLS={self._hex_cols}\n')
                f.write(f'ECHO_ENABLED={str(self._echo_enabled).lower()}\n')
                f.write(f'LOG_TO_FILE={str(self._log_to_file).lower()}\n')
                f.write(f'MACROS_ENABLED={str(self._macros_enabled).lower()}\n')
                f.write(f'FILE_SEND_FILTER={self._file_send_filter}\n')
                f.write(f'FILE_SEND_FORMAT={self._file_send_format}\n')
                f.write(f'FILE_SEND_ASC_CR={str(self._file_send_asc_cr).lower()}\n')
                f.write(f'LINE_SEND_MODE={str(self._line_send_mode).lower()}\n')
                f.write(f'LINE_SEND_FORMAT={self._line_send_format}\n')
                # Macros always last, sorted alphabetically by key for readability and maintainability
                for key, (fmt, value) in sorted(self._macros.items()):
                    f.write(f'MACRO_{key}_{fmt}={value}\n')
            print(f'  Settings saved to {CFG_FILE}')
        except OSError as e:
            print(f'  \u2716  Could not save settings: {e}')

    def load_config(self) -> str | None:
        """Load settings from akkiterm.cfg. Return saved port name or None."""
        if not os.path.exists(CFG_FILE):
            return None
        cfg = {}
        try:
            with open(CFG_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    key, _, val = line.partition('=')
                    cfg[key.strip()] = val.strip()
        except OSError:
            return None
        try:
            if 'BAUDRATE' in cfg: self.baudrate  = int(cfg['BAUDRATE'])
            if 'BYTESIZE' in cfg: self.bytesize  = int(cfg['BYTESIZE'])
            if 'PARITY'   in cfg: self.parity    = cfg['PARITY']
            if 'STOPBITS' in cfg: self.stopbits  = float(cfg['STOPBITS'])
            if 'HEX_MODE' in cfg: self._hex_mode = cfg['HEX_MODE'].lower() == 'true'
            if 'DEC_MODE' in cfg: self._dec_mode = cfg['DEC_MODE'].lower() == 'true'
            if 'HEX_COLS' in cfg: self._hex_cols = int(cfg['HEX_COLS'])
            if 'ECHO_ENABLED' in cfg: self._echo_enabled = cfg['ECHO_ENABLED'].lower() == 'true'
            if 'LOG_TO_FILE' in cfg: self._log_to_file = cfg['LOG_TO_FILE'].lower() == 'true'
            if 'LINE_SEND_MODE' in cfg:
                self._line_send_mode = cfg['LINE_SEND_MODE'].lower() == 'true'
            if 'LINE_SEND_FORMAT' in cfg and cfg['LINE_SEND_FORMAT'].lower() in ('dec', 'hex'):
                self._line_send_format = cfg['LINE_SEND_FORMAT'].lower()
            if 'MACROS_ENABLED' in cfg: self._macros_enabled = cfg['MACROS_ENABLED'].lower() == 'true'
            if 'FILE_SEND_FILTER' in cfg and cfg['FILE_SEND_FILTER']:
                self._file_send_filter = cfg['FILE_SEND_FILTER']
            if 'FILE_SEND_FORMAT' in cfg and cfg['FILE_SEND_FORMAT'].lower() in ('asc', 'dec', 'hex'):
                self._file_send_format = cfg['FILE_SEND_FORMAT'].lower()
            if 'FILE_SEND_ASC_CR' in cfg:
                self._file_send_asc_cr = cfg['FILE_SEND_ASC_CR'].lower() == 'true'
            # Parse macros: MACRO_<KEY>_<FORMAT>=<VALUE>
            for key, val in cfg.items():
                if key.startswith('MACRO_'):
                    parts = key.split('_')
                    if len(parts) >= 3:
                        macro_key = parts[1]
                        macro_fmt = '_'.join(parts[2:]).upper()
                        if macro_fmt in ('ASC', 'DEC', 'HEX') and len(macro_key) == 1 and 32 <= ord(macro_key) <= 126:
                            self._macros[macro_key] = (macro_fmt, val)
            # If both are enabled by malformed/legacy config, prefer HEX.
            if self._hex_mode and self._dec_mode:
                self._dec_mode = False
        except (ValueError, KeyError):
            pass
        return cfg.get('PORT')

    def _parse_byte_token(self, token: str) -> int | None:
        """Parse a single token in current line-send format and return 0..255."""
        if not token:
            return None
        token_l = token.lower().strip()

        if self._line_send_format == 'hex':
            if not all(c in '0123456789abcdef' for c in token_l):
                return None
            base = 16
        else:
            if not token_l.isdigit():
                return None
            base = 10

        try:
            value = int(token_l, base)
        except ValueError:
            return None
        if not (0 <= value <= 255):
            return None
        return value

    def _parse_byte_token_explicit(self, token: str, base: int) -> int | None:
        """Parse a byte token in given base (10 or 16). Return 0..255 or None."""
        if not token:
            return None
        token_l = token.lower().strip()

        if base == 16:
            if not all(c in '0123456789abcdef' for c in token_l):
                return None
        else:
            if not token_l.isdigit():
                return None

        try:
            value = int(token_l, base)
        except ValueError:
            return None
        if not (0 <= value <= 255):
            return None
        return value

    def _format_macros_list(self) -> str:
        """Return a formatted string of all defined macros (e.g., '2→ASC, L→HEX, w→DEC')."""
        if not self._macros:
            return "(none)"
        items = [f"{key}→{fmt}" for key, (fmt, _) in sorted(self._macros.items())]
        return ", ".join(items)

    def _print_macros_lines(self):
        """Print each defined macro on its own line with indentation."""
        for key, (fmt, value) in sorted(self._macros.items()):
            print(f"         {key}→{fmt}: {value}")

    def _print_config_info(self, header: str = "Config loaded:"):
        """Print all loaded config settings (output mode, logging, macros, etc.)."""
        if header:
            print(f"  {header}")
        print(f"  Baud rate : {self.baudrate}")
        print(f"  Format    : {self.bytesize}{self.parity}{int(self.stopbits)}")
        cols_label = "no wrap" if self._hex_cols == 0 else str(self._hex_cols)
        if self._hex_mode:
            out_mode = 'HEX'
        elif self._dec_mode:
            out_mode = 'DEC'
        else:
            out_mode = 'ASCII'
        print(f"  Output    : {out_mode}  ({cols_label} bytes/line)")
        print(f"  Echo TX   : {'ON' if self._echo_enabled else 'OFF'}")
        print(f"  Logging   : {'ON' if self._log_to_file else 'OFF'}")
        print(f"  Macros    : {'ON (' + str(len(self._macros)) + ' defined)' if self._macros_enabled else 'OFF'}")
        if self._macros_enabled and self._macros:
            self._print_macros_lines()
        cr_label = " +CR" if self._file_send_format == 'asc' and self._file_send_asc_cr else ""
        print(f"  Send file : {self._file_send_format.upper()}{cr_label}  (filter: {self._file_send_filter})")
        print(f"  Line send : {'ON' if self._line_send_mode else 'OFF'}  ({self._line_send_format.upper()})")

    def _echo_tx(self, data: bytes):
        """Echo sent bytes to terminal when TX echo is enabled."""
        if not self._echo_enabled or not data:
            return

        if self._hex_mode:
            for b in data:
                sys.stdout.write(f'{b:02X} ')
        elif self._dec_mode:
            for b in data:
                sys.stdout.write(f'{b:03d} ')
        else:
            sys.stdout.write(data.decode('utf-8', errors='replace'))
        sys.stdout.flush()

    def _send_bytes(self, data: bytes, allow_in_menu: bool = False):
        """Send raw bytes and optionally echo exactly what was sent."""
        if not (self.ser and self.ser.is_open):
            return
        if self._in_menu and not allow_in_menu:
            return
        # Echo immediately before sending so full TX payload is visible first.
        self._echo_tx(data)
        self.ser.write(data)

    def _resolve_file_patterns(self, pattern_input: str) -> list[str]:
        """Split semicolon-separated wildcard filters and normalize defaults."""
        raw = (pattern_input or '').strip()
        if not raw:
            raw = '*.*'

        patterns = [p.strip() for p in raw.split(';') if p.strip()]
        if not patterns:
            patterns = ['*.*']

        # In shell-style matching, '*' behaves like "everything" and is often what users
        # expect from '*.*' in this small dialog.
        return ['*' if p == '*.*' else p for p in patterns]

    def _find_matching_files(self, pattern_input: str) -> list[str]:
        """Return matching files from BASE_DIR for semicolon-separated wildcard patterns."""
        patterns = self._resolve_file_patterns(pattern_input)
        matches = []
        for name in sorted(os.listdir(BASE_DIR)):
            full_path = os.path.join(BASE_DIR, name)
            if not os.path.isfile(full_path):
                continue
            if any(fnmatch.fnmatch(name, pat) for pat in patterns):
                matches.append(name)
        return matches

    def _bytes_from_file_content(self, file_path: str, send_format: str) -> bytes | None:
        """Load and parse file content according to ASC/DEC/HEX mode."""
        fmt = send_format.lower()

        if fmt == 'asc':
            try:
                with open(file_path, 'rb') as f:
                    return f.read()
            except OSError as e:
                print(f"  ✖  Could not read file: {e}")
                return None

        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError as e:
            print(f"  ✖  Could not read file: {e}")
            return None

        base = 16 if fmt == 'hex' else 10
        out = bytearray()
        for token in text.split():
            value = self._parse_byte_token_explicit(token, base)
            if value is None:
                hint = '00..FF' if fmt == 'hex' else '0..255'
                print(f"  ✖  Invalid token in file: {token!r} (expected {fmt.upper()} {hint})")
                return None
            out.append(value)
        return bytes(out)

    def _send_file_dialog(self):
        """Interactive file-send dialog with wildcard filter and one-key selection."""
        if not (self.ser and self.ser.is_open):
            print("  ✖  Not connected.")
            return

        pattern = input(f"  File filter [default: {self._file_send_filter}]: ").strip()
        if pattern:
            self._file_send_filter = pattern
        files = self._find_matching_files(self._file_send_filter)
        if not files:
            print(f"  No matching files for filter: {self._file_send_filter}")
            return

        send_fmt = input(f"  Send format [asc/dec/hex, default: {self._file_send_format}]: ").strip().lower()
        if send_fmt:
            if send_fmt not in ('asc', 'dec', 'hex'):
                print("  Invalid format.")
                return
            self._file_send_format = send_fmt

        if self._file_send_format == 'asc':
            default_cr = 'y' if self._file_send_asc_cr else 'n'
            cr_choice = input(f"  Normalize LF→CRLF in ASC file [y/n, default: {default_cr}]: ").strip().lower()
            if cr_choice:
                if cr_choice in ('y', 'yes', '1', 'true', 'on'):
                    self._file_send_asc_cr = True
                elif cr_choice in ('n', 'no', '0', 'false', 'off'):
                    self._file_send_asc_cr = False
                else:
                    print("  Invalid option.")
                    return

        max_items = min(len(files), len(FILE_SELECT_KEYS))
        if len(files) > len(FILE_SELECT_KEYS):
            print(f"  Showing first {len(FILE_SELECT_KEYS)} files (filter matched {len(files)}).")

        print("\n  Select file to send:")
        key_to_file = {}
        for idx in range(max_items):
            key = FILE_SELECT_KEYS[idx]
            name = files[idx]
            full = os.path.join(BASE_DIR, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            size_label = f"{size} B" if size >= 0 else "size ?"
            print(f"    [{key}]  {name:<30} {size_label}")
            key_to_file[key] = full

        selected = input("  Key [0-9,a-z,A-Z] (Enter=cancel): ").strip()
        if not selected:
            print("  Canceled.")
            return
        if len(selected) != 1 or selected not in key_to_file:
            print("  Invalid selection key.")
            return

        file_path = key_to_file[selected]
        payload = self._bytes_from_file_content(file_path, self._file_send_format)
        if payload is None:
            return

        send_payload = payload
        if self._file_send_format == 'asc' and self._file_send_asc_cr:
            # Normalize line endings: replace bare \n with \r\n (avoid double \r\r\n)
            send_payload = send_payload.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')

        if not send_payload:
            print("  Selected file is empty. Nothing sent.")
            return

        try:
            self._send_bytes(send_payload, allow_in_menu=True)
            cr_info = " +CR" if self._file_send_format == 'asc' and self._file_send_asc_cr else ""
            print(f"  Sent {len(send_payload)} byte(s) from: {os.path.basename(file_path)} ({self._file_send_format.upper()}{cr_info})")
        except serial.SerialException as e:
            print(f"  ✖  File send error: {e}")

    def _send_macro_data(self, fmt: str, value: str):
        """Parse and send macro data based on format (ASC/DEC/HEX)."""
        if not (self.ser and self.ser.is_open and not self._in_menu):
            return

        out = bytearray()

        if fmt == 'ASC':
            # Treat as raw ASCII string
            try:
                out = bytearray(value.encode('utf-8'))
            except Exception:
                sys.stdout.write(f"\r\n  Macro ASC error: invalid encoding\r\n")
                sys.stdout.flush()
                return

        elif fmt in ('DEC', 'HEX'):
            # Parse tokens separated by spaces
            tokens = value.split()
            base = 16 if fmt == 'HEX' else 10
            for token in tokens:
                parsed = self._parse_byte_token_explicit(token, base)
                if parsed is None:
                    fmt_hint = "0..255" if fmt == 'DEC' else "00..FF"
                    sys.stdout.write(f"\r\n  Macro {fmt} error: invalid token '{token}' (expected {fmt_hint})\r\n")
                    sys.stdout.flush()
                    return
                out.append(parsed)
        else:
            return

        if out:
            try:
                self._send_bytes(bytes(out))
                # sys.stdout.write(f"\r\n  Macro sent ({len(out)} byte(s))\r\n")
                sys.stdout.flush()
            except serial.SerialException as e:
                sys.stdout.write(f"\r\n✖  Macro send error: {e}\r\n")
                sys.stdout.flush()

    def _send_collected_line(self):
        """Parse and send buffered line as raw bytes."""
        line = self._line_input_buf.decode('ascii', errors='ignore').strip()
        self._line_input_buf.clear()

        if not line:
            return

        out = bytearray()
        for token in line.split():
            value = self._parse_byte_token(token)
            if value is None:
                fmt_hint = "0..255" if self._line_send_format == 'dec' else "00..FF"
                sys.stdout.write(f"\r\n  Invalid token: {token!r} (expected {self._line_send_format.upper()} {fmt_hint})\r\n")
                sys.stdout.flush()
                return
            out.append(value)

        if self.ser and self.ser.is_open and not self._in_menu:
            try:
                self._send_bytes(bytes(out))
                # sys.stdout.write(f"\r\n  Sent {len(out)} byte(s).\r\n")
                sys.stdout.flush()
            except serial.SerialException as e:
                sys.stdout.write(f"\r\n✖  Send error: {e}\r\n")
                sys.stdout.flush()

    # --- Connection
    def connect(self, port: str) -> bool:
        try:
            self.ser = serial.Serial(
                port     = port,
                baudrate = self.baudrate,
                bytesize = self.bytesize,
                parity   = self.parity,
                stopbits = self.stopbits,
                timeout  = DEFAULT_TIMEOUT,
            )
            self.port = port
            print(f"\n✔  Connected: {port}  |  "
                  f"{self.baudrate} Baud  |  "
                  f"{self.bytesize}"
                  f"{self.parity}"
                  f"{int(self.stopbits)}\n")
            return True
        except serial.SerialException as e:
            print(f"\n✖  Error opening {port}: {e}\n")
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None

    def reconnect(self):
        """Disconnect and reconnect (e.g., after a baud-rate change)."""
        self.disconnect()
        if self.port:
            self.connect(self.port)

    # --- Serial reader thread
    def _reader(self):
        """Continuously read from the serial port and print incoming data."""
        while self._running:
            if self._in_menu or not self.ser or not self.ser.is_open:
                time.sleep(0.05)
                continue
            try:
                data = self.ser.read(256)
                if data:
                    log_text = ''
                    if self._hex_mode:
                        parts = []
                        for b in data:
                            part = f'{b:02X} '
                            parts.append(part)
                            sys.stdout.write(part)
                            if self._hex_cols > 0:
                                self._hex_col_count += 1
                                if self._hex_col_count >= self._hex_cols:
                                    sys.stdout.write('\r\n')
                                    parts.append('\r\n')
                                    self._hex_col_count = 0
                        log_text = ''.join(parts)
                    elif self._dec_mode:
                        parts = []
                        for b in data:
                            part = f'{b:03d} '
                            parts.append(part)
                            sys.stdout.write(part)
                            if self._hex_cols > 0:
                                self._hex_col_count += 1
                                if self._hex_col_count >= self._hex_cols:
                                    sys.stdout.write('\r\n')
                                    parts.append('\r\n')
                                    self._hex_col_count = 0
                        log_text = ''.join(parts)
                    else:
                        # Print raw bytes as text (UTF-8; replace unknown bytes).
                        log_text = data.decode('utf-8', errors='replace')
                        sys.stdout.write(log_text)
                    self._write_log(log_text)
                    sys.stdout.flush()
            except serial.SerialException:
                if self._running:
                    print("\n⚠  Connection interrupted!")
                break

    # --- Menu
    def show_menu(self):
        self._in_menu = True
        _set_raw(False)  # Switch to normal mode for menu input.

        print("\n")
        print("┌─────────────────────────────────┐")
        print("│              MENU               │")
        print("├─────────────────────────────────┤")
        hex_state = "on " if self._hex_mode else "off"
        dec_state = "on " if self._dec_mode else "off"
        print("│  [b]  change baud rate          │")
        print("│  [p]  change port               │")
        print("│  [i]  info / status             │")
        print("│  [c]  clear screen              │")
        print("│  [r]  reconnect                 │")
        print(f"│  [x]  hex output  [{hex_state:<3}]         │")
        print(f"│  [d]  dec output  [{dec_state:<3}]         │")
        print(f"│  [w]  out cols    [{self._hex_cols:>3}]         │")
        print(f"│  [e]  echo tx     [{'on ' if self._echo_enabled else 'off'}]         │")
        print(f"│  [l]  log to file [{'on ' if self._log_to_file else 'off'}]         │")
        print(f"│  [g]  macros      [{'on ' if self._macros_enabled else 'off'}]  ({len(self._macros):>2})   │")
        print(f"│  [u]  send file   [{self._file_send_format:<3}]         │")
        print(f"│  [m]  line send   [{'on ' if self._line_send_mode else 'off'}]         │")
        print(f"│  [f]  line format [{self._line_send_format:<3}]         │")
        print("│  [s]  save settings             │")
        print("│  [q]  quit                      │")
        print("│  [Enter/Esc]  back              │")
        print("└─────────────────────────────────┘")
        choice = input("Select option: ").strip().lower()

        if choice == 'q':
#            self.stop()
            self._running = False

        elif choice == 'b':
            new_baud = select_baudrate(self.baudrate)
            if new_baud != self.baudrate:
                self.baudrate = new_baud
                self.reconnect()

        elif choice == 'p':
            new_port = select_port()
            if new_port and new_port != self.port:
                self.disconnect()
                self.connect(new_port)
            elif new_port == self.port:
                print("  Port unchanged.")

        elif choice == 'x':
            self._hex_mode = not self._hex_mode
            if self._hex_mode:
                self._dec_mode = False
            self._hex_col_count = 0
            state = "ON" if self._hex_mode else "OFF"
            print(f"  Hex output: {state}")

        elif choice == 'd':
            self._dec_mode = not self._dec_mode
            if self._dec_mode:
                self._hex_mode = False
            self._hex_col_count = 0
            state = "ON" if self._dec_mode else "OFF"
            print(f"  Dec output: {state}")

        elif choice == 'w':
            try:
                cols = int(input("  Bytes per line (0 = no wrap): ").strip())
                if cols >= 0:
                    self._hex_cols      = cols
                    self._hex_col_count = 0
                    label = "no wrap" if cols == 0 else str(cols)
                    print(f"  Output cols: {label}")
                else:
                    print("  Invalid value.")
            except (ValueError, KeyboardInterrupt):
                print("  Unchanged.")

        elif choice == 'e':
            self._echo_enabled = not self._echo_enabled
            state = "ON" if self._echo_enabled else "OFF"
            print(f"  Echo TX: {state}")

        elif choice == 'l':
            new_state = not self._log_to_file
            if self._set_logging(new_state):
                state = "ON" if self._log_to_file else "OFF"
                print(f"  Log to file: {state}")
                if self._log_to_file:
                    print(f"  File: {self._log_file_path}")

        elif choice == 'g':
            self._macros_enabled = not self._macros_enabled
            state = "ON" if self._macros_enabled else "OFF"
            print(f"  Macros: {state}  ({len(self._macros)} defined)")
            if self._macros_enabled and self._macros:
                self._print_macros_lines()

        elif choice == 'm':
            self._line_send_mode = not self._line_send_mode
            self._line_input_buf.clear()
            state = "ON" if self._line_send_mode else "OFF"
            print(f"  Line send mode: {state}")
            if self._line_send_mode:
                if self._line_send_format == 'hex':
                    print("  Enter HEX bytes separated by spaces, then press Enter (e.g. 0A 10 7F ff).")
                else:
                    print("  Enter DEC bytes separated by spaces, then press Enter (e.g. 10 20 127 255).")

        elif choice == 'f':
            line_format = input("  Line send format [dec/hex]: ").strip().lower()
            if line_format in ('dec', 'hex'):
                self._line_send_format = line_format
                self._line_input_buf.clear()
                print(f"  Line send format: {self._line_send_format.upper()}")
            elif line_format:
                print("  Invalid format.")

        elif choice == 'u':
            self._send_file_dialog()

        elif choice == 'i':
            connected = self.ser and self.ser.is_open
            status = "Connected ✔" if connected else "Disconnected ✖"
            if self._hex_mode:
                out_mode = "HEX"
            elif self._dec_mode:
                out_mode = "DEC"
            else:
                out_mode = "ASCII"
            hex_cols_label = "no wrap" if self._hex_cols == 0 else str(self._hex_cols)
            line_mode = "ON" if self._line_send_mode else "OFF"
            log_state = "ON" if self._log_to_file else "OFF"
            echo_state = "ON" if self._echo_enabled else "OFF"
            print(f"\n  Port      : {self.port or '—'}")
            print(f"  Baud rate : {self.baudrate}")
            print(f"  Format    : {self.bytesize}{self.parity}{int(self.stopbits)}")
            print(f"  Output    : {out_mode}  ({hex_cols_label} bytes/line)")
            print(f"  Echo TX   : {echo_state}")
            print(f"  Logging   : {log_state}{f'  ({self._log_file_path})' if self._log_file_path else ''}")
            macros_status = f"ON ({len(self._macros)} defined)" if self._macros_enabled else "OFF"
            print(f"  Macros    : {macros_status}")
            cr_label = " +CR" if self._file_send_format == 'asc' and self._file_send_asc_cr else ""
            print(f"  Send file : {self._file_send_format.upper()}{cr_label}  (filter: {self._file_send_filter})")
            print(f"  Line send : {line_mode}  ({self._line_send_format.upper()})")
            print(f"  Status    : {status}\n")
            input("  [Enter] to continue...")

        elif choice == 'c':
            clear_screen()
            banner()

        elif choice == 'r':
            print("  Reconnecting...")
            self.reconnect()

        elif choice == 's':
            self.save_config()

        # ESC / Enter / anything else -> back to terminal mode.
        _set_raw(True)
        self._in_menu = False

    # --- Main loop
    def run(self):
        clear_screen()
        banner()

        # Load saved config; use saved port if still available.
        saved_port = self.load_config()
        available  = [p.device for p in list_ports()]

        if saved_port and saved_port in available:
            print(f"  Config loaded:")
            print(f"  Port      : {saved_port}")
            self._print_config_info("")
            print()
            port = saved_port
        else:
            if saved_port:
                print(f"  \u26a0  Saved port {saved_port!r} not available, please select manually.\n")
                self._print_config_info("Config loaded (port unavailable):")
                print()
            port = select_port()
            if not port:
                sys.exit(0)

        if not self.connect(port):
            sys.exit(1)

        if self._log_to_file and not self._start_logging():
            print("  Logging disabled due to file error.")
            self._log_to_file = False
        elif self._log_to_file:
            print(f"  Logging to: {self._log_file_path}")

        self._running = True

        # Start reader thread.
        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()

        print("  (Type = Send  |  ESC = Menu)\n")

        _set_raw(True)  # Raw mode: each key is processed immediately.
        try:
            while self._running:
                if not _kbhit():
                    time.sleep(0.01)
                    continue

                ch = _getch()
                if not ch:
                    continue

                if ch == ESC:
                    if self._line_send_mode and self._line_input_buf:
                        self._line_input_buf.clear()
                        sys.stdout.write("\r\n")
                        sys.stdout.flush()
                    self.show_menu()
                    continue

                # Send input to serial port.
                if self.ser and self.ser.is_open and not self._in_menu:
                    try:
                        # Check for macro first (only in normal mode, not in line_send_mode)
                        if not self._line_send_mode and self._macros_enabled and len(ch) == 1:
                            ch_char = chr(ch[0])
                            if ch_char in self._macros:
                                fmt, value = self._macros[ch_char]
                                self._send_macro_data(fmt, value)
                                continue

                        if self._line_send_mode:
                            # Collect bytes as text tokens and send parsed bytes on Enter.
                            if ch in (CR, LF):
                                sys.stdout.write("\r\n")
                                sys.stdout.flush()
                                self._send_collected_line()
                                continue
                            if ch in (b'\x08', b'\x7f'):
                                if self._line_input_buf:
                                    self._line_input_buf.pop()
                                    sys.stdout.write("\b \b")
                                    sys.stdout.flush()
                                continue
                            if 32 <= ch[0] <= 126:
                                if not self._line_input_buf:
                                    # Start collected input on a fresh line for readability.
                                    sys.stdout.write("\r\n")
                                self._line_input_buf.append(ch[0])
                                sys.stdout.write(chr(ch[0]))
                                sys.stdout.flush()
                                continue
                            continue

                        # Send CR as CR+LF (adjust if needed).
                        if ch == CR:
                            self._send_bytes(CR + LF)
                        else:
                            self._send_bytes(ch)
                    except serial.SerialException as e:
                        print(f"\n✖  Send error: {e}")

        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self._running = False
        _set_raw(False)
        self._stop_logging()
        self.disconnect()
        print("\n\nBis bald, aber es eilt nicht.\n")

        # Calling sys.exit() here would skip run()'s finally block;
        # instead, let run() exit cleanly.


# ----------------------------------------------------------------------
# --- Entry point
if __name__ == "__main__":
    terminal = SerialTerminal()
    terminal.run()
