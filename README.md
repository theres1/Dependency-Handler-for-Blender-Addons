# Dependency-Handler-for-Blender-Addons
## Automatic module installation via pip, handling exceptions, configurable output printing in Blender addons.

Module that allows easy handling of dependencies, created mainly for Blender add-ons.

Usage Examples:

Import output printing front-ends:
    ```
    from . dependency_handler.blender_printer import BlenderPrinter
    from . dependency_handler import FilePrinter
    ```

BlenderPrinter - creates a new Blender window with Text Editor and writes logs into text file
FilePrinter - writes logs into text file. By default, text file is created next in Path(__file__).parent path.

    ```
    from . import dependency_handler
    from . dependency_handler import FROM, IMPORT
    ```

Initialise dependencies. Already installed modules will be imported during initialisation.

    ```
    dependency_handler.init([('PIL', 'Pillow'), 'pyexiv2'], module_globals=globals(), printers=[BlenderPrinter("Dependency Log of My Addon"), FilePrinter()])
    FROM('PIL').IMPORT('ImageCms', 'Image') # or FROM(('PIL', 'Pillow')).IMPORT('ImageCms', 'Image')
    IMPORT('Non-Existing-Module')
    ```

Dependencies can be initialised by init, FROM and IMPORT functions. Use tuple (module_name, pip_name) for modules that need different names for pip installing and importing.
Pass globals() as a module_globals parameter to import modules into global namespace.
State of all dependencies can be tracked by dependency_handler.check_all_loaded() function returning True if all dependencies are imported.
    
    ```
    DEPS_IMPORTED = dependency_handler.check_all_loaded()
    ```

Another option is track initialisation functions returns:

    ```
    DEPS_IMPORTED = dependency_handler.init(['pyexiv2'], module_globals=globals())
    DEPS_IMPORTED &= FROM(('PIL', 'Pillow')).IMPORT('ImageCms', 'Image')
    DEPS_IMPORTED &= IMPORT('Non-Existing-Module')
    ```

Modules loaded into global namespace are freely available but are not visible for code completion.
To make them accessible, import them once again like this:

    ```
    if DEPS_IMPORTED:
        import pyexiv2
        from PIL import ImageCms, Image
    ```

Missing modules can be installed in a time of your choosing like this:
    
    ```
    global DEPS_IMPORTED
    DEPS_IMPORTED = dependency_handler.install_all()
    ```

dependency_handler.install_all() function starts generating logs that will be presented in chosen front-ends.