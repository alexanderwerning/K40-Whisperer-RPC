import os
import json
from flask import Flask
from flask import render_template
from flask import g
from flask import Response
from flask import request
from werkzeug.utils import secure_filename
from pathlib import Path

from k40_web.worker import work

from queue import Queue, Empty
from threading import Thread

statusQueue = Queue(10)
taskQueue = Queue(10)

class WorkerThread (Thread):
    def __init__(self):
        Thread.__init__(self)
    def run(self):
        print ("Starting " + self.name)
        try:
            work(taskQueue, statusQueue)
        except KeyboardInterrupt as e:
            raise e
        print ("Exiting " + self.name)

def event_stream():
    while True:
        try:
            text = statusQueue.get(timeout=1)
            yield f"data: {text}\n\n"

        except Empty:
            pass

def send_task(msg):
    taskQueue.put(msg)

def send_status(msg):
    statusQueue.put(msg)
'''
[("SVG Files ", "*.svg"),
    default_types,
    ("G-Code Files ", ("*.ngc",
                        "*.gcode", "*.g", "*.tap")),
    ("DXF Files ", "*.dxf"),
    ("All Files ", "*"),
    ("Design Files ", ("*.svg", "*.dxf"))],


        design_types = ("Design Files", ("*.svg", "*.dxf"))
        gcode_types = ("G-Code Files", ("*.ngc", "*.gcode", "*.g", "*.tap"))
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
    
    mythread = WorkerThread()
    mythread.start()
    
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


    @app.route('/cmd', methods=['GET', 'POST'])
    def send_command():
        # if cmd legal, exists etc
        print(json.dumps(request.json))
        send_task(json.dumps(request.json))

        return "OK"


    @app.route("/settings/<param>", methods=["GET", "POST"])
    def command_sync(param):
        print(json.dumps(request.json))
        if request.method == "POST":
            send_task(json.dumps(dict(cmd="set", key=param, value=request.json)))
        else:
            send_task(json.dumps(dict(cmd="get", key=param)))

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
            command = dict(command="Open_design", value=file_path.__fspath__())
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
