from flask import Flask, render_template
from flask_socketio import SocketIO

socketio = SocketIO()

def webapp():
    app = Flask(__name__)

    # import logging
    # log = logging.getLogger('werkzeug')
    # log.setLevel(logging.ERROR)

    @app.route("/")
    def home():
        return render_template('status.html')


    @app.route("/status")
    def status():
        return render_template('status.html')


    @app.route("/logs")
    def logs():
        return render_template('logs.html')


    @app.route("/settings")
    def settings():
        sections=(
            {
                "title":"Switches",
                "content":(
                    {"description":"Slack Notifications", "name":"Slack", "type":"toggle"},
                    {"description":"Airtable Posts", "name":"Airtable", "type":"toggle"},
                    {"description":"Debug Messages", "name":"Debug", "type":"toggle"}
            )},
            {
                "title":"Check-in",
                "content":(
                    {"description":"Enable Slack daily check-in", "name":"Check-in", "type":"toggle"},
                    {"description":"Initial hour of the day to check-in (upon program startup)", "name":"Check-in hour", "type":"textbox"},
                    {"description":"Time between check-ins (in minutes)", "name":"Check-in minutes", "type":"textbox"}
            )}
            )
        return render_template('settings.html', sections=sections)


    @app.route("/pdfsettings")
    def pdfsettings():
        return render_template('processingsettings.html')

    socketio.init_app(app)
    return app

# for testing
if __name__ == "__main__":
    socketio.run(webapp())
    print("Running!")
