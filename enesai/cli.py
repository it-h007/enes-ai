"""CLI: flask --app run create-owner / migrate."""
import click


def register(app):
    @app.cli.command("create-owner")
    @click.option("--username", prompt="Emri i përdoruesit")
    @click.option("--name", prompt="Emri i plotë", default="Pronari")
    @click.password_option("--password", prompt="Fjalëkalimi")
    def create_owner_cmd(username, name, password):
        from .services.auth import create_owner
        ok, msg = create_owner(username, name, password)
        click.echo(msg)
        if not ok:
            raise SystemExit(1)
