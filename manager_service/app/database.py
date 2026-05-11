import psycopg2
from psycopg2.extras import RealDictCursor

import config

class Database:
    def __init__(
        self,
        host: str | None,
        db: str | None,
        user: str | None,
        password: str | None,
        port: int
    ):
        self.host: str | None = host
        self.db: str | None = db
        self.user: str | None = user
        self.password: str | None = password

        if port > 0:
            self.port = port
        else:
            self.port = -1

        self._conn = None
        self._cursor = None
        self.connected = False

        if (host is None) or (db is None) or (user is None) or (password is None) or (port == -1):
            print(f"[database.py] Database.__init__: Initialization failed " +
                  f"[host = {host}, db = {db}, user = {user}, " +
                  f"password = {password}, port = {port}]"
            )
            self.host = None
            self.db = None
            self.user = None
            self.password = None
            self.port = -1
        else:
            print(f"[database.py] Database.__init__: Initialized successfully " +
                  f"[host = {host}, db = {db}, user = {user}, " +
                  f"password = {password}, port = {port}]"
            )

    def connect(self) -> bool:
        try:
            self._conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.db,
                user=self.user,
                password=self.password,
                cursor_factory=RealDictCursor
            )

            self.connected = True
            print(f"[database.py] Database.connect: Connection successful")
        except psycopg2.Error as ex:
            print(f"[database.py] Database.connect: Connection failed [{ex}]")

            self.connected = False
            self._conn = None

            return False

        return True

    def disconnect(self) -> bool:
        res: bool = True
        self.connected = False

        if self._conn is not None:
            try:
                self._conn.close()
                print(f"[database.py] Database.disconnect: Disconnection successful")
            except psycopg2.Error as ex:
                res = False
                print(f"[database.py] Database.disconnect: Disconnection failed [{ex}]")

        self._conn = None

        return res

    def cursor(self):
        if (not self.connected) or (self._conn is None):
            print(f"[database.py] Database.cursor: Not connected")
            return None

        if self._cursor is None:
            try:
                self._cursor = self._conn.cursor()
            except psycopg2.Error as ex:
                print(f"[database.py] Database.cursor: Could not get cursor [{ex}]")

        return self._cursor

    def close(self):
        if (not self.connected) or (self._conn is None):
            print(f"[database.py] Database.close: Not connected")
            return False

        res: bool = True

        if self._cursor is not None:
            try:
                self._cursor.close()
            except psycopg2.Error as ex:
                print(f"[database.py] Database.close: Close failed [{ex}]")
                res = False

        self._cursor = None

        return res

    def commit(self) -> bool:
        if (not self.connected) or (self._conn is None):
            print(f"[database.py] Database.commit: Not connected")
            return False

        try:
            self._conn.commit()
        except psycopg2.Error as ex:
            print(f"[database.py] Database.commit: commit failed [{ex}]")
            self._conn.rollback()
            return False

        return True


dds_db = Database(
    config.DDS_DB_SERVER,
    config.DDS_DB_NAME,
    config.DDS_DB_USER,
    config.DDS_DB_PASSWORD,
    config.DDS_DB_PORT
)
