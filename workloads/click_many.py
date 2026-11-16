"""Parse 2000 positional arguments (click <8.2, src layout)."""
import click

NAME = "click-many"
WARMUP = 2
ARGV = [f"item-{i}" for i in range(2000)]


def setup():
    @click.command()
    @click.argument("items", nargs=-1)
    def cmd(items):
        pass

    def once():
        cmd.make_context("prog", list(ARGV), parent=click.Context(cmd))
    return once
