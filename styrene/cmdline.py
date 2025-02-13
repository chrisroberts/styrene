# Copyright © 2017 Andrew Chadwick.
#
# This file is part of ’Styrene.
#
# ’Styrene is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# ’Styrene is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ’Styrene.  If not, see <http://www.gnu.org/licenses/>.


"""Launching from the command line."""

from .bundle import NativeBundle
from .utils import fix_tree_perms

import optparse
import configparser
import sys
import os.path
import os
import tempfile
import shutil
from textwrap import dedent
import re
import logging

logger = logging.getLogger(__name__)


class ColorFormatter (logging.Formatter):
    """Minimal ANSI formatter, for use with non-Windows console logging."""

    # ANSI control sequences for various things:

    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
    FG = 30
    BG = 40
    LEVELCOL = {
        "DEBUG": "\033[%02dm" % (FG+CYAN,),
        "INFO": "\033[%02dm" % (FG+GREEN,),
        "WARNING": "\033[%02dm" % (FG+MAGENTA,),
        "ERROR": "\033[%02dm" % (FG+RED,),
        "CRITICAL": "\033[%02d;%02dm" % (FG+RED, BG+BLACK),
    }
    BOLD = "\033[01m"
    BOLDOFF = "\033[22m"
    ITALIC = "\033[03m"
    ITALICOFF = "\033[23m"
    UNDERLINE = "\033[04m"
    UNDERLINEOFF = "\033[24m"
    RESET = "\033[0m"

    # Token formatting:

    @classmethod
    def replace_bold(cls, m):
        return cls.BOLD + m.group(0) + cls.BOLDOFF

    @classmethod
    def replace_italic(cls, m):
        return cls.ITALIC + m.group(0) + cls.ITALICOFF

    @classmethod
    def replace_underline(cls, m):
        return cls.UNDERLINE + m.group(0) + cls.UNDERLINEOFF

    # Formatter methods:

    def format(self, record):
        record = logging.makeLogRecord(record.__dict__)
        msg = record.msg
        replace = self.replace_bold
        token_formatting = [
            (re.compile(r'%r'), replace),
            (re.compile(r'%s'), replace),
            (re.compile(r'%\+?[0-9.]*d'), replace),
            (re.compile(r'%\+?[0-9.]*f'), replace),
        ]
        for token_re, repl in token_formatting:
            msg = token_re.sub(repl, msg)
        record.msg = msg
        record.reset = self.RESET
        record.bold = self.BOLD
        record.boldOff = self.BOLDOFF
        record.italic = self.ITALIC
        record.italicOff = self.ITALICOFF
        record.underline = self.UNDERLINE
        record.underlineOff = self.UNDERLINEOFF
        record.levelCol = ""
        if record.levelname in self.LEVELCOL:
            record.levelCol = self.LEVELCOL[record.levelname]
        return super(ColorFormatter, self).format(record)


# Top-level commands:

def process_spec_file(spec, options):
    """Prepare the bundle as specified in the spec."""
    bundle = NativeBundle(spec)
    bundle.check_runtime_dependencies()
    output_dir = options.output_dir
    if not output_dir:
        if not (options.build_zip or options.build_exe):
            logger.warning(
                "Both --no-zip and --no-exe were specified, with no "
                "--output-dir to write and keep the remaining "
                "intermediate files in."
            )
            logger.warning(
                "This means that the bundle tree would be "
                "deleted as soon as it was created, "
                "so I'm doing nothing."
            )
            return
        output_dir = os.getcwd()
        tmp_dir = tempfile.mkdtemp(prefix="styrene")
        try:
            written = bundle.write_distributables(tmp_dir, options)
            for distfile in written:
                distfile_final = os.path.join(
                    output_dir,
                    os.path.basename(distfile),
                )
                shutil.copy(distfile, distfile_final)
        finally:
            logger.info("Cleaning up “%s”", tmp_dir)
            fix_tree_perms(tmp_dir)
            shutil.rmtree(tmp_dir)
    else:
        bundle.write_distributables(output_dir, options)


# Startup:

def main():

    # Parse command line args
    parser = optparse.OptionParser(
        usage="%prog [options] spec1.cfg ...",
        description=dedent("""
            Creates distributable installers and portable zipfiles
            by bundling together MSYS2 packages.
        """).strip(),
        epilog=dedent("""
            Normally a temp directory is used for building,
            and the output distributables are then copied
            into the current directory.
            The temp dir is normally deleted after processing.

            Specifying --output-dir changes this behaviour:
            no temp directory will be made.
            The output dir will be created if it doesn't exist,
            and all output will be retained there, not copied out.
            The temporary bundle tree is kept too,
            for inspection and testing.

            More: http://styrene.readthedocs.io/
        """).strip(),
    )
    parser.add_option(
        "-q", "--quiet",
        help="log errors and warnings only",
        action="store_true",
        default=False,
    )
    parser.add_option(
        "--debug",
        help="debug mode (noisy operation, pause after postinst)",
        action="store_true",
        default=False,
    )
    parser.add_option(
        "-o", "--output-dir",
        help="where to store output, created if needed",
        metavar="DIR",
        default=None,
    )
    parser.add_option(
        "-p", "--pkg-dir",
        metavar="DIR",
        help="preferentially use package files from DIR",
        action="append",
        dest="pkgdirs",
        default=[],
    )
    parser.add_option(
        "--no-exe",
        help="do not build the installer .exe output",
        action="store_false",
        dest="build_exe",
        default=True,
    )
    parser.add_option(
        "--no-zip",
        help="do not create the standalone .zip output",
        action="store_false",
        dest="build_zip",
        default=True,
    )
    parser.add_option(
        "--colour", "--color",
        help="colourize output: yes/no/auto",
        metavar="COLSPEC",
        default="auto",
    )
    options, args = parser.parse_args(sys.argv[1:])
    if not len(args):
        parser.print_help()
        sys.exit(1)

    # Initialize logging
    colourize = {
        "yes".casefold(): True,
        "no".casefold(): False,
    }.get(options.colour.casefold(), sys.stderr.isatty())
    if colourize:
        log_format = (
            "%(levelCol)s%(levelname)s: "
            "%(bold)s%(name)s%(boldOff)s: "
            "%(message)s%(reset)s"
        )
        console_formatter = ColorFormatter(log_format)
    else:
        log_format = "%(levelname)s: %(name)s: %(message)s"
        console_formatter = logging.Formatter(log_format)
    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setFormatter(console_formatter)
    root_logger = logging.getLogger(None)
    root_logger.addHandler(console_handler)
    if options.quiet:
        loglevel = logging.WARNING
    elif options.debug:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO
    root_logger.setLevel(loglevel)

    # Process bundles
    for spec_file in args:
        try:
            spec = configparser.ConfigParser()
            spec.read(spec_file, encoding="utf-8")
        except Exception:
            logger.exception(
                "Failed to load bundle spec file “%s”",
                spec_file,
            )
            sys.exit(2)
        try:
            process_spec_file(spec, options)
        except Exception:
            logger.exception(
                "Unexpected error while processing “%s”",
                spec_file,
            )
            sys.exit(2)
