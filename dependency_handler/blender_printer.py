import queue
import threading
import bpy
from . import PrinterInterface, install_all_generator

class BlenderPrinter(PrinterInterface):
    '''
    A class representing Blender front-end. Creates a new Blender window with Text Editor ready to receive logs.
    Before printing, task queue have to be registered with register_timer(). finish() method invokes unregister_timer()

    register_timer() is not invoked in prepare() because the latter is supposed to be run in new thread.
    '''
    area = None

    def __init__(self, logname):
        self.logname = logname

    @staticmethod
    def register_timer():
        bpy.app.timers.register(_queued_functions_timer)

    @staticmethod
    def unregister_timer():
        bpy.app.timers.unregister(_queued_functions_timer)
    
    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def log(self, *msg: list):
        msg = '\n' + " ".join(map(str, map(str, msg))).rstrip()
        def do():
            if not (self.area and len(self.area.spaces) and self.area.type=='TEXT_EDITOR'):
                self.area = self._create_text_window()
            text = self._get_text()
            self.area.spaces[0].text = text
            text.cursor_set(len(text.lines), character=len(text.lines[-1].body))
            text.write(msg)
        _run_in_main_thread(do)
    
    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def prepare(self):
        # bpy.app.timers.register(_queued_functions_timer)
        def do():
            text = self._get_text()
            text.clear()
        _run_in_main_thread(do)

    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def finish(self):
        self.log("\nPlease restart Blender and try again or save and show this log to the developer.")
        _run_in_main_thread(lambda: BlenderPrinter.unregister_timer())

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

execution_queue = queue.Queue()

def _queued_functions_timer():
    while not execution_queue.empty():
        function = execution_queue.get()
        function()
    return 0.5
    
# This function can safely be called in another thread.
# The function will be executed when the timer runs the next time.
def _run_in_main_thread(function):
    execution_queue.put(function)

def install_operator_factory(bl_info_name: str) -> bpy.types.Operator:
    '''Factory for modal operator that creates a new window and prints logs real time (though Blender will be only partialy responsive).'''
    def execute(self, context):
        def worker():
            for _ in install_all_generator(): pass
        
        BlenderPrinter.register_timer()
        # Turn-on the worker thread.
        threading.Thread(target=worker, daemon=True).start()
        return {"FINISHED"}

    return type(f"DEPS_OT_{bpy.path.clean_name(bl_info_name)}", (bpy.types.Operator,), {
        "bl_idname": f"dependencies.{bpy.path.clean_name(bl_info_name).lower()}",
        "bl_label": "Install Dependencies",
        "bl_options": {'INTERNAL'},
        "execute": execute,
    })