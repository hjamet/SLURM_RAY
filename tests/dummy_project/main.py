
import utils.helper
from core import logic
import importlib
import os

def main():
    utils.helper.do_stuff()
    logic.run()
    
    # Dynamic import warning expected
    mod = importlib.import_module("plugins." + "plugin_a")
    
    # Open warning expected
    with open("data/config.json", "r") as f:
        pass
