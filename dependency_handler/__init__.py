'''
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
```
# Use factory to create modal operator that will handle drawing logs in real time.
# Blender will not be responsive during modules installation but pip logs will be printed immediately.
OT_ModalInstall = dependency_handler.blender_printer.install_operator_factory(bl_info['name'])

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
```
'''
import abc
from dataclasses import dataclass, field
import importlib
from pathlib import Path
import subprocess
import sys
import io
from typing import Generator

pybin = sys.executable
DEPENDENCIES_IMPORTED = False

class DepndencyHandlerException(Exception):
    def __init__(self, message="Module Fatal Exception"):
        self.message = message
        _log(f'{self.__class__.__name__}: {message}')
        super().__init__(self.message)
class ModuleFatalException(DepndencyHandlerException): pass
class SubModuleNotFound(DepndencyHandlerException): pass

pip_ensured = False

def _ensure_pip():
    global pip_ensured
    if pip_ensured:
        return
    
    try:
        importlib.import_module('pip')

        # update pip
        try:
            _log("----- Upgrading PIP -----")
            yield from _execute([pybin, "-m", "pip", "install", "--upgrade", "pip"])
            # [_ for _ in _execute([pybin, "-m", "pip", "install", "--upgrade", "pip"])]
        except subprocess.CalledProcessError as e:
            _log('Error: Pip module could not be upgraded. Using existing version.')
            _log(e.stderr)

        pip_ensured = True
    except ModuleNotFoundError:
        _log("\n----- Pip python package not found. Installing. -----")
        
        try:
            yield from _execute([pybin, "-m", "ensurepip"])
            yield from _execute([pybin, "-m", "pip", "install", "--upgrade", "pip"])
            # sys.path.append(site.getusersitepackages())
            # importlib.import_module('pip')
            pip_ensured = True
        except subprocess.CalledProcessError as e:
            raise ModuleFatalException(f"Pip Fatal Exception: {e}")
        # except ModuleNotFoundError:
        #     raise ModuleFatalException('Pip installation finished but import failed. Please restart Blender.')
        
        _log("Done.")

def _log(*msg: list):
    msg = " ".join(map(str, map(str, msg)))

    for printer in all_printers:
        printer.log(msg)

def _execute(args: list[str]) -> Generator[str, None, None]:
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True) as p:
        for line in p.stdout:
            _log('>>', line)
            yield line

    if p.returncode != 0:
        _log(f"Exit code: {p.returncode}")
        raise subprocess.CalledProcessError(p.returncode, p.args)

    # proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # for line in io.TextIOWrapper(proc.stdout, encoding="utf-8"):  # or another encoding
    #     _log('>>', line)
    # exit_code = proc.wait()
    # if exit_code:
    #     _log(f"Exit code: {exit_code}")
    #     raise subprocess.CalledProcessError(returncode=exit_code, cmd=" ".join(args))

@dataclass
class Dependency:
    '''A class representing a Dependency. For internal use mainly.'''
    name: str
    pip_name: str = None
    imported: bool = field(default=False, init=False)
    installed: bool = field(default=False, init=False)
    submodules: list[str] = field(default_factory=list, init=False)

    def __post_init__(self):
        all_dependencies[self.name] = self
        if not self.pip_name:
            self.pip_name = self.name
        # other_globals['test'] = 10

        try:
            module = importlib.import_module(self.name)
            self.imported = self.installed = True
            self._add_to_globals(module)
        except ModuleNotFoundError as e:
            pass
    
    def _add_to_globals(self, parent_module):
        if other_globals:
            other_globals[self.name] = parent_module
            for submodule in self.submodules:
                try:
                    other_globals[submodule] = importlib.import_module(f'{self.name}.{submodule}')
                except ModuleNotFoundError as e:
                    _log(f"Error: {submodule} of package {self.name} not found")
                    raise SubModuleNotFound(f"{submodule} of package {self.name} not found")

    def install_me(self):
        if self.imported:
            return True
        yield from _ensure_pip()
        _log("\n----- Installing ", self.pip_name, "-----")
        try:
            # subprocess.run([pybin, "-m", "pip", "install", "--upgrade", "--user", self.name], capture_output=True, text=True, check=True)
            yield from _execute([pybin, "-m", "pip", "install", "--upgrade", "--user", self.pip_name])
            self.installed = True
            try:
                module = importlib.import_module(self.name)
                self.imported = True
                self._add_to_globals(module)
                _log("Done.")
                return True
            except ModuleNotFoundError:
                estr = f'{self.pip_name} installation finished but {self.name} import failed. Try restarting Blender.'
                _log(estr)
                # raise ModuleFatalException(estr)
        except subprocess.CalledProcessError as e:
            _log(f'{self.pip_name} module installation failed.')
        
        return False
    
    def IMPORT(self, *submodules: list[str]) -> bool:
        self.submodules.extend(submodules)
        if self.imported:
            self._add_to_globals(other_globals[self.name])
            return True
        return False

