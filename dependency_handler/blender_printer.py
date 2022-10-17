'''
This submodule contains BlenderPrinter implementation and utilities to invoke subprocesses and print their output in a thread-safe way.
Helper utilities:
@threaded: decorator to run functions in a new thread
run_in_main_thread: function that takes a callback function that will be safely run in the Blender main thread
execute_process: function to run subprocess and log its output
TaskQueue: a class to create a queue of ordered tasks that will run in a new thread
'''
from functools import partial
import queue
import site
import subprocess
import sys
import threading
from time import sleep
from typing import Callable
import bpy
from . import PrinterInterface, install_all_generator, list_module_updates, FROM
from . import restart_needed, _log
# from . import deepreload

class BlenderPrinter(PrinterInterface):
    '''
    A class representing Blender front-end. Creates a new Blender window with Text Editor ready to receive logs.
    Before printing, task queue have to be registered with register_timer(). finish() method invokes unregister_timer()
    register_timer() is not invoked in prepare() because the latter is supposed to be run in new thread.
    '''

    def __init__(self, logname):
        self.logname = logname

    @staticmethod
    def register_timer():
        if not bpy.app.timers.is_registered(_queued_functions_timer):
            bpy.app.timers.register(_queued_functions_timer)

    @staticmethod
    def unregister_timer():
        def do():
            if bpy.app.timers.is_registered(_queued_functions_timer):
                bpy.app.timers.unregister(_queued_functions_timer)
        run_in_main_thread(do)
    
    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def log(self, *msg: list):
        msg = '\n' + " ".join(map(str, msg)).rstrip()
        def do():
            area = self._create_text_window()
            text = self._get_text()
            area.spaces[0].text = text
            text.cursor_set(len(text.lines), character=len(text.lines[-1].body))
            text.write(msg)
        run_in_main_thread(do)
    
    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def prepare(self, clear=True):
        # BlenderPrinter.register_timer()
        clear_ = clear
        def do():
            text = self._get_text()
            if clear_:
                text.clear()
        run_in_main_thread(do)

    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def finish(self):
        # self.log("\nPlease restart Blender and try again or save and show this log to the developer.")
        # BlenderPrinter.unregister_timer()
        pass

    def _get_text(self) -> bpy.types.Text:
        if self.logname in bpy.data.texts:
            return bpy.data.texts[self.logname]
        else:
            text = bpy.data.texts.new(self.logname)
            text.use_fake_user = False
            return text
    
    def _create_text_window(self)-> bpy.types.Area:
        for window in bpy.context.window_manager.windows:
            if len(window.screen.areas) == 1:
                area = window.screen.areas[0]
                if area.type == 'TEXT_EDITOR':
                    return area
        
        # Call user prefs window
        bpy.ops.screen.userpref_show("INVOKE_DEFAULT")

        # Change area type
        area = bpy.context.window_manager.windows[-1].screen.areas[0]
        area.type = "TEXT_EDITOR"
        area.spaces[0].show_region_footer = False
        area.spaces[0].show_word_wrap=True
        return area

def fast_log(*msg):
    '''Quick logging to new window from thread (BlenderPrinter.log puts into queue)'''
    from . import all_printers
    for printer in all_printers:
        printer.log(*msg)

def install_operator_factory(bl_info_name: str, *, callback: Callable=None) -> bpy.types.Operator:
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
            run_in_main_thread(partial(callback, context))
            BlenderPrinter.unregister_timer()
        
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

def _parse_out(proc: subprocess.CompletedProcess):
    last_line = ""
    if proc.stdout:
        last_line = proc.stdout.splitlines()[-1]
    if any(string in last_line for string in ("Successfully", "Requirement already satisfied")):
        fast_log(proc.stdout)
        fast_log("\n", "Some temporary directories might have been left undeleted. You can remove them after closing Blender.")
        fast_log("All folders whose names start with ~ (tilde) can be safely removed from:")
        fast_log(site.getusersitepackages())
    else:
        fast_log("\n", proc.args)
        fast_log("\n", proc.stdout)
        fast_log("\n", proc.stderr)

