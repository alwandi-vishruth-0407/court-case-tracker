"""Check MySQL access without printing the runtime password."""
import os
import sys

import mysql.connector

try:
    connection = mysql.connector.connect(
        host="127.0.0.1", port=3306, user="root",
        password=os.environ["DB_PASSWORD"], connection_timeout=3,
    )
    if "--shutdown" in sys.argv:
        cursor = connection.cursor()
        cursor.execute("SHUTDOWN")
        cursor.close()
    else:
        cursor = connection.cursor()
        cursor.execute("SELECT VERSION(), CURRENT_USER()")
        print(cursor.fetchone())
        cursor.close()
    connection.close()
except mysql.connector.Error as error:
    print(f"MySQL connection failed: {error.errno}: {error.msg}", file=sys.stderr)
    sys.exit(1)
