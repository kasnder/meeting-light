"""Desktop entry point; never print private exceptions."""
import sys

if __name__ == "__main__":
    try:
        from meetinglight.app import main
        main()
    except Exception:
        if "--self-check" in sys.argv:
            print('{"ok": false, "error": "Application check failed; private details suppressed"}')
            sys.exit(1)
        from tkinter import messagebox
        messagebox.showerror("Meeting Light",
            "Meeting Light could not start. Check the Python environment and encrypted data access. "
            "No private details have been logged.")
        sys.exit(1)
