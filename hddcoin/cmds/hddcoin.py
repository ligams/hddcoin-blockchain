from __future__ import annotations

from io import TextIOWrapper
from typing import Optional

import click

from hddcoin import __version__
from hddcoin.cmds.beta import beta_cmd
from hddcoin.cmds.completion import completion
from hddcoin.cmds.configure import configure_cmd
from hddcoin.cmds.dao import dao_cmd
from hddcoin.cmds.data import data_cmd
from hddcoin.cmds.db import db_cmd
from hddcoin.cmds.dev import dev_cmd
from hddcoin.cmds.farm import farm_cmd
from hddcoin.cmds.init import init_cmd
from hddcoin.cmds.keys import keys_cmd
from hddcoin.cmds.netspace import netspace_cmd
from hddcoin.cmds.passphrase import passphrase_cmd
from hddcoin.cmds.peer import peer_cmd
from hddcoin.cmds.plotnft import plotnft_cmd
from hddcoin.cmds.plots import plots_cmd
from hddcoin.cmds.plotters import plotters_cmd
from hddcoin.cmds.rpc import rpc_cmd
from hddcoin.cmds.show import show_cmd
from hddcoin.cmds.start import start_cmd
from hddcoin.cmds.stop import stop_cmd
from hddcoin.cmds.wallet import wallet_cmd
from hddcoin.util.default_root import DEFAULT_KEYS_ROOT_PATH, DEFAULT_ROOT_PATH
from hddcoin.util.errors import KeychainCurrentPassphraseIsInvalid
from hddcoin.util.keychain import Keychain, set_keys_root_path
from hddcoin.util.ssl_check import check_ssl

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.group(
    help=f"\n  Manage hddcoin blockchain infrastructure ({__version__})\n",
    epilog="Try 'hddcoin start node', 'hddcoin netspace -d 192', or 'hddcoin show -s'",
    context_settings=CONTEXT_SETTINGS,
)
@click.option("--root-path", default=DEFAULT_ROOT_PATH, help="Config file root", type=click.Path(), show_default=True)
@click.option(
    "--keys-root-path", default=DEFAULT_KEYS_ROOT_PATH, help="Keyring file root", type=click.Path(), show_default=True
)
@click.option("--passphrase-file", type=click.File("r"), help="File or descriptor to read the keyring passphrase from")
@click.pass_context
def cli(
    ctx: click.Context,
    root_path: str,
    keys_root_path: Optional[str] = None,
    passphrase_file: Optional[TextIOWrapper] = None,
) -> None:
    from pathlib import Path

    ctx.ensure_object(dict)
    ctx.obj["root_path"] = Path(root_path)

    # keys_root_path and passphrase_file will be None if the passphrase options have been
    # scrubbed from the CLI options
    if keys_root_path is not None:
        set_keys_root_path(Path(keys_root_path))

    if passphrase_file is not None:
        import sys

        from hddcoin.cmds.passphrase_funcs import cache_passphrase, read_passphrase_from_file

        try:
            passphrase = read_passphrase_from_file(passphrase_file)
            if Keychain.master_passphrase_is_valid(passphrase):
                cache_passphrase(passphrase)
            else:
                raise KeychainCurrentPassphraseIsInvalid()
        except KeychainCurrentPassphraseIsInvalid:
            if Path(passphrase_file.name).is_file():
                print(f'Invalid passphrase found in "{passphrase_file.name}"')
            else:
                print("Invalid passphrase")
            sys.exit(1)
        except Exception as e:
            print(f"Failed to read passphrase: {e}")

    check_ssl(Path(root_path))


@cli.command("version", help="Show hddcoin version")
def version_cmd() -> None:
    print(__version__)


@cli.command("run_daemon", help="Runs hddcoin daemon")
@click.option(
    "--wait-for-unlock",
    help="If the keyring is passphrase-protected, the daemon will wait for an unlock command before accessing keys",
    default=False,
    is_flag=True,
    hidden=True,  # --wait-for-unlock is only set when launched by hddcoin start <service>
)
@click.pass_context
def run_daemon_cmd(ctx: click.Context, wait_for_unlock: bool) -> None:
    import asyncio

    from hddcoin.daemon.server import async_run_daemon
    from hddcoin.util.keychain import Keychain

    wait_for_unlock = wait_for_unlock and Keychain.is_keyring_locked()

    asyncio.run(async_run_daemon(ctx.obj["root_path"], wait_for_unlock=wait_for_unlock))


cli.add_command(keys_cmd)
cli.add_command(plots_cmd)
cli.add_command(wallet_cmd)
cli.add_command(plotnft_cmd)
cli.add_command(configure_cmd)
cli.add_command(init_cmd)
cli.add_command(rpc_cmd)
cli.add_command(show_cmd)
cli.add_command(start_cmd)
cli.add_command(stop_cmd)
cli.add_command(netspace_cmd)
cli.add_command(farm_cmd)
cli.add_command(plotters_cmd)
cli.add_command(db_cmd)
cli.add_command(peer_cmd)
cli.add_command(data_cmd)
cli.add_command(passphrase_cmd)
cli.add_command(beta_cmd)
cli.add_command(completion)
cli.add_command(dao_cmd)
cli.add_command(dev_cmd)


def main() -> None:
    cli()  # pylint: disable=no-value-for-parameter


if __name__ == "__main__":
    main()
