import os
import json
from flask import Flask
from flask import render_template
from flask import g
from flask import Response
from flask import request
from werkzeug.utils import secure_filename
from pathlib import Path


from zmq import Context, PUB, SUB, SUBSCRIBE
context = Context()

task_socket = context.socket(PUB)
task_socket.connect("tcp://localhost:6660")
status_socket = context.socket(PUB)
status_socket.connect("tcp://localhost:5556")

def event_stream():
    status_socket = context.socket(SUB)
    status_socket.setsockopt(SUBSCRIBE, b"")
    status_socket.connect("tcp://localhost:5556")
    while True:
        text = status_socket.recv_string()
        yield f"data: {text}\n\n"

def send_task(msg):
    task_socket.send_string(msg)

def send_status(msg):
    status_socket.send_string(msg)
'''
[("SVG Files ", "*.svg"),
    ("G-Code Files ", ("*.ngc",
                        "*.gcode", "*.g", "*.tap")),
    ("DXF Files ", "*.dxf"),
    ("All Files ", "*"),
   #// ("Design Files ", ("*.svg", "*.dxf"))],
'''
ALLOWED_EXTENSIONS = {"svg", "gcode", "png", "jpg"}
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'flaskr.sqlite'),
    )
    if __name__ == "__main__":
        app.run(threaded=True)
    
    # mythread = WorkerThread()
    # mythread.start()
    
    UPLOAD_FOLDER = './uploads'
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    upload_folder_path = Path(UPLOAD_FOLDER)
    if not upload_folder_path.exists():
        upload_folder_path.mkdir()
    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass


    # a simple page that says hello
    @app.route('/')
    def index():
        return render_template('index.html')


    @app.route('/cmd/<command>', methods=['GET', 'POST'])
    def send_command(command):
        # if cmd legal, exists etc
        print(json.dumps(request.json))
        send_task(json.dumps(dict(command=command, parameter=request.json)))
        return "OK"


    @app.route("/settings/<param>", methods=["GET", "POST"])
    def settings_rest(param):
        print(json.dumps(request.json))
        if request.method == "POST":
            send_task(json.dumps(dict(command="set", key=param, value=request.json)))
        else:
            send_task(json.dumps(dict(command="get", key=param)))

        return "OK"


    @app.route('/upload', methods=['POST'])
    def upload():
        # check if the post request has the file part
        print("received upload")
        if 'file' not in request.files:
            print("no file in upload")
            return "NOT OK"
        file = request.files['file']
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == '':
            print("no file uploaded")
            send_status('{"type": "error", "content":"No file selected"}')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = Path(app.config['UPLOAD_FOLDER']) / filename
            file.save(file_path)
            command = dict(command="Open_design", parameter=file_path.__fspath__())
            send_task(json.dumps(command))
            return "OK"
        else:
            print("file format not accepted")
        return "NOT OK"


    @app.route('/stream')
    def stream():
        return Response(event_stream(),
                        mimetype="text/event-stream")

    from . import db
    db.init_app(app)

    ##app.teardown_appcontext(connection.close())
    return app
