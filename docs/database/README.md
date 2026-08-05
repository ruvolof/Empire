# Database

Beginning in Empire 5.0, MySQL is the default database. Trying to support multi-user setups and expanding our usage of the database started to reach limitations in SQLite. SQLite is still supported, and we run the full test suite against it, but is not recommended.

For database configuration see the [Configuration](../quickstart/server.md) section.

## Setup
The install script will install MySQL if you install on one of the supported operating systems. If you want to switch between MySQL and SQLite, change the `use` property in the `database` section of the configuration file.

Config values can also be set via environment variables. The convention is to use `EMPIRE_TOPLEVEL__NEXT_SETTING` for each setting in `config.yaml`.
For example: `EMPIRE_DATABASE__USE='mysql'` will override the `database.use` setting in `config.yaml`.

## Migrations

Empire uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations. This allows schema changes to be applied incrementally without requiring a full database reset.

On startup, `startup_db()` stamps databases not yet tracked by Alembic at the baseline revision (`0001`), not head. When future updates include schema changes, migrations bring the database up to head via the `migrate_db()` function without data loss.

### Creating a new migration

After modifying SQLAlchemy models in `empire/server/core/db/models.py`, generate a migration:

```bash
poetry run alembic revision --autogenerate -m "describe the change"
```

Review the generated file in `empire/server/core/db/alembic/versions/` to ensure the `upgrade()` and `downgrade()` functions are correct, then commit it with your model changes.

To apply pending migrations on existing databases, run the following from the Empire root directory:

```bash
poetry run alembic -c alembic.ini upgrade head
```

Empire stamps fresh databases at baseline automatically on startup but does NOT auto-apply migrations. Run the command above after upgrading Empire to a release that includes new migrations.

### Backing up before migrations

The `backup_db()` function creates a timestamped backup before applying migrations:
- **SQLite**: copies the database file to `~/.local/share/empire/backups/`
- **MySQL**: runs `mysqldump` to the same backup directory

# Docker
The Docker image still defaults to SQLite. To use MySQL, you can change `config.yaml` or utilize the `DATABASE_USE` enviornment variable. For example `docker run -p 3306:3306 -p 1337:1337 -e DATABASE_USE='mysql' -it bcsecurity/empire:latest`.
The Docker image does not contain MySQL, so you will need to run a MySQL container or install MySQL on the host machine.
