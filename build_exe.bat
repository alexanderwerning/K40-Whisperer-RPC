PROMPT $g
rem ---------------------------------------------------------------------
rem This file executes the build command for the windows executable file.
rem It is here because I am lazy
rem ---------------------------------------------------------------------
del *.pyc
rmdir /S /Q dist
rmdir /S /Q dist32
rmdir /S /Q dist64

python py2exe_setup.py py2exe
rmdir /S /Q build
move dist dist32
robocopy icons dist32/icons /E
rem pause

del *.pyc
python py2exe_setup.py py2exe
rmdir /S /Q build
move dist dist64
robocopy icons dist64/icons /E
pause