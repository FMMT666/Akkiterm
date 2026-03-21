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

import sys
import os
import threading
import time
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

# ----------------------------------------------------------------------
# --- Helper functions
def clear_screen():
    os.system('cls' if sys.platform == 'win32' else 'clear')


def banner():
    print("╔═════════════════════════════════╗")
    print("║         Akkiterm  v0.11         ║")
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
        self._hex_cols       = 16   # bytes per line in hex mode (0 = no wrap)
        self._hex_col_count  = 0    # running byte counter for current line
        self._reader_thread: threading.Thread | None = None

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
                f.write(f'HEX_COLS={self._hex_cols}\n')
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
            if 'HEX_COLS' in cfg: self._hex_cols = int(cfg['HEX_COLS'])
        except (ValueError, KeyError):
            pass
        return cfg.get('PORT')

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
                    if self._hex_mode:
                        for b in data:
                            sys.stdout.write(f'{b:02X} ')
                            if self._hex_cols > 0:
                                self._hex_col_count += 1
                                if self._hex_col_count >= self._hex_cols:
                                    sys.stdout.write('\r\n')
                                    self._hex_col_count = 0
                    else:
                        # Print raw bytes as text (UTF-8; replace unknown bytes).
                        sys.stdout.write(data.decode('utf-8', errors='replace'))
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
        print("│  [b]  change baud rate          │")
        print("│  [p]  change port               │")
        print("│  [i]  info / status             │")
        print("│  [c]  clear screen              │")
        print("│  [r]  reconnect                 │")
        print(f"│  [x]  hex output  [{hex_state:<3}]         │")
        print(f"│  [w]  hex cols    [{self._hex_cols:>3}]         │")
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
            self._hex_col_count = 0
            state = "ON" if self._hex_mode else "OFF"
            print(f"  Hex output: {state}")

        elif choice == 'w':
            try:
                cols = int(input("  Bytes per line (0 = no wrap): ").strip())
                if cols >= 0:
                    self._hex_cols      = cols
                    self._hex_col_count = 0
                    label = "no wrap" if cols == 0 else str(cols)
                    print(f"  Hex cols: {label}")
                else:
                    print("  Invalid value.")
            except (ValueError, KeyboardInterrupt):
                print("  Unchanged.")

        elif choice == 'i':
            connected = self.ser and self.ser.is_open
            status = "Connected ✔" if connected else "Disconnected ✖"
            hex_status = "ON" if self._hex_mode else "OFF"
            hex_cols_label = "no wrap" if self._hex_cols == 0 else str(self._hex_cols)
            print(f"\n  Port      : {self.port or '—'}")
            print(f"  Baud rate : {self.baudrate}")
            print(f"  Format    : {self.bytesize}{self.parity}{int(self.stopbits)}")
            print(f"  Hex output: {hex_status}  ({hex_cols_label} bytes/line)")
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
            print(f"  Baud rate : {self.baudrate}")
            print(f"  Format    : {self.bytesize}{self.parity}{int(self.stopbits)}")
            cols_label = "no wrap" if self._hex_cols == 0 else str(self._hex_cols)
            print(f"  Hex output: {'ON' if self._hex_mode else 'OFF'}  ({cols_label} bytes/line)")
            print()
            port = saved_port
        else:
            if saved_port:
                print(f"  \u26a0  Saved port {saved_port!r} not available, please select manually.\n")
            port = select_port()
            if not port:
                sys.exit(0)

        if not self.connect(port):
            sys.exit(1)

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
                    self.show_menu()
                    continue

                # Send input to serial port.
                if self.ser and self.ser.is_open and not self._in_menu:
                    try:
                        # Send CR as CR+LF (adjust if needed).
                        if ch == CR:
                            self.ser.write(CR + LF)
                        else:
                            self.ser.write(ch)
                    except serial.SerialException as e:
                        print(f"\n✖  Send error: {e}")

        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self._running = False
        _set_raw(False)
        self.disconnect()
        print("\n\nBis bald, aber es eilt nicht.\n")

        # Calling sys.exit() here would skip run()'s finally block;
        # instead, let run() exit cleanly.


# ----------------------------------------------------------------------
# --- Entry point
if __name__ == "__main__":
    terminal = SerialTerminal()
    terminal.run()
