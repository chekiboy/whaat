from importlib.metadata import version

__version__ = version("whaat")


def main() -> None:
    from whaat.cli.main import app

    app()
