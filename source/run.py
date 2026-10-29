"""Desktop entry point; never print private exceptions."""
import sys

if __name__ == "__main__":
    try:
        from meetinglight.app import main
        main()
    except Exception:
        if "--smoke" in sys.argv:
            print('{"ok": false, "error": "Application check failed; private details suppressed"}')
            sys.exit(1)
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,
            "Meeting Light could not start. Check the Python environment and encrypted data access. "
            "No private details have been logged.", "Meeting Light", 0x10)
        sys.exit(1)
