import bpy
from . import PrinterInterface


class BlenderPrinter(PrinterInterface):
    area = None

    def __init__(self, logname):
        self.logname = logname

    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def log(self, *msg: list):
        msg = '\n' + " ".join(map(str, map(str, msg))).rstrip()
        if not (self.area and len(self.area.spaces) and self.area.type=='TEXT_EDITOR'):
            self.area = self._create_text_window()
        text = self._get_text()
        self.area.spaces[0].text = text
        text.cursor_set(len(text.lines), character=len(text.lines[-1].body))
        text.write(msg)
    
    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def prepare(self):
        text = self._get_text()
        text.clear()

    def _get_text(self) -> bpy.types.Text:
        if self.logname in bpy.data.texts:
            return bpy.data.texts[self.logname]
        else:
            text = bpy.data.texts.new(self.logname)
            text.use_fake_user = False
            return text

    def _create_text_window(self)-> bpy.types.Area:
        # Call user prefs window
        bpy.ops.screen.userpref_show("INVOKE_DEFAULT")

        # Change area type
        area = bpy.context.window_manager.windows[-1].screen.areas[0]
        area.type = "TEXT_EDITOR"
        area.spaces[0].show_region_footer = False
        area.spaces[0].show_word_wrap=True
        return area