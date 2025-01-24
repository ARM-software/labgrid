import attr
import argparse
import logging
import sys
import os
import signal
import traceback

from .client import ServerError, InteractiveCommandError, Error
from ..util.helper import processwrapper
from ..logging import StepLogger
from .client import basicConfig, ClientSession, common_args
from .. import Environment
from ..util.proxy import proxymanager
from ..exceptions import NoDriverFoundError, NoResourceFoundError, InvalidConfigError


@attr.s(eq=False)
class LocalClientSession(ClientSession):

    def _get_target(self):
        return self.env.get_target("main")


def main():
    basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
    )

    StepLogger.start()
    processwrapper.enable_logging()

    state = os.environ.get("STATE", None)
    state = os.environ.get("LG_STATE", state)
    initial_state = os.environ.get("LG_INITIAL_STATE", None)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        dest="command",
        title="available subcommands",
        metavar="COMMAND",
    )

    common_args(parser, subparsers, state, initial_state)

    # make any leftover arguments available for some commands
    args, leftover = parser.parse_known_args()
    if args.command not in ["ssh", "rsync", "forward"]:
        args = parser.parse_args()
    else:
        args.leftover = leftover

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    if args.verbose > 1:
        logging.getLogger().setLevel(logging.CONSOLE)
    if args.debug or args.verbose > 2:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.config and (args.state or args.initial_state):
        print("Setting the state requires a configuration file", file=sys.stderr)
        exit(1)
    if args.initial_state and not args.state:
        print("Setting the initial state requires a desired state", file=sys.stderr)
        exit(1)

    if args.proxy:
        proxymanager.force_proxy(args.proxy)

    env = None
    if args.config:
        env = Environment(config_file=args.config)

    if args.command and args.command != "help":
        exitcode = 0
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        session = LocalClientSession(env=env, args=args, prog=parser.prog)
        try:
            args.func(session)
        except (NoResourceFoundError, NoDriverFoundError, InvalidConfigError) as e:
            if args.debug:
                traceback.print_exc(file=sys.stderr)
            else:
                print(f"{parser.prog}: error: {e}", file=sys.stderr)

            if isinstance(e, NoResourceFoundError):
                if e.found:
                    print("Found multiple resources but no name was given, available names:", file=sys.stderr)
                    for res in e.found:
                        print(f"{res.name}", file=sys.stderr)
                else:
                    print(
                        "This may be caused by disconnected exporter or wrong match entries.\nYou can use the 'show' command to review all matching resources.",
                        file=sys.stderr,
                    )  # pylint: disable=line-too-long
            elif isinstance(e, NoDriverFoundError):
                print(
                    "This is likely caused by an error or missing driver in the environment configuration.",
                    file=sys.stderr,
                )  # pylint: disable=line-too-long
            elif isinstance(e, InvalidConfigError):
                print(
                    "This is likely caused by an error in the environment configuration or invalid\nresource information provided by the coordinator.",
                    file=sys.stderr,
                )  # pylint: disable=line-too-long

            exitcode = 1
        except ServerError as e:
            print(f"Server error: {e}", file=sys.stderr)
            exitcode = 1
        except InteractiveCommandError as e:
            if args.debug:
                traceback.print_exc(file=sys.stderr)
            exitcode = e.exitcode
        except Error as e:
            if args.debug:
                traceback.print_exc(file=sys.stderr)
            else:
                print(f"{parser.prog}: error: {e}", file=sys.stderr)
            exitcode = 1
        except KeyboardInterrupt:
            exitcode = 1
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc(file=sys.stderr)
            exitcode = 2
        exit(exitcode)
    else:
        parser.print_help(file=sys.stderr)