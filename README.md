Akkiterm
========

A quick and dirty serial terminal application for the console, for now.  
Useful for coomunication with MCUs, debugging, etc.  

Works on all platforms which support Python and PySerial. 

---------------------------------------------------------------------------------------------

---
## FEATURES (yet)

  - ASCII
  - HEX
  - HEX formatted
  - DEC
  - local folder config save & autoload
  - console (yeah \o/)
  - many more to come
  - ...


### SOME SCREENSHOTS

Startup with ```akkiterm.cfg``` in local path:  

![startup with config](images/start.png)  

The menu:  

![menu](images/menu.png)  

[...]


---
## INSTALLATION

Requirements:

 - Python 3
 - PySerial

In case you don't have PySerial installed or are not sure, get it with:

    pip install pyserial

or

    pip3 install pyserial

depending on your Python installation.


### Linux, macOS

Just copy ```akkiterm.py``` to a directory in your path and make it executable:

    chmod +x ./akkiterm.py

If ```python3``` does not invoke your Python interpreter, you need to change
the first line in ```akkiterm.py``` to

    #!/usr/bin/env python

although I would not recommend this. Go fix your installation and symlinks instead.


### Windows

I recommend [RealTerm][2]. Yo, rly :)

Otherwise, in case you dislike typing

    python3 d:\pathtowherever\longwindozepath\akkiterm.py

consider creating a batch file

    @echo off
    where py >nul 2>nul && py "%~dp0akkiterm.py" %* && goto :eof
    python "%~dp0akkiterm.py" %*

and store it, together with akkiterm.py, in a directory within your path variable.


---
## USAGE

This should be self-explanatory (for now).  
Press ESC for the menu.

In case a file ```akkiterm.cfg``` exists in the local directory, the configuration is loaded
automatically.


---
## TODO
    - decimal output (like formatted hex)
    - send macros
    - optional delimiter for formatted output (e.g. CSV)
    - logging to file
    - send files
    - new line on/off
    - much more


---
## NEWS

### CHANGES 2026/03/24:
    - added HEX and DEC input (linewise)

### CHANGES 2026/03/22:
    - added config file with automatic loading function on startup

### CHANGES 2026/03/21:
    - added HEX output
    - added HEX output formatting; new line after n bytes

### CHANGES 2026/03/18:
    - initial version


---
Have fun  
FMMT666(ASkr)  


[1]: https://pyserial.readthedocs.io
[2]: https://sourceforge.net/projects/realterm/
