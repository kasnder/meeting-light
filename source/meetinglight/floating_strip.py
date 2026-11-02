"""Optional Windows next-meeting strip. All methods run on the Tk thread."""
import tkinter as tk
from . import platform_api as platform


def clamp_position(position, size, areas, margin=12):
    """Keep the whole strip in a usable monitor area; recover missing monitors."""
    width, height = size
    primary = areas[0]
    valid = (isinstance(position, (list, tuple)) and len(position) == 2
             and all(isinstance(n, int) and not isinstance(n, bool) for n in position))
    if valid:
        x, y = position
        area = next((a for a in areas if a[0] <= x < a[2] and a[1] <= y < a[3]), primary)
    else:
        area = primary
        x, y = area[2] - width - margin, area[3] - height - margin
    left, top, right, bottom = area
    return max(left, min(x, right-width)), max(top, min(y, bottom-height))


class FloatingStrip:
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root, takefocus=False)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.label = tk.Label(self.window, padx=14, pady=9, cursor='hand2',
                              font=('Segoe UI', 10), bd=1, relief='solid')
        self.label.pack()
        self.event = None
        self.drag = None
        self.menu = tk.Menu(self.window, tearoff=False)
        self.menu.add_command(label='Settings', command=app.show_settings)
        self.menu.add_command(label='Reset position', command=self.reset)
        self.menu.add_command(label='Hide strip', command=app.toggle_strip)
        self.label.bind('<ButtonPress-1>', self.press)
        self.label.bind('<B1-Motion>', self.motion)
        self.label.bind('<ButtonRelease-1>', self.release)
        self.label.bind('<Button-3>', self.context)

    def context(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def press(self, event):
        self.drag = (event.x_root, event.y_root, self.window.winfo_x(), self.window.winfo_y())
        self.moved = False

    def motion(self, event):
        if self.drag:
            x, y, wx, wy = self.drag
            if abs(event.x_root-x) + abs(event.y_root-y) > 4:
                self.moved = True
            if self.moved:
                self.place((wx+event.x_root-x, wy+event.y_root-y))

    def release(self, event):
        if not self.drag:
            return
        self.drag = None
        if self.moved:
            self.app.settings['floating_strip_position'] = [self.window.winfo_x(), self.window.winfo_y()]
            self.app.save_config()
        elif self.event:
            platform.bring_to_front(self.app.root)
            if self.app.tree.exists(self.event.key):
                self.app.tree.selection_set(self.event.key)
                self.app.tree.see(self.event.key)

    def place(self, position):
        self.window.update_idletasks()
        areas = platform.monitor_work_areas()
        anchor = clamp_position(position, (0, 0), areas)
        area = next((a for a in areas if a[0] <= anchor[0] <= a[2] and a[1] <= anchor[1] <= a[3]), areas[0])
        width = min(self.label.winfo_reqwidth(), area[2]-area[0])
        height = self.label.winfo_reqheight()
        x, y = clamp_position(position, (width, height), areas)
        # Tk treats negative geometry offsets as distances from the right/bottom.
        platform.position_strip(self.window, x, y, width, height)

    def reset(self):
        self.app.settings['floating_strip_position'] = None
        self.app.save_config()
        self.place(None)

    def update(self, text, event, stale):
        self.event = event
        if (not self.app.settings['floating_strip'] or not text or not event
                or self.app.locked or platform.foreground_fullscreen()):
            self.window.withdraw()
            return
        self.label.configure(text=('⚠ ' if stale else '') + text,
                             background='#fff3d6' if stale else self.app.background,
                             foreground='#805000' if stale else '#202020')
        if not self.drag:
            self.place(self.app.settings['floating_strip_position'])
        platform.show_strip_without_focus(self.window)
