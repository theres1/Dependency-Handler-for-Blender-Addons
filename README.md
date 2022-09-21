# Dependency-Handler-for-Blender-Addons
## Automatic module installation via pip, handling exceptions, configurable output printing in Blender addons.

[![Real time logging](https://img.youtube.com/vi/zgJLy2tE1-0/0.jpg)](https://www.youtube.com/watch?v=zgJLy2tE1-0)

![Dependency GUI](https://github.com/theres1/Dependency-Handler-for-Blender-Addons/blob/main/gui.jpg?raw=true)

Module that allows easy handling of dependencies, created mainly for Blender add-ons.

Usage Examples:

Import output printing front-ends:
```
    from . dependency_handler.blender_printer import BlenderPrinter
    from . dependency_handler import FilePrinter
```
BlenderPrinter - creates a new Blender window with Text Editor and writes logs into text file.
FilePrinter - writes logs into text file. By default, text file is created next to __file__.
```
    from . import dependency_handler
    from . dependency_handler import FROM, IMPORT
```
Initialise dependencies. Already installed modules will be imported during initialisation.
```
    dependency_handler.init([('PIL', 'Pillow'), 'AnyModule'], module_globals=globals(), printers=[BlenderPrinter("Dependency Log of My Addon"), FilePrinter()])
    FROM('PIL').IMPORT('ImageCms', 'Image') # or FROM(('PIL', 'Pillow')).IMPORT('ImageCms', 'Image')
    IMPORT('AnyModule2')
```
Dependencies can be initialised by init, FROM and IMPORT functions. Use tuple (module_name, pip_name) for modules that need different names for pip installing and importing.
Pass globals() as a module_globals parameter to import modules into global namespace.
State of all dependencies can be tracked by dependency_handler.check_all_loaded() function returning True if all dependencies are imported.
```    
    DEPS_IMPORTED = dependency_handler.check_all_loaded()
```
Another option is to track returns of initialisation functions:
```
    DEPS_IMPORTED = dependency_handler.init(['AnyModule'], module_globals=globals())
    DEPS_IMPORTED &= FROM(('PIL', 'Pillow')).IMPORT('ImageCms', 'Image')
    DEPS_IMPORTED &= IMPORT('Non-Existing-Module')
```
It is also possible to use dependency_handler.DEPENDENCIES_IMPORTED variable that is updated by install_all(), install_all_generator() and check_all_loaded() functions.
Modules loaded into global namespace are freely available but are not visible to code completion.
To make them accessible, import them once again like this:
```
    if dependency_handler.DEPENDENCIES_IMPORTED:
        import AnyModule
        from PIL import ImageCms, Image
```
Missing modules can be installed in a time of your choosing like this:
```
    DEPS_IMPORTED = dependency_handler.install_all()
    # or use a generator function
    for _ in dependency_handler.install_all_generator():
        do_something_between_lines()
```
install_all()/install_all_generator() function starts generating logs that will be presented in chosen front-ends.

#### Blender specific usage
Use blender_printer.install_operator_factory() to create an operator that will handle drawing logs in real time.
Blender will be responsive during modules installation and pip logs will be printed immediately in new window.
Use blender_printer.gui_operators_factory() and blender_printer.create_gui() to generate GUI.
```
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
```