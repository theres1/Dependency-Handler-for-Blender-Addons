bl_info = {
    "name" : "Dependency Handler Example Addon",
    "author" : "theres1",
    "description" : "",
    "blender" : (3, 2, 0),
    "version" : (0, 0, 1),
    "location" : "Object Properties -> Dependency Addon Example",
    "warning" : "",
    "category" : "Test"
}

import bpy

from . dependency_handler.blender_printer import BlenderPrinter, check_module_upgrades_thread, gui_operators_factory, install_operator_factory
from . dependency_handler import FROM, IMPORT
from . import dependency_handler as dp
from . dependency_handler import blender_printer

dp.init(
    [('NEM', 'Non_Existing_Module'), 'Non_Existing_Module2'],
    module_globals=globals(),
    printers=[BlenderPrinter(f"Dependency Log of {bl_info['name']}"),
    ])
FROM('Non_Existing_Module3').IMPORT('Sub1', 'Sub2')
IMPORT('Non_Existing_Module4')
FROM(('PIL', 'Pillow')).IMPORT('Image', 'ImageCms')

dp.check_all_loaded()


from . dependency_handler import deepreload

print(1, FROM('PIL').module.__version__)
import subprocess, sys
# proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", "--upgrade-strategy", "only-if-needed", "Pillow==9.2.0"], capture_output=True, text=True);print(proc.stdout, proc.stderr)
# proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", "--upgrade-strategy", "only-if-needed", "Pillow"], capture_output=True, text=True);print(proc.stdout, proc.stderr)
# proc = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--force-reinstall", "Pillow==9.1.1"], capture_output=True, text=True);print(proc.stdout, proc.stderr)
# deepreload.reload(FROM('PIL').module)
print(2, FROM('PIL').module.__version__)

# Import once again to make these modules visible to code completion
if dp.DEPENDENCIES_IMPORTED:
    import NEM, Non_Existing_Module2
    from Non_Existing_Module3 import Sub1, Sub2
    import Non_Existing_Module4
    from PIL import Image, ImageCms

# updatable_modules = dp.list_module_updates()
# updatable_modules = {'astroid': ('2.12.9', '2.12.10'), 'autopep8': ('1.6.0', '1.7.0'), 'certifi': ('2021.10.8', '2022.9.14'), 'charset-normalizer': ('2.0.10', '2.1.1'), 'Cython': ('0.29.26', '0.29.32'), 'debugpy': ('1.6.2', '1.6.3'), 'idna': ('3.3', '3.4'), 'networkx': ('2.8', '2.8.6'), 'numpy': ('1.22.0', '1.23.3'), 'Pillow': ('9.1.1', '9.2.0'), 'pycodestyle': ('2.8.0', '2.9.1'), 'pyexiv2': ('2.7.1', '2.8.0'), 'requests': ('2.27.1', '2.28.1'), 'setuptools': ('58.1.0', '65.3.0'), 'urllib3': ('1.26.8', '1.26.12'), 'zstandard': ('0.16.0', '0.18.0')}

class OBJECT_PT_DepAddonExample(bpy.types.Panel):
    bl_label = "Dependency Addon Example"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    def draw(self, context):
        layout = self.layout
        if dp.DEPENDENCIES_IMPORTED:
            layout.label(text="All imported")
        else:
            layout.label(text="Button to install all missing dependencies")
            layout.operator(OT_ThreadedInstall.bl_idname)
        
        layout.separator()

        layout.label(text="Optional dependencies manager:")
        blender_printer.create_gui(layout, *gui_ops)

class PREFS_PT_DepAddonExample(bpy.types.AddonPreferences):
    bl_idname = __package__
    def draw(self, context):
        layout = self.layout
        layout.operator(OT_ThreadedInstall.bl_idname)
        
        blender_printer.create_gui(layout, *gui_ops)

# Create operator that will handle drawing logs in real time.
# Blender will be responsive during modules installation and pip logs will be printed immediately in new window.
OT_ThreadedInstall = install_operator_factory(bl_info['name'])

# If you want to use dependencies GUI, generate a tuple with operators
gui_ops = gui_operators_factory(bl_info['name'])


classes = (
    OT_ThreadedInstall,
    OBJECT_PT_DepAddonExample,
 ) + gui_ops

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Check for available updates to installed packages (for GUI).
    check_module_upgrades_thread()

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)