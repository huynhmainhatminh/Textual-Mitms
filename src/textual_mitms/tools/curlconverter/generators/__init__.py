# curlconverter/generators/__init__.py
import importlib
import pkgutil
from pathlib import Path

GENERATORS = {}

def register_generator(name: str):
    """Decorator để đăng ký một hàm sinh mã vào hệ thống."""
    def decorator(func):
        GENERATORS[name] = func
        return func
    return decorator

def load_all_generators():
    package_dir = Path(__file__).resolve().parent
    for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
        if module_name != "utils":
            importlib.import_module(f".{module_name}", package=__package__)

load_all_generators()