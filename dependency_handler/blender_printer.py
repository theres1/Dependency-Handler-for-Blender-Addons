import queue
import subprocess
import sys
import threading
from typing import Callable
import bpy
from . import PrinterInterface, install_all_generator, list_module_updates, FROM
from . import deepreload

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
        run_in_main_thread(do)
    
    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def prepare(self):
        def do():
            text = self._get_text()
            text.clear()
        run_in_main_thread(do)

    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def finish(self):
        self.log("\nPlease restart Blender and try again or save and show this log to the developer.")
        run_in_main_thread(lambda: BlenderPrinter.unregister_timer())

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
    '''Factory for operator that installs dependencies and prints logs into new window in real-time.'''
    @classmethod
    def poll(cls, context):
        from . import DEPENDENCIES_IMPORTED
        return not DEPENDENCIES_IMPORTED

    def execute(self, context):
        def worker():
            global doing_something, doing_what
            doing_what = "Installing dependencies..."
            doing_something = True
            for _ in install_all_generator(): pass
            doing_something = False
        
        BlenderPrinter.register_timer()
        # Turn-on the worker thread.
        threading.Thread(target=worker, daemon=True).start()
        return {"FINISHED"}

    return type(f"DEPS_OT_{bpy.path.clean_name(bl_info_name)}", (bpy.types.Operator,), {
        "bl_idname": f"dependencies.{bpy.path.clean_name(bl_info_name).lower()}",
        "bl_label": "Install Dependencies",
        "bl_options": {'INTERNAL'},
        "__doc__": "Install addon's missing modules",
        "execute": execute,
        "poll": poll,
    })

def gui_operators_factory(bl_info_name: str):
    '''Factory for GUI operators. Returns a tuple that can be passed to gui factory.'''
    idname_change_version = f"dependencies.change_{bpy.path.clean_name(bl_info_name).lower()}"
    idname_update = f"dependencies.update_{bpy.path.clean_name(bl_info_name).lower()}"

    # I can't get annotations to work in the dynamic version but it looks as generating different class names is not really neccessary
    class DEPS_OT_InstallModuleVersion(bpy.types.Operator):
        '''Install different version of module'''
        bl_idname = idname_change_version
        bl_label = "Change Module Version"
        bl_options = {"INTERNAL"}

        module_name: bpy.props.StringProperty(default="", name="Module")
        
        versions = ('0.0.0')
        def _get_versions(self, context):
            return tuple((v, v, '', i) for i, v in enumerate(DEPS_OT_InstallModuleVersion.versions))

        choosen_version: bpy.props.EnumProperty(items=_get_versions,
            default=0,
            name="Version")
        
        def draw(self, context):
            layout = self.layout
            layout.label(text=self.dep.pip_name)
            col = layout.column(align=True)
            col.label(text="Changing package version may result in a cascade")
            col.label(text="upgrade/downgrade of its dependencies.")
            layout.prop(self, 'choosen_version')
        
        def invoke(self, context, event):
            self.dep = FROM(self.module_name)
            DEPS_OT_InstallModuleVersion.versions = self.dep.list_available()
            wm = context.window_manager
            return wm.invoke_props_dialog(self)

        def execute(self, context):
            @threaded
            def change(pip_name, choosen_version, module):
                global doing_something, doing_what, updatable_modules
                doing_what = "Reinstalling module..."
                doing_something = True
                proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--force-reinstall", f"{pip_name}=={choosen_version}"], capture_output=True, text=True)
                print(proc.returncode, proc.stdout, proc.stderr)
                deepreload.reload(module)
                updatable_modules = list_module_updates()
                doing_something = False
                _refresh_gui()
            change(self.dep.pip_name, self.choosen_version, self.dep.module)
            return {'FINISHED'}

    class DEPS_OT_UpdateModule(bpy.types.Operator):
        '''Update module'''
        bl_idname = idname_update
        bl_label = "Update Module"
        bl_options = {"INTERNAL"}

        module_name: bpy.props.StringProperty(default="", name="Module")

        def execute(self, context):
            @threaded
            def upgrade(module_name):
                global doing_something, doing_what, updatable_modules
                doing_something = True
                if module_name:
                    dependency = FROM(module_name)
                    doing_what = "Updating module... Please wait..."
                    proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", "--upgrade-strategy", "only-if-needed", f"{dependency.pip_name}"], capture_output=True, text=True)
                    print(proc.returncode, proc.stdout, proc.stderr)
                    doing_what = "Reloading module... Please wait..."
                    deepreload.reload(dependency.module)
                    doing_what = "Checking for module updates..."
                    updatable_modules = list_module_updates()
                else:
                    doing_what = "Updating all modules... Please wait..."
                    deps = {d.pip_name for d in get_all_dependiencies().values()}
                    installed_modules = set(updatable_modules.keys()) & deps
                    if installed_modules:
                        proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", "--upgrade-strategy", "only-if-needed"] + list(installed_modules), capture_output=True, text=True)
                        print(proc.returncode, proc.stdout, proc.stderr)
                        doing_what = "Reloading updated modules... Please wait..."
                        for dep in get_all_dependiencies().values():
                            if dep.imported:
                                deepreload.reload(dep.module)
                        doing_what = "Checking for module updates..."
                        updatable_modules = list_module_updates()

                doing_something = False
                _refresh_gui()
            
            upgrade(self.module_name if self.module_name else "")
            return {'FINISHED'}
    
    return (DEPS_OT_InstallModuleVersion, DEPS_OT_UpdateModule)

