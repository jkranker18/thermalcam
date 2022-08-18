#!/usr/bin/env python3
# Copyright 2021 Seek Thermal Inc.
#
# Original author: Michael S. Mead <mmead@thermal.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from threading import Condition
import cv2
import numpy
import PIL.Image
import os
import glob
from PIL import Image, ImageFont, ImageDraw
from flask import Flask, render_template, Response, request, redirect
from seekcamera import (
    SeekCameraIOType,
    SeekCameraColorPalette,
    SeekCameraManager,
    SeekCameraManagerEvent,
    SeekCameraFrameFormat,
    SeekCameraShutterMode,
    SeekCamera,
    SeekFrame,
)
app = Flask(__name__)
# videoNew = cv2.VideoCapture(0)
# local testing
# def gen(video2, color):
#     while True:
#         success, image = video2.read()
#         ret, jpeg = cv2.imencode('.jpg', image)
#         frame = jpeg.tobytes()
#         yield (b'--frame\r\n'
#                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
#
# @app.route('/video')
# def video():
#     # Video streaming route. Put this in the src attribute of an img tag
#     print("video args", request.args)
#     videoNew = cv2.VideoCapture(0)
#     if "color" in request.args:
#         x = request.args.get('color')
#         print("video color", x)
#         # print(getcolor(x))
#         return Response(gen(videoNew, x), mimetype='multipart/x-mixed-replace; boundary=frame')
#     return Response(gen(videoNew, 1), mimetype='multipart/x-mixed-replace; boundary=frame')
# thermal cam routes
@app.route('/video')
def video():
    print("video stream init", request.args)
    if "color" in request.args:
        color = request.args.get('color')
        print("video color", color)
        return Response(run_camera(color),
                        mimetype='multipart/x-mixed-replace; boundary=frame')
    return Response(run_camera(4),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
@app.route('/home', methods=["GET"])
def index():
    """Video streaming home page."""
    print("home page load", request.args)
    if "color" in request.args:
        # x = getColor(request.args.get('color'))
        x = request.args.get('color')
        print("color", x)
        return render_template('index.html', number=x)
    print("no color")
    return render_template('index.html', number=4)
class Renderer:
    """Contains camera and image data required to render images to the screen."""
    def __init__(self):
        self.busy = False
        self.frame = SeekFrame()
        self.camera = SeekCamera()
        self.frame_condition = Condition()
        self.first_frame = True
def on_frame(_camera, camera_frame, renderer):
    """Async callback fired whenever a new frame is available.
    Parameters
    ----------
    _camera: SeekCamera
        Reference to the camera for which the new frame is available.
    camera_frame: SeekCameraFrame
        Reference to the class encapsulating the new frame (potentially
        in multiple formats).
    renderer: Renderer
        User defined data passed to the callback. This can be anything
        but in this case it is a reference to the renderer object.
    """
    # Acquire the condition variable and notify the main thread
    # that a new frame is ready to render. This is required since
    # all rendering done by OpenCV needs to happen on the main thread.
    print("on frame async")
    with renderer.frame_condition:
        renderer.frame = camera_frame.color_argb8888
        renderer.frame_condition.notify()
def on_event(camera, event_type, event_status, renderer):
    """Async callback fired whenever a camera event occurs.
    Parameters
    ----------
    camera: SeekCamera
        Reference to the camera on which an event occurred.
    event_type: SeekCameraManagerEvent
        Enumerated type indicating the type of event that occurred.
    event_status: Optional[SeekCameraError]
        Optional exception type. It will be a non-None derived instance of
        SeekCameraError if the event_type is SeekCameraManagerEvent.ERROR.
    renderer: Renderer
        User defined data passed to the callback. This can be anything
        but in this case it is a reference to the Renderer object.
    """
    print("on event", "{}: {}".format(str(event_type), camera.chipid))
    if event_type == SeekCameraManagerEvent.CONNECT:
        if renderer.busy:
            return
        print("camera connected")
        # Claim the renderer.
        # This is required in case of multiple cameras.
        renderer.busy = True
        renderer.camera = camera
        # Indicate the first frame has not come in yet.
        # This is required to properly resize the rendering window.
        renderer.first_frame = True
        # Set a custom color palette.
        # Other options can set in a similar fashion.
        # camera.color_palette = SeekCameraColorPalette.TYRIAN
        # Start imaging and provide a custom callback to be called
        # every time a new frame is received.
        camera.register_frame_available_callback(on_frame, renderer)
        camera.capture_session_start(SeekCameraFrameFormat.COLOR_ARGB8888)
    elif event_type == SeekCameraManagerEvent.DISCONNECT:
        print("camera disconnected")
        # Check that the camera disconnecting is one actually associated with
        # the renderer. This is required in case of multiple cameras.
        if renderer.camera == camera:
            # Stop imaging and reset all the renderer state.
            camera.capture_session_stop()
            renderer.camera = None
            renderer.frame = None
            renderer.busy = False
    elif event_type == SeekCameraManagerEvent.ERROR:
        print("{}: {}".format(str(event_status), camera.chipid))
    elif event_type == SeekCameraManagerEvent.READY_TO_PAIR:
        return
def bgra2rgb(bgra):
    print("convert image")
    row, col, ch = bgra.shape
    assert ch == 4, 'ARGB image has 4 channels.'
    rgb = numpy.zeros((row, col, 3), dtype='uint8')
    # convert to rgb expected to generate the jpeg image
    rgb[:, :, 0] = bgra[:, :, 2]
    rgb[:, :, 1] = bgra[:, :, 1]
    rgb[:, :, 2] = bgra[:, :, 0]
    return rgb
def gen_frame(frame):  # generate frame by frame from camera
    print("gen frame")
    ret, buffer = cv2.imencode('.jpg', frame)
    frame = buffer.tobytes()
    yield (b'--frame\r\n'
           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')  # concat frame one by one and show result
def getcolor(int):
    print("get color func", int)
    return {
        0: SeekCameraColorPalette.WHITE_HOT,
        1: SeekCameraColorPalette.BLACK_HOT,
        2: SeekCameraColorPalette.SPECTRA,
        3: SeekCameraColorPalette.PRISM,
        4: SeekCameraColorPalette.TYRIAN,
        5: SeekCameraColorPalette.IRON,
        6: SeekCameraColorPalette.AMBER,
        7: SeekCameraColorPalette.HI,
        8: SeekCameraColorPalette.GREEN,
        9: SeekCameraColorPalette.USER_0,
        10: SeekCameraColorPalette.USER_1,
        11: SeekCameraColorPalette.USER_2,
        12: SeekCameraColorPalette.USER_3,
        13: SeekCameraColorPalette.USER_4,
    }.get(int, SeekCameraColorPalette.TYRIAN)
def run_camera(colorInt):
    print("run camera with color", colorInt)
    # window_name = "Seek Thermal - Python OpenCV Sample"
    # from PIL import Image
    from pathlib import Path
    # for f in glob.glob(fileName + '*.jpg'):
    #     os.remove(f)
    with SeekCameraManager(SeekCameraIOType.USB) as manager:
        # Start listening for events.
        renderer = Renderer()
        manager.register_event_callback(on_event, renderer)
        print("Camera started")
        # print("Note: shutter is disabled while recording...so keep the videos relatively short")
        while True:
            # Wait a maximum of 150ms for each frame to be received.
            # A condition variable is used to synchronize the access to the renderer;
            # it will be notified by the user defined frame available callback thread.
            renderer.camera.shutter_mode = SeekCameraShutterMode.MANUAL
            # color = getcolor(colorInt)
            # print("got color", color)
            if colorInt == "0":
                renderer.camera.color_palette = SeekCameraColorPalette.WHITE_HOT
            elif colorInt == "1":
                renderer.camera.color_palette = SeekCameraColorPalette.BLACK_HOT
            elif colorInt == "2":
                renderer.camera.color_palette = SeekCameraColorPalette.SPECTRA
            elif colorInt == "3":
                renderer.camera.color_palette = SeekCameraColorPalette.PRISM
            elif colorInt == "4":
                renderer.camera.color_palette = SeekCameraColorPalette.TYRIAN
            elif colorInt == "5":
                renderer.camera.color_palette = SeekCameraColorPalette.IRON
            elif colorInt == "6":
                renderer.camera.color_palette = SeekCameraColorPalette.AMBER
            elif colorInt == "7":
                renderer.camera.color_palette = SeekCameraColorPalette.HI
            elif colorInt == "8":
                renderer.camera.color_palette = SeekCameraColorPalette.GREEN
            elif colorInt == "9":
                renderer.camera.color_palette = SeekCameraColorPalette.USER_0
            elif colorInt == "10":
                renderer.camera.color_palette = SeekCameraColorPalette.USER_1
            elif colorInt == "11":
                renderer.camera.color_palette = SeekCameraColorPalette.USER_2
            elif colorInt == "12":
                renderer.camera.color_palette = SeekCameraColorPalette.USER_3
            elif colorInt == "13":
                renderer.camera.color_palette = SeekCameraColorPalette.USER_4
            else:
                print('color int not set', colorInt)
                renderer.camera.color_palette = SeekCameraColorPalette.TYRIAN
            with renderer.frame_condition:
                print("frame condition received")
                # renderer.camera.shutter_mode = SeekCameraShutterMode.MANUAL
                if renderer.frame_condition.wait(150.0 / 1000.0):
                    print("create image received")
                    img = renderer.frame.data
                    ret, jpeg = cv2.imencode('.jpg', img)
                    frame = jpeg.tobytes()
                    print("frame generated")
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
        print("manager false")
        # renderer.camera.shutter_mode = SeekCameraShutterMode.AUTO
    print("no manager")
def main():
    print("running app")
if __name__ == "__main__":
    app.run(debug=True)