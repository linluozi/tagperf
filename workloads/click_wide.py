"""Parse a 10-option command with 4 positionals (click <8.2, src layout)."""
import click

NAME = "click-wide"
WARMUP = 3
ARGV = ["--alpha", "v", "--beta", "9", "--gamma", "--delta", "d1", "--delta", "d2",
        "--epsilon", "b", "--zeta", "/tmp/z", "--eta", "2.25", "--theta", "t",
        "--iota", "--kappa", "11", "f1", "f2", "f3", "f4"]


def setup():
    @click.command()
    @click.option("--alpha")
    @click.option("--beta", type=int, default=3)
    @click.option("--gamma", is_flag=True)
    @click.option("--delta", multiple=True)
    @click.option("--epsilon", type=click.Choice(["a", "b", "c"]), default="a")
    @click.option("--zeta", type=click.Path())
    @click.option("--eta", type=float, default=1.5)
    @click.option("--theta", multiple=True)
    @click.option("--iota", is_flag=True)
    @click.option("--kappa", type=int, default=7)
    @click.argument("files", nargs=-1)
    def cmd(**kw):
        pass

    def once():
        cmd.make_context("prog", list(ARGV), parent=click.Context(cmd))
    return once
