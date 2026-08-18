#!/usr/bin/env python3
"""WSGI entrypoint for hosted deployments.

Platforms auto-detect Flask by scanning for conventional module names, and
``ui_app`` is not one of them. This exposes the same app object under a name
they recognise:

    gunicorn wsgi:app

Note that Fetch is designed as a local tool: downloads are written to the
machine running the server, and nothing serves them back to the browser.
Hosting this gives you the UI, not a working download.
"""

from ui_app import app

__all__ = ["app"]
