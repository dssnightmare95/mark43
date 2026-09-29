@echo off
REM Windows launcher to uninstall the action-capture integration.
REM Removes the MCP server, hooks, AGENTS.md block and skill it added.
python "%~dp0install.py" --uninstall %*
pause