def gui_operators_factory(bl_info_name: str):
    '''Factory for GUI operators. Returns a tuple that can be passed to gui factory.'''
    clean_name = bpy.path.clean_name(bl_info_name).lower()
    idname_change_version = f"dependencies.change_{clean_name}"
    idname_update = f"dependencies.update_{clean_name}"
    idname_find_updates = f"dependencies.find_updates_{clean_name}"
    idname_list_versions = f"dependencies.list_versions_{clean_name}"
    idname_update_popup = f"dependencies.update_popup_{clean_name}"

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
                    package_name = dependency.pip_name
                    match self.version_range:
                        case (str(), None):
                            package_name += f'>={dependency.version_range[0]}'
                        case (None, str()):
                            package_name += f'<={dependency.version_range[1]}'
                        case (str(), str()):
                            package_name += f'>={dependency.version_range[0]},<={dependency.version_range[1]}'
                    proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", "--upgrade-strategy", "only-if-needed", f"{package_name}"], capture_output=True, text=True)
                    _parse_out(proc)
                    restart_needed(True)
                    fast_log("\n", "Modules need to be reloaded. Please restart Blender.")
                    # Reloading does not work with some packages. Removed for now.
                    # doing_what = "Reloading module... Please wait..."
                    # try:
                    #     deepreload.reload(dependency.module)
                    #     doing_what = "Checking for module updates..."
                    #     updatable_modules = list_module_updates()
                    # except:
                    #     fast_log("\n", "Reloading modules failed. Please restart Blender.")
                else:
                    # Does not really work. pip temp dirs of upgraded modules cannot be deleted because they are still in use by Blender.
                    # This interrupts the installation of modules in the middle of the list.
                    # For now I removed Update All from the GUI
                    doing_what = "Updating all modules... Please wait..."
                    deps = {d.pip_name for d in get_all_dependiencies().values()}
                    installed_modules = set(updatable_modules.keys()) & deps
                    if installed_modules:
                        proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", "--upgrade-strategy", "only-if-needed"] + list(installed_modules), capture_output=True, text=True)
                        _parse_out(proc)
                        restart_needed(True)
                        fast_log("\n", "Modules need to be reloaded. Please restart Blender.")

                        # doing_what = "Reloading updated modules... Please wait..."
                        # for dep in get_all_dependiencies().values():
                        #     if dep.imported:
                        #         try:
                        #             deepreload.reload(dep.module)
                        #         except:
                        #             fast_log("\n", "Reloading modules failed. Please restart Blender.")
                        # doing_what = "Checking for module updates..."
                        # updatable_modules = list_module_updates()

                doing_something = False
                _refresh_gui()
            
            upgrade(self.module_name if self.module_name else "")
            return {'FINISHED'}

    # I can't get annotations to work in the dynamic version but it looks as generating different class names is not really neccessary
    class DEPS_OT_ChangeModuleVersion(bpy.types.Operator):
        '''Install different version of module'''
        bl_idname = idname_change_version
        bl_label = "Change Module Version"
        bl_options = {"INTERNAL"}

        module_name: bpy.props.StringProperty(default="", name="Module")
        
        def _get_versions(self, context):
            return tuple((v, v, '', i) for i, v in enumerate(module_versions))

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
            if not self.module_name:
                self.report(type={"ERROR"}, message="Module name cannot be empty.")
                return {"FINISHED"}
            self.dep = FROM(self.module_name)
            wm = context.window_manager
            return wm.invoke_props_dialog(self)

        def execute(self, context):
            if not self.module_name:
                self.report(type={"ERROR"}, message="Module name cannot be empty.")
                return {"FINISHED"}
            
            @threaded
            def change(pip_name, choosen_version, module):
                global doing_something, doing_what, updatable_modules
                doing_what = "Reinstalling module..."
                doing_something = True
                proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", f"{pip_name}=={choosen_version}"], capture_output=True, text=True)
                _parse_out(proc)
                restart_needed(True)
                fast_log("\n", "Modules need to be reloaded. Please restart Blender.")

                # try:
                #     deepreload.reload(module)
                # except:
                #     fast_log("\n", "Reloading modules failed. Please restart Blender.")
                # updatable_modules = list_module_updates()

                doing_something = False
                _refresh_gui()
            change(self.dep.pip_name, self.choosen_version, self.dep.module)
            return {'FINISHED'}
    
    class DEPS_OT_ListVersions(bpy.types.Operator):
        '''List available module versions'''
        bl_idname = idname_list_versions
        bl_label = "List Versions"
        bl_options = {"INTERNAL"}

        module_name: bpy.props.StringProperty(default="", name="Module")

        def execute(self, context):
            @threaded
            def do(module_name):
                global module_versions, doing_something, doing_what
                doing_something = True
                doing_what = "Listing available versions... Please wait..."
                dep = FROM(module_name)
                module_versions = dep.list_available()
                doing_something = False
                _refresh_gui()
                # run_in_main_thread(lambda: bpy.ops.dependencies.change_dependency_handler_example_addon('INVOKE_DEFAULT', module_name=module_name))
                run_in_main_thread(lambda: getattr(bpy.ops.dependencies, DEPS_OT_ChangeModuleVersion.bl_idname.split('.')[1])('INVOKE_DEFAULT', module_name=module_name))
            do(self.module_name)
            return {'FINISHED'}

    class DEPS_OT_FindUpdates(bpy.types.Operator):
        '''Check for module updates'''
        bl_idname = idname_find_updates
        bl_label = "Check for module updates"
        bl_options = {"INTERNAL"}

        def execute(self, context):
            check_module_upgrades_thread(_force_check=True)
            return {'FINISHED'}
    
    class DEPS_OT_UpdatePopup(bpy.types.Operator):
        '''Check for module updates'''
        bl_idname = idname_update_popup
        bl_label = "Dependency Manager"
        bl_options = {"INTERNAL"}

        def draw(self, context):
            layout = self.layout
            col = layout.column(align=True)
            col.label(text=bl_info_name)
            col.label(text="Dependencies can be upgraded.")
            create_gui(layout, DEPS_OT_ChangeModuleVersion, DEPS_OT_UpdateModule, DEPS_OT_FindUpdates, DEPS_OT_ListVersions)

        def invoke(self, context, event):
            wm = context.window_manager
            return wm.invoke_props_dialog(self)

        def execute(self, context):
            return {'FINISHED'}
    
    return (DEPS_OT_ChangeModuleVersion, DEPS_OT_UpdateModule, DEPS_OT_FindUpdates, DEPS_OT_ListVersions, DEPS_OT_UpdatePopup)

