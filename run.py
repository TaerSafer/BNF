#!/usr/bin/env python3
"""Lance le serveur O.R.I.O.N. — RedRock Capital"""
from orion.server import start_server

if __name__ == "__main__":
    start_server(host="0.0.0.0", port=8000)