other_globals = None
all_dependencies: dict[str, Dependency] = {}

def is_restart_needed() -> bool:
    '''Returns True if any of the installed dependencies can be fixed by restarting the program.'''
    return any(dep.installed and not dep.imported for dep in all_dependencies)

def get_failed_modules() -> list[Dependency]:
    '''Returns a list of dependencies whose installation failed.'''
    return [dep for dep in all_dependencies if not dep.installed]

def get_installed_version():
    pass

def FROM(module_name: str | tuple[str, str], /) -> Dependency:
    '''Takes a module that can be a string or a tuple of strings (package_name, pip_name). Returns a Dependency (not a module).'''
    match module_name:
        case (str(), str()):
            name, pip_name = module_name
        case str():
            name = pip_name = module_name
        case _:
            raise Exception("Wrong argument type")
    
    if name in all_dependencies:
        m = all_dependencies[name]
    else:
        m = Dependency(name, pip_name)
    return m

def IMPORT(module_name: str | tuple[str, str], /) -> Dependency:
    '''Takes a module that can be a string or a tuple of strings (package_name, pip_name). Returns True if module is successfully loaded.'''
    return FROM(module_name).imported


class PrinterInterface(metaclass=abc.ABCMeta):
    '''An abstract class representing the printer front-end interface.'''
    all_printers = []

    @abc.abstractmethod
    def log(self, *msg: list) -> None:
        """Prints message."""
        raise NotImplementedError
    
    @abc.abstractmethod
    def prepare(self) -> None:
        """Clears buffer. Prepares to receive data."""
        raise NotImplementedError
    
    @abc.abstractmethod
    def finish(self) -> None:
        """Finish"""
        raise NotImplementedError
    
    def catch_exceptions(use_fallback_log=True):
        '''
        Decorator. Catches printer exceptions and prints them using other printers.
        Use it when implementing concrete methods.
        '''
        def wrap(f):
            def wrapper(*args):
                try:
                    f(*args)
                except Exception as e:
                    if use_fallback_log:
                        for p in all_printers:
                            if f.__qualname__.split('.')[0] != p.__class__.__qualname__:
                                p.log(f"Printer {f.__qualname__} error: {e}")
            return wrapper
        return wrap

class ConsolePrinter(PrinterInterface):
    
    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def log(self, *msg: list):
        msg = " ".join(map(str, map(str, msg)))
        print(msg)
    
    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def prepare(self):
        # Do nothing
        return

    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def finish(self):
        # Do nothing
        return

class FilePrinter(PrinterInterface):
    def __init__(self, filepath: str=None):
        if not filepath:
            self.filepath = Path(__file__).parent / 'dependency_pip_report.txt'
        else:
            self.filepath = filepath

    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def log(self, *msg: list):
        msg = '\n' + " ".join(map(str, map(str, msg))).rstrip()
        with open(self.filepath, 'a') as f:
            f.write(msg)
    
    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def prepare(self):
        with open(self.filepath, 'w'):
            pass

    @PrinterInterface.catch_exceptions(use_fallback_log=True)
    def finish(self):
        # Do nothing
        return

all_printers: list[PrinterInterface] = []

