"""Desktop entry point; never print private exceptions."""
import sys

if __name__ == "__main__" and sys.argv[1:2] == ["--parse-calendar"]:
    # Calendar worker: import only the parser, never the desktop UI.
    from meetinglight.feeds import parse_worker
    sys.exit(parse_worker(sys.argv[2:]))

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