updatable_modules = {}
doing_something = False
doing_what = ""

execution_queue = queue.Queue()

def _queued_functions_timer():
    while not execution_queue.empty():
        function = execution_queue.get()
        function()
    return 0.5
    
# This function can safely be called in another thread.
# The function will be executed when the timer runs the next time.
def run_in_main_thread(function):
    '''Add function to the task queue. Use it to safely change values inside Blender.'''
    execution_queue.put(function)

def threaded(task: Callable):
    '''Decorator. Run function in a new thread.'''
    def thread_task(*args, **kwargs):
        def worker():
            task(*args, **kwargs)
            run_in_main_thread(lambda: bpy.app.timers.unregister(_queued_functions_timer))
        
        bpy.app.timers.register(_queued_functions_timer)
        threading.Thread(target=worker, daemon=True).start()

    return thread_task

@threaded
def check_module_upgrades_thread():
    '''Fill a list of upgradable modules used in GUI'''
    global updatable_modules, doing_something, doing_what
    doing_what = "Checking for module updates..."
    doing_something = True
    updatable_modules = list_module_updates()
    doing_something = False
    _refresh_gui()




from . import get_all_dependiencies
def create_gui(layout: bpy.types.UILayout, module_change_op: bpy.types.Operator, module_update_op: bpy.types.Operator):
    '''GUI generator. Use gui_operators_factory to generate required operators.'''
    layout.separator()

    def box_wrap(layout):
        return layout.box()

    if doing_something:
        layout.label(text=doing_what)
    
    col = layout.column()
    col.enabled = not doing_something


    grid = col.grid_flow(row_major=True, columns=4, align=True, even_columns=True)
    box_wrap(grid).label(text="Package")
    box_wrap(grid).label(text="Current")
    box_wrap(grid).label(text="Latest")
    box_wrap(grid).label(text="")
    box = col.box()
    grid = box.grid_flow(row_major=True, columns=4, align=True, even_columns=True)
    for dep in get_all_dependiencies().values():
        grid.label(text=dep.name)
        grid.label(text=dep.version) # current
        grid.label(text=updatable_modules[dep.pip_name][1] if dep.pip_name in updatable_modules else "") # latest
        sub = grid.row(align=True)
        sub.enabled = dep.imported
        subcol = sub.column(align=True)
        subcol.enabled = dep.pip_name in updatable_modules and dep.version != updatable_modules[dep.pip_name][1]
        subcol.operator(module_update_op.bl_idname, text="Update").module_name = dep.name
        sub.operator(module_change_op.bl_idname, text="", icon="THREE_DOTS").module_name = dep.name

    box.operator(module_update_op.bl_idname, text="Update All").module_name = ""

def _refresh_gui():
    def do():
        for screen in bpy.data.screens:
            for area in screen.areas:
                area.tag_redraw()
    run_in_main_thread(do)