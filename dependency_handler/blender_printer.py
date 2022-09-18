from email import message
import bpy
from . import PrinterInterface, install_all_generator

class BlenderPrinter(PrinterInterface):
    '''A class representing Blender front-end. Creates a new Blender window with Text Editor ready to receive logs.'''
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
        self.log("Blender may be unresponsive during modules installation. Please wait until the end.\n")
        self.area.spaces[0].top = 0

    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def finish(self):
        self.log("\nPlease restart Blender and try again or save and show this log to the developer.")

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

def install_operator_factory(bl_info_name: str) -> bpy.types.Operator:
    '''Factory for modal operator that creates a new window and prints logs real time (though Blender will be only partialy responsive).'''
    def gen_modal(self, context, event):
        try:
            next(self.iterator)
            return {'RUNNING_MODAL'}
        except StopIteration:
            context.window_manager.event_timer_remove(self.timer)
            from . import DEPENDENCIES_IMPORTED
            if not DEPENDENCIES_IMPORTED:
                self.report(type={'ERROR'}, message="Installation failed. Check out logs in Text Editor...")
            return {'FINISHED'}

    def gen_invoke(self, context, event):
        self.iterator = iter(install_all_generator())
        self.timer = context.window_manager.event_timer_add(0.1, window=context.window)

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    return type(f"DEPS_OT_{bpy.path.clean_name(bl_info_name)}", (bpy.types.Operator,), {
        "bl_idname": f"dependencies.{bpy.path.clean_name(bl_info_name).lower()}",
        "bl_label": "Install Dependencies",
        "bl_options": {'INTERNAL'},
        "invoke": gen_invoke,
        "modal": gen_modal,
    })