updatable_modules = {}
doing_something = False
doing_what = ""
module_upgrades_checked = False
module_versions = ()

execution_queue = queue.Queue()

def _queued_functions_timer():
    while not execution_queue.empty():
        function = execution_queue.get()
        function()
    return 0.25
    
# This function can safely be called in another thread.
# The function will be executed when the timer runs the next time.
def run_in_main_thread(function):
    '''Add function to the task queue. Use it to safely change values inside Blender.'''
    execution_queue.put(function)

def threaded(task: Callable):
    '''Decorator. Run function in a new thread.'''
    def thread_task(*args, **kwargs):
        def worker():
            try:
                task(*args, **kwargs)
            finally:
                run_in_main_thread(lambda: BlenderPrinter.unregister_timer())
            # run_in_main_thread(lambda: bpy.app.timers.unregister(_queued_functions_timer))
        
        # bpy.app.timers.register(_queued_functions_timer)
        BlenderPrinter.register_timer()
        threading.Thread(target=worker, daemon=True).start()

    return thread_task

def _should_check_on_start(addon_prefs):
    return hasattr(addon_prefs, 'dependencies_check_on_start') and addon_prefs.dependencies_check_on_start

def _should_show_popup_on_start(addon_prefs):
    return hasattr(addon_prefs, 'dependencies_show_popup') and addon_prefs.dependencies_show_popup

@threaded
def check_module_upgrades_thread(gui_ops_tuple=None, *, _force_check=False):
    '''
    Fill a list of upgradable modules used in GUI.
    :param gui_ops_tuple: a tuple returned by gui_operators_factory()
    :type: tuple[bpy.types.Operator, bpy.types.Operator, bpy.types.Operator, bpy.types.Operator, bpy.types.Operator]
    '''
    addon_prefs = bpy.context.preferences.addons[addon_package].preferences
    if not _should_check_on_start(addon_prefs) and not _force_check:
        return
    if _should_check_on_start(addon_prefs) and not gui_ops_tuple:
        raise ValueError("gui_ops_tuple must be defined")

    global updatable_modules, doing_something, doing_what, module_upgrades_checked
    module_upgrades_checked = True
    doing_what = "Checking for module updates..."
    doing_something = True
    updatable_modules = list_module_updates()
    doing_something = False
    _refresh_gui()
    if _should_check_on_start(addon_prefs) and _should_show_popup_on_start(addon_prefs):
        installed_modules = {d.pip_name for d in get_all_dependiencies().values() if d.pip_name in updatable_modules.keys() and _update_in_range(updatable_modules[d.pip_name][1], d)}
        if not installed_modules:
            return
        # open pop-up
        run_in_main_thread(lambda: getattr(bpy.ops.dependencies, gui_ops_tuple[4].bl_idname.split('.')[1])('INVOKE_DEFAULT'))



addon_package = __package__.split('.')[0]

