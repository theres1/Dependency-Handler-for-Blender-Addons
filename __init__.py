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

from . dependency_handler.blender_printer import BlenderPrinter, install_operator_factory
from . dependency_handler import FROM, IMPORT
from . import dependency_handler as dp

dp.init(
    [('NEM', 'Non_Existing_Module'), 'Non_Existing_Module2'],
    module_globals=globals(),
    printers=[BlenderPrinter(f"Dependency Log of {bl_info['name']}"),
    ])
FROM('Non_Existing_Module3').IMPORT('Sub1', 'Sub2')
IMPORT('Non_Existing_Module4')

dp.check_all_loaded()

# Import once again to make these modules visible to code completion
if dp.DEPENDENCIES_IMPORTED:
    import NEM, Non_Existing_Module2
    from Non_Existing_Module3 import Sub1, Sub2
    import Non_Existing_Module4

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
            layout.operator(OT_ModalInstall.bl_idname)

# Use factory to create modal operator that will handle drawing logs in real time.
# Blender will not be responsive during modules installation but pip logs will be printed immediately.
OT_ModalInstall = install_operator_factory(bl_info['name'])

classes = {
    OT_ModalInstall,
    OBJECT_PT_DepAddonExample
}

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)