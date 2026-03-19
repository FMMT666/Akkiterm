Akkiterm
========

A yet quick and dirty serial terminal application for the console.  
Useful for coomunication with MCUs, debugging, etc.  

Works on all platforms which support Python and PySerial. 

---------------------------------------------------------------------------------------------

Not nearly there yet; not even in the same universe, but I always
wanted a simple macOS console replacement for the great RealTerm Windoze app.  

I often work with small controllers, like PICs, NECs (oops Renesas'), etc. and
a simple serial connection is still the way to go for lab equipment, debugging,
dataloggers or configuration.

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

This should be self explanatory (for now).



---
## TODO
    - switch to English
    - HEX output
    - HEX input
    - new line on/off
    - send makros
    - send files
    - many, many more


---
## NEWS

### CHANGES 2026/03/18:
    - initial version


---
Have fun  
FMMT666(ASkr)  


[1]: https://pyserial.readthedocs.io
[2]: https://sourceforge.net/projects/realterm/