from . import get_all_dependiencies
def create_gui(layout: bpy.types.UILayout,
        module_change_op: bpy.types.Operator,
        module_update_op: bpy.types.Operator,
        module_find_updates_op: bpy.types.Operator,
        module_list_versions_op: bpy.types.Operator,
        *args
        ):
    '''GUI generator. Use gui_operators_factory to generate required operators.'''
    layout.separator()

    def box_wrap(layout):
        return layout.box()

    if doing_something:
        layout.label(text=doing_what)
    
    col = layout.column()
    col.enabled = not doing_something

    if restart_needed():
        box = col.box()
        box.label(text="Modules need to be reloaded. Please restart Blender.")
    else:
        if not module_upgrades_checked:
            col.operator(module_find_updates_op.bl_idname)
        
        grid = col.grid_flow(row_major=True, columns=4, align=True, even_columns=True)
        box_wrap(grid).label(text="Package")
        box_wrap(grid).label(text="Current")
        box_wrap(grid).label(text="Latest")
        box_wrap(grid).label(text="")
        box = col.box()
        grid = box.grid_flow(row_major=True, columns=4, align=True, even_columns=True)
        for dep in get_all_dependiencies().values():
            grid.label(text=dep.name)
            vmin, vmax = dep.version_range
            if vmin or vmax:
                vmin = vmin if vmin else ""
                vmax = vmax if vmax else ""
                version_range_str = f"<{vmin}, {vmax}>"
                grid.label(text=f"{dep.version} {version_range_str}") # current (wrong version)
            else:
                grid.label(text=dep.version) # current
            
            upd_cur, upd_lat = updatable_modules[dep.pip_name] if dep.pip_name in updatable_modules else ("","")
            grid.label(text=upd_lat if dep.pip_name in updatable_modules else "") # latest
            sub = grid.row(align=True)
            sub.enabled = dep.module is not None
            subcol = sub.column(align=True)
            subcol.enabled = dep.pip_name in updatable_modules and dep.version != upd_lat
            subcol.enabled &= _update_in_range(upd_lat, dep)
            

            subcol.operator(module_update_op.bl_idname, text="Update").module_name = dep.name
            sub.operator(module_list_versions_op.bl_idname, text="", icon="THREE_DOTS").module_name = dep.name

        # if module_upgrades_checked:
        #     box.operator(module_update_op.bl_idname, text="Update All").module_name = ""

    addon_prefs = bpy.context.preferences.addons[addon_package].preferences
    col = layout.column(align=True)
    if hasattr(addon_prefs, 'dependencies_check_on_start'):
        col.prop(addon_prefs, 'dependencies_check_on_start')
    if hasattr(addon_prefs, 'dependencies_show_popup'):
        col.prop(addon_prefs, 'dependencies_show_popup')

def _update_in_range(latest, dep):
    if dep.module is None:
        return False
    vmin, vmax = dep.version_range
    if not (vmin or vmax):
        return True
    
    ret = True
    if vmin:
        ret &= latest >= vmin
    if vmax:
        ret &= latest <= vmax
    return ret

def _refresh_gui():
    def do():
        for screen in bpy.data.screens:
            for area in screen.areas:
                area.tag_redraw()
    run_in_main_thread(do)

########################################
########### HELPER FUNCTIONS ###########
########################################

@threaded
def execute_process(args, **kvargs):
    '''Helper function. Run a process and log to printers.'''
    print(args, kvargs)
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True, **kvargs) as p:
        for line in p.stdout:
            _log('>>', line)

    if p.returncode != 0:
        _log(f"Exit code: {p.returncode}")
        raise subprocess.CalledProcessError(p.returncode, p.args)

class TaskQueue:
    READY=0
    WAIT=1
    CANCELLED=2
    def __init__(self):
        self.tasks = []

    def add_condition(self, callback):
        '''Starting condition of the queue (like finished rendering)'''
        def cond():
            while True:
                ret = callback(self)
                match ret:
                    case TaskQueue.READY:
                        return
                    case TaskQueue.WAIT:
                        sleep(0.5)
                    case TaskQueue.CANCELLED:
                        return TaskQueue.CANCELLED
        self.tasks.append(cond)

    def add_task(self, callback, *args, **kvargs):
        self.tasks.append(partial(callback, *args, **kvargs))

    def add_exec(self, args, callback=None, **kvargs):
        def task():
            # print('Run:', args, kvargs)
            _log('Run:', args, kvargs)
            with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True, **kvargs) as p:
                for line in p.stdout:
                    # print(line)
                    _log('>>', line)

            if p.returncode != 0:
                _log(f"Exit code: {p.returncode}")
                raise subprocess.CalledProcessError(p.returncode, p.args)
            
            if callback:
                callback(self)
        self.tasks.append(task)
    
    @threaded
    def run(self):
        for task in self.tasks:
            if task():
                break