# ### temporary hack, removeme ##
# import sys
# sys.path.append("..")
# ##########

import os
import json
from flask import Flask
from flask import render_template
from flask import g
from flask import Response
from flask import request
import pika
from werkzeug.utils import secure_filename
from pathlib import Path

def event_stream():

    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', port=5672))
    channel = connection.channel()
    channel.queue_declare(queue='status_queue', durable=True)
    
    # TODO: handle client disconnection.
    try:
        for message in channel.consume('status_queue', auto_ack=True):
            deliver, properties, text = message
            print(text.decode('utf-8'))
            yield f"data: {text.decode('utf-8')}\n\n"
    finally:
        channel.cancel()
        connection.close()

def send_task(ch, msg):
    ch.basic_publish(
            exchange='',
            routing_key='task_queue',
            body=msg,
            properties=pika.BasicProperties(
            delivery_mode=2,  # make message persistent
        ))

def send_status(ch, msg):
    ch.basic_publish(
            exchange='',
            routing_key='status_queue',
            body=msg,
            properties=pika.BasicProperties(
            delivery_mode=2,  # make message persistent
        ))
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
    app.run(threaded=True)

    UPLOAD_FOLDER = './uploads'
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
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

    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', port=5672))
    channel = connection.channel()
    channel.queue_declare(queue='task_queue', durable=True)
    channel.queue_declare(queue='status_queue', durable=True)
    

    # a simple page that says hello
    @app.route('/')
    def hello():
        return render_template('index.html')
    
    @app.route('/cmd', methods=['GET', 'POST'])
    def send_command():
        # if cmd legal, exists etc
        print(json.dumps(request.json))
        send_task(channel, json.dumps(request.json))

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
            file_path = Path(app.config['UPLOAD_FOLDER'])/ filename
            file.save(file_path)
            command = dict(command="Open_design", value=file_path.__fspath__())
            send_task(channel, json.dumps(command))
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

    from . import auth
    app.register_blueprint(auth.bp)
    ##app.teardown_appcontext(connection.close())
    return app


