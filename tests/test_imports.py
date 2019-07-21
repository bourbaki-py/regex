# coding:utf-8
import os
from itertools import chain
from pathlib import Path
from setuptools import find_packages
import pytest

module = type(os)

top_dir = Path(__file__).parent.parent


def all_module_paths(rootdir):
    parents = find_packages(rootdir)
    return list(chain(parents, chain.from_iterable(map(submodule_paths, parents))))


def submodule_paths(parent_module_path: str):
    paths = Path(parent_module_path.replace(".", os.path.sep)).glob("*.py")
    return (parent_module_path + "." + os.path.splitext(p.name)[0].replace(os.path.sep, ".")
            for p in paths if not p.name.startswith("_"))


@pytest.mark.parametrize("module_name", all_module_paths(top_dir))
def test_submodule_import(module_name):
    mod = __import__(module_name)
    assert isinstance(mod, module)
