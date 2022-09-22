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
IMPORT(('Non_Existing_Module4', ("1.5.0", None)))
FROM(('PIL', 'Pillow', ("9.2.0", "9.1.9"))).IMPORT('Image', 'ImageCms')

dp.check_all_loaded()

# Import once again to make these modules visible to code completion
if dp.DEPENDENCIES_IMPORTED:
    import NEM, Non_Existing_Module2
    import Non_Existing_Module4
    from PIL import Image, ImageCms

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
    
    # Add these optional properties to the addon preferences, if you want these functionalities turned on.
    # Check-for-updates-on-start and pop-up notification will be disabled without them.
    dependencies_check_on_start: bpy.props.BoolProperty(default=True, name="Check for module updates on start")
    dependencies_show_popup: bpy.props.BoolProperty(default=True, name="Show pop-up notification.")
    
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
    PREFS_PT_DepAddonExample,
 ) + gui_ops

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Check for available updates to installed packages (for GUI).
    # GUI operators tuple needs to be passed if aformentioned AddonPreferences properties are set
    check_module_upgrades_thread(gui_ops_tuple=gui_ops)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)