def init(dependencies: list[str | tuple[str, str]]=None, /, *, module_globals: dict=None, printers: list[PrinterInterface]=None, use_console: bool=True) -> bool:
    '''
    Takes in a list of dependencies and a module globals() dict. A dependency can be a string or a tuple of strings (package name, pip name).
    Returns True if all dependencies are installed.

    :param dependencies: List of dependencies to initialise. Use tuple (module_name, pip_name) for modules that need different names for pip installing and importing. Used to import modules into.
    :type dependencies: list[str | tuple[str, str]]
    :param module_globals: Reference to global namespace dict.
    :type module_globals: dict
    :param printers: list of used output front-ends.
    :type printers: list[PrinterInterface]
    :param use_console: Create console front-end if True.
    :type use_console: bool
    '''
    if printers:
        if any(not isinstance(p, PrinterInterface) for p in printers):
            raise TypeError("Printer does not implement PrinterInterface.")
        all_printers.extend(printers)
    
    if use_console:
        all_printers.append(ConsolePrinter())

    global other_globals
    other_globals = module_globals
    if not dependencies:
        dependencies = []
    if not all({Dependency(*name if isinstance(name, tuple) else (name,)).imported for name in dependencies}):
        return False
    return True
    
def install_all():
    '''
    Installs all initialized dependencies. Returns True if all dependencies are installed and loaded.
    May throw SubModuleNotFound exception and ModuleFatalException when PIP cannot be installed.
    '''
    for _ in install_all_generator(): pass
    return check_all_loaded()

def install_all_generator():
    '''
    Generator function. Installs all initialized dependencies.
    May throw SubModuleNotFound exception and ModuleFatalException when PIP cannot be installed.
    Use it when you need to print output in real time.

    This function does not return successful loading of modules, so use check_all_loaded() instead.
    '''

    for printer in all_printers:
        printer.prepare()
    
    try:
        for dependency in all_dependencies.values():
            yield from dependency.install_me()
        
        if check_all_loaded():
            _log("\n\n---------- Installation Successful ----------")
            return True
    except SubModuleNotFound as e:
        raise
    except ModuleFatalException as e:
        raise
    except Exception as e:
        _log(e)
        raise
    finally:
        _log('\n\n ------ System Info ------\n')
        try:
            # try to get Blender info if the module is run in its environment
            import bpy
            _log('\nBlender info:')
            _log(f' bpy.app.version: {bpy.app.version}')
            _log(f' Addon Name: {other_globals["bl_info"]["name"]}')
            _log(f' Addon Version: {other_globals["bl_info"]["version"]}')
            _log(f' bpy.app.binary_path: {bpy.app.binary_path}')
            _log('\n')
        except:
            pass

        import platform
        _log(f' sys.executable: {sys.executable}')
        _log('\nImported modules:')
        for dep in all_dependencies.values():
            if dep.imported:
                _log(f' {dep.name}: {importlib.import_module(dep.name)}')
        _log(f'\n platform.machine: {platform.machine()}')
        _log(f' platform.platform: {platform.platform()}')
        _log(f' platform.platform: {platform.platform()}')
        _log(f' platform.processor: {platform.processor()}')

        _log("\n\n---------- Installation Failed ----------")
    
    return False

def check_all_loaded() -> bool:
    '''Returns True if all initialized dependencies were successfully loaded and False otherwise.'''
    global DEPENDENCIES_IMPORTED
    DEPENDENCIES_IMPORTED = all(dep.imported for dep in all_dependencies.values())
    return DEPENDENCIES_IMPORTED

if __name__ == "__main__":
    # deps_installed = init([('PIL', 'Pillow'), 'pyexiv2'], globals=globals())
    # _log('checked and installed:', deps_installed)
    # _log('all deps installed:', install_all())
    # _log('is restart needed:', is_restart_needed())
    
    deps_installed = init(['pyexiv2'], module_globals=globals(), printers=[FilePrinter(),])
    FROM(('PIL', 'Pillow')).IMPORT('Image', 'ImageCms')
    IMPORT('Non-Existing-Module')
    # print('check all:', check_all_loaded())
    print('install_all generator:', [_ for _ in install_all_generator()])
    # print('### install_all:', install_all())
    # print(ImageCms)