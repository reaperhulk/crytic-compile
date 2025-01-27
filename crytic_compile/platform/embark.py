"""
Embark platform. https://github.com/embark-framework/embark
"""

import json
import logging
import os
import subprocess
from pathlib import Path

from typing import TYPE_CHECKING

from crytic_compile.utils.naming import extract_filename, extract_name, convert_filename
from crytic_compile.compiler.compiler import CompilerVersion
from crytic_compile.platform.types import Type
from crytic_compile.platform.exceptions import InvalidCompilation

# Cycle dependency
if TYPE_CHECKING:
    from crytic_compile import CryticCompile

LOGGER = logging.getLogger("CryticCompile")


def compile(crytic_compile: "CryticCompile", target: str, **kwargs: str):
    """
    Compile the target
    :param crytic_compile:
    :param target:
    :param kwargs:
    :return:
    """
    embark_ignore_compile = kwargs.get("embark_ignore_compile", False)
    embark_overwrite_config = kwargs.get("embark_overwrite_config", False)
    crytic_compile.type = Type.EMBARK
    plugin_name = "@trailofbits/embark-contract-info"
    with open(os.path.join(target, "embark.json"), encoding="utf8") as file_desc:
        embark_json = json.load(file_desc)
    if embark_overwrite_config:
        write_embark_json = False
        if not "plugins" in embark_json:
            embark_json["plugins"] = {plugin_name: {"flags": ""}}
            write_embark_json = True
        elif not plugin_name in embark_json["plugins"]:
            embark_json["plugins"][plugin_name] = {"flags": ""}
            write_embark_json = True
        if write_embark_json:
            process = subprocess.Popen(["npm", "install", plugin_name], cwd=target)
            _, stderr = process.communicate()
            with open(os.path.join(target, "embark.json"), "w", encoding="utf8") as outfile:
                json.dump(embark_json, outfile, indent=2)
    else:
        if (not "plugins" in embark_json) or (not plugin_name in embark_json["plugins"]):
            raise InvalidCompilation(
                "embark-contract-info plugin was found in embark.json. "
                "Please install the plugin (see "
                "https://github.com/crytic/crytic-compile/wiki/Usage#embark)"
                ", or use --embark-overwrite-config."
            )

    if not embark_ignore_compile:
        process = subprocess.Popen(
            ["embark", "build", "--contracts"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=target,
        )
        stdout, stderr = process.communicate()
        LOGGER.info("%s\n", stdout.decode())
        if stderr:
            # Embark might return information to stderr, but compile without issue
            LOGGER.error("%s", stderr.decode())
    infile = os.path.join(target, "crytic-export", "contracts-embark.json")
    if not os.path.isfile(infile):
        raise InvalidCompilation(
            "Embark did not generate the AST file. Is Embark installed "
            "(npm install -g embark)? Is embark-contract-info installed? (npm install -g embark)."
        )

    crytic_compile.compiler_version = _get_version(target)

    with open(infile, "r", encoding="utf8") as file_desc:
        targets_loaded = json.load(file_desc)
        for k, ast in targets_loaded["asts"].items():
            filename = convert_filename(k, _relative_to_short, crytic_compile, working_dir=target)
            crytic_compile.asts[filename.absolute] = ast
            crytic_compile.filenames.add(filename)

        if not "contracts" in targets_loaded:
            LOGGER.error("Incorrect json file generated. Are you using %s >= 1.1.0?", plugin_name)
            raise InvalidCompilation(
                f"Incorrect json file generated. Are you using {plugin_name} >= 1.1.0?"
            )

        for original_contract_name, info in targets_loaded["contracts"].items():
            contract_name = extract_name(original_contract_name)
            contract_filename = extract_filename(original_contract_name)
            contract_filename = convert_filename(
                contract_filename, _relative_to_short, crytic_compile, working_dir=target
            )

            crytic_compile.contracts_filenames[contract_name] = contract_filename
            crytic_compile.contracts_names.add(contract_name)

            if "abi" in info:
                crytic_compile.abis[contract_name] = info["abi"]
            if "bin" in info:
                crytic_compile.bytecodes_init[contract_name] = info["bin"].replace("0x", "")
            if "bin-runtime" in info:
                crytic_compile.bytecodes_runtime[contract_name] = info["bin-runtime"].replace(
                    "0x", ""
                )
            if "srcmap" in info:
                crytic_compile.srcmaps_init[contract_name] = info["srcmap"].split(";")
            if "srcmap-runtime" in info:
                crytic_compile.srcmaps_runtime[contract_name] = info["srcmap-runtime"].split(";")


def is_embark(target: str) -> bool:
    """
    Check if the target is an embark project
    :param target:
    :return:
    """
    return os.path.isfile(os.path.join(target, "embark.json"))


def is_dependency(path: str) -> bool:
    """
    Check if the path is a dependency
    :param path:
    :return:
    """
    return "node_modules" in Path(path).parts


def _get_version(target: str) -> CompilerVersion:
    """
    Get the compiler version
    :param target:
    :return:
    """
    with open(os.path.join(target, "embark.json"), encoding="utf8") as file_desc:
        config = json.load(file_desc)
        version = "0.5.0"  # default version with Embark 0.4
        if "versions" in config:
            if "solc" in config["versions"]:
                version = config["versions"]["solc"]
        optimized = False
        if "options" in config:
            if "solc" in config["options"]:
                if "optimize" in config["options"]["solc"]:
                    optimized = config["options"]["solc"]

    return CompilerVersion(compiler="solc-js", version=version, optimized=optimized)


def _relative_to_short(relative: Path) -> Path:
    """
    Convert relative to short
    :param relative:
    :return:
    """
    short = relative
    try:
        short = short.relative_to(Path(".embark", "contracts"))
    except ValueError:
        try:
            short = short.relative_to("node_modules")
        except ValueError:
            pass
    return short
