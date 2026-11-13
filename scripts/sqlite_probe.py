import json
import platform
import sqlite3
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory


def probe():
    with TemporaryDirectory(prefix="sqlite-uri-probe-") as directory, chdir(directory):
        root = Path(directory)
        uri = "file:shared?mode=memory&cache=shared"
        keeper = sqlite3.connect(uri, uri=True)
        try:
            keeper.execute("CREATE TABLE sample (value INTEGER)")
            keeper.execute("INSERT INTO sample VALUES (123)")
            keeper.commit()
            results = []
            for enabled in (False, True):
                connection = sqlite3.connect(root / f"disk-{enabled}.db", uri=enabled)
                try:
                    connection.execute("ATTACH DATABASE ? AS shared", (uri,))
                    try:
                        value = connection.execute(
                            "SELECT value FROM shared.sample"
                        ).fetchone()[0]
                    except sqlite3.OperationalError as error:
                        value = str(error)
                    results.append(
                        {
                            "uri_enabled": enabled,
                            "attached_filename": connection.execute(
                                "PRAGMA database_list"
                            ).fetchall()[-1][2],
                            "value": value,
                        }
                    )
                finally:
                    connection.close()
            return {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
                "compile_options": [
                    row[0] for row in keeper.execute("PRAGMA compile_options")
                ],
                "connections": results,
            }
        finally:
            keeper.close()


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
