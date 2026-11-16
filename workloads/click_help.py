"""Render --help for a group of 8 commands x 10 options (click <8.2)."""
import click

NAME = "click-help"
WARMUP = 5


def setup():
    group = click.Group()
    for i in range(8):
        cmd = click.Command(f"cmd{i}", help="x" * 40)
        for j in range(10):
            cmd.params.append(click.Option([f"--opt{j}"], help="y" * 30))
        group.add_command(cmd)
    ctx = click.Context(group)
    return lambda: group.get_help(ctx)
