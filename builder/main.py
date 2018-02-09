# Copyright 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
    Builder for MCS-51 series of microcontrollers
"""

from os.path import join
from time import sleep

from SCons.Script import (ARGUMENTS, COMMAND_LINE_TARGETS, AlwaysBuild,
                          Builder, Default, DefaultEnvironment)

from platformio.util import get_serialports


def BeforeUpload(target, source, env):  # pylint: disable=W0613,W0621

    if "program" in COMMAND_LINE_TARGETS:
        return

    upload_options = {}
    if "BOARD" in env:
        upload_options = env.BoardConfig().get("upload", {})

    # Deprecated: compatibility with old projects. Use `program` instead
    if "usb" in env.subst("$UPLOAD_PROTOCOL"):
        upload_options['require_upload_port'] = False
        env.Replace(UPLOAD_SPEED=None)

    if env.subst("$UPLOAD_SPEED"):
        env.Append(UPLOADERFLAGS=["-b", "$UPLOAD_SPEED"])

    if upload_options and not upload_options.get("require_upload_port", False):
        return

    env.AutodetectUploadPort()
    env.Append(UPLOADERFLAGS=["-P", '"$UPLOAD_PORT"'])

    if not upload_options.get("disable_flushing", False):
        env.FlushSerialBuffer("$UPLOAD_PORT")

    before_ports = get_serialports()


def __getSize(size_type, env):
    # FIXME: i don't really know how to do this right. see:
    #        https://community.platformio.org/t/missing-integers-in-board-extra-flags-in-board-json/821
    return str(env.BoardConfig().get("build", {
        # defaults
        "size_heap": 1024,
        "size_iram": 256,
        "size_xram": 65536,
        "size_code": 65536,
    })[size_type])


env = DefaultEnvironment()

env.Replace(
    AR="sdar",
    AS="sdas8051",
    CC="sdcc",
    LD="sdld",
    RANLIB="sdranlib",
    OBJCOPY="sdobjcopy",
    OBJSUFFIX=".rel",
    LIBSUFFIX=".lib",

    CFLAGS=[
        "--std-sdcc11"
    ],

    CCFLAGS=[
        "--opt-code-size",  # optimize for size
        "--peep-return",    # peephole optimization for return instructions
        "-m$BOARD_MCU"
    ],

    CPPDEFINES=[
        "F_CPU=$BOARD_F_CPU",
        "HEAP_SIZE=" + __getSize("size_heap", env)
    ],

    LINKFLAGS=[
        "-m$BOARD_MCU",
        "--iram-size", __getSize("size_iram", env),
        "--xram-size", __getSize("size_xram", env),
        "--code-size", __getSize("size_code", env),
        "$BUILD_FLAGS",
        "--out-fmt-ihx",
    ],

    # LIBS=["m"],

    # SIZEPRINTCMD='$SIZETOOL --mcu=$BOARD_MCU -C -d $SOURCES',

    PROGNAME="firmware",
    PROGSUFFIX=".ihx"
)

env.Append(
    ASFLAGS=env.get("CCFLAGS", [])[:],

    BUILDERS=dict(
        ElfToEep=Builder(
            action=env.VerboseAction(" ".join([
                "$OBJCOPY",
                "-O",
                "ihex",
                "-j",
                ".eeprom",
                '--set-section-flags=.eeprom="alloc,load"',
                "--no-change-warnings",
                "--change-section-lma",
                ".eeprom=0",
                "$SOURCES",
                "$TARGET"
            ]), "Building $TARGET"),
            suffix=".eep"
        ),

        ElfToHex=Builder(
            action=env.VerboseAction(" ".join([
                "$OBJCOPY",
                "-O",
                "ihex",
                "-R",
                ".eeprom",
                "$SOURCES",
                "$TARGET"
            ]), "Building $TARGET"),
            suffix=".hex"
        )
    )
)

if int(ARGUMENTS.get("PIOVERBOSE", 0)):
    env.Prepend(UPLOADERFLAGS=["-v"])

#
# Target: Build executable and linkable firmware
#

target_firm = env.BuildProgram()

#
# Target: Upload by default .hex file
#

# options for stcgal uploader tool
# https://github.com/grigorig/stcgal

if env.subst("$UPLOAD_PROTOCOL") == "stcgal":
    if "BOARD" in env and env.BoardConfig().get("vendor") == "STC":
        f_cpu_khz = int(env.BoardConfig().get("build.f_cpu")) / 1000
        env.Replace(
                UPLOAD_OPTIONS = [
                    "-p", "$UPLOAD_PORT",
                    "-t", int(f_cpu_khz),
                    "-a"
                ],
                STCGALCMD="stcgal",
                UPLOADHEXCMD = "$STCGALCMD $UPLOAD_OPTIONS $UPLOAD_FLAGS $SOURCE"
        )

upload = env.Alias(
    ["upload"], target_firm,
    [env.VerboseAction(BeforeUpload, "Looking for upload port..."),
     env.VerboseAction("$UPLOADHEXCMD", "Uploading $SOURCE")])
AlwaysBuild(upload)

#
# Target: Upload firmware using external programmer
#

program = env.Alias(
    "program", target_firm,
    [env.VerboseAction(BeforeUpload, "Looking for upload port..."),
     env.VerboseAction("$PROGRAMHEXCMD", "Programming $SOURCE")])

AlwaysBuild(program)

#
# Setup default targets
#

Default([target_firm])
