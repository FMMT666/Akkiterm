Akkiterm
========

A quick and dirty serial terminal application for the console, for now.  
Useful for communication with MCUs, debugging, etc.  

Works on all platforms which support Python and PySerial. 

---------------------------------------------------------------------------------------------

---
## FEATURES (yet)

  - ASCII
  - HEX/DEC with optional formatting
  - log received output to local file
  - macros: configurable key bindings (ASCII/DEC/HEX)
  - local folder config save & autoload
  - local TX echo
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

Most should be self-explanatory (for now). Press ESC for the menu.  

In case a file ```akkiterm.cfg``` exists in the local directory, the configuration is loaded automatically.


### MACROS

Akkiterm supports sending messages/data with hotkeys if defined.  
So far, macros can be defined in the config file:

    MACRO_<key>_<TYPE>=<macro/data to be sent>

Type can be one of:

    ASC -> ASCII text
    DEC -> decimal numbers, to be sent as (character) codes
    HEX -> hexadecimal numbers, to be sent as (character) codes

Example:

    MACRO_1_ASC=Henlo, i bims die 1
    MACRO_2_ASC=Und i di 2
    MACRO_3_ASC=Drei, angenehm.
    MACRO_d_DEC=97 98 99 100 101
    MACRO_h_HEX=33 34 35 3a

With this, pressing
  - "1", "2" or "3" (```ASC```) will send the corresponding strings defined.  
  - "d" will send the character codes 97..101, resulting in '```abcde```'.  
  - "h" will send the character codes 0x33, 0x34, 0x35, 0x3a, which should give '```123:```'.


---
## TODO
    - send files
    - trigger
    - new line on/off
    - optional delimiter for formatted output (e.g. CSV)
    - much more


---
## NEWS

### CHANGES 2026/03/28:
    - added local TX echo

### CHANGES 2026/03/27:
    - added macro system (configurable key bindings with ASC/DEC/HEX data)
    - config format: MACRO_<key>_<format>=<value> (e.g., MACRO_2_ASC=Hello, MACRO_L_HEX=aa bb e4)
    - added logging of received output to local file

### CHANGES 2026/03/25:
    - added DEC output mode (formatted, 3 digits with leading zeros)

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
