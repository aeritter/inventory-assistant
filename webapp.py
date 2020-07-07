from flask import Flask, request, render_template
from flask_socketio import SocketIO, emit, join_room, send
import time, threading
app = Flask(__name__)
socketio = SocketIO(app)

log = {"content":["initial data here" for x in range(5)]}

@app.route("/")
def home():
    return render_template('status.html')



@app.route("/status")
def status():
    return render_template('status.html')



@app.route("/logs")
def logs():
    return render_template('logs.html', **log)

@socketio.on('loadlogs')
def logsconnect(methods=["GET","POST"]):
    for x in log["content"]:
        emit("addlog", x)



@app.route("/settings")
def settings():
    return render_template('settings.html')



@app.route("/pdfsettings")
def pdfsettings():
    return render_template('processingsettings.html')


def addtolog(msg):
    x = 0
    while True:
        time.sleep(1)
        x+=1
        socketio.emit("addlog", msg+str(x))


if __name__ == "__main__":
    threading.Thread(target=(addtolog), args=(["Test, line #"])).start()
    socketio.run(app, debug=True)
