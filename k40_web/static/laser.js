state = {
    variables: {
    "Reng_feed": 100,
    "Veng_feed": 20,
    "Vcut_feed": 10,
    "laser_pos": [0, 0],
    "laser_bed_size": [325, 220],
    "units": "mm",
    "Reng_image": "",
    "Veng_coords": [],
    "Vcut_coords": [],
    "Reng_coords": [],
    "Trace_coords": [],
    "pos_offset": [0, 0],
    // advanced
    "halftone": false,
    "invert": false,
    "mirror": false,
    "rotate": false,
    "inputCSYS": false,
    "design_scale": 1.0,
    "inside_first": true,
    "is_rotary": false,
    "Reng_passes": 1,
    "Veng_passes": 1,
    "Vcut_passes": 1,
    //raster
    "ht_size": 100,
    "rast_step": 100,
    "bezier_m1": 2.5,
    "bezier_m2": 0.5,
    "bezier_weight": 3.5,
    "bezier_plot": {"x": [], "y": []},
    },
    listeners: {},
    addListener: function (variable, listener){
        if(variable in this.listeners){
            this.listeners[variable].push(listener);
        }else{
            this.listeners[variable] = [listener];
        }
    },
}

function setValue(name, value){
    console.log("set value "+name+":"+value)
    state.variables[name] = value;
    if(name in state.listeners){
        state.listeners[name].forEach(listener => {
            listener(value);
        });
    }
}

function sendCommand(cmd, data=""){
    console.log(cmd+"("+data+") sent");
    fetch("/cmd/"+cmd, {
        headers: {
            'Content-Type': 'application/json'
        },
        method: "POST",
    body: JSON.stringify(data)
    });
}

function sendData(variable, data=""){
    console.log(variable+"("+data+") sent");
    fetch("/settings/"+variable, {
        headers: {
            'Content-Type': 'application/json'
        },
        method: "POST",
    body: JSON.stringify(data)
    });
}


function statusStream() {
    var source = new EventSource('/stream');
    var out = document.getElementById('statusbar');
    source.onmessage = function(e) {
        console.log(e.data);
        message = JSON.parse(e.data)
        switch(message.type){
            case "clear":
                newStatus(out, message.content);
            case "status":
                newStatus(out, message.content);
                break;
            case "information":
                newInformation(out, message.content);
                break;
            case "warning":
                newWarning(out, message.content);
                break;
            case "error":
                newError(out, message.content);
                break;
            case "fieldClear":
                var elm = document.getElementById(message.content);
                elm.classList.remove("fieldWarning", "fieldError");
                break;
            case "fieldWarning":
                var elm = document.getElementById(message.content);
                elm.classList.add("FieldError");
                break;
            case "fieldError":
                var elm = document.getElementById(message.content);
                elm.classList.add("fieldError");
                break;
            case "update":
                var elm = document.getElementById(message.content);
                if(elm){
                    elm.value = message.value;
                }else{
                    setValue(message.content, message.value);
                }
                break;
            default:
                console.log("unknown message type: "+message.type);
        }
        //out.innerHTML  =  out.innerHTML+ "<br>" +e.data;
    };
}

function bindInput(input, is_numeric=false){
    var elm = document.getElementById(input);
    
    elm.addEventListener("input",
        function(){
            var value = elm.value;
            if (is_numeric){
                value = parseFloat(value);
            }
            sendData(input, value);
            state.variables[input]=value;
        });
    state.addListener(input, function(value){elm.value = value;})
}

function bindButton(button){
    var elm = document.getElementById(button);
    elm.addEventListener("click", function(){sendCommand(button);});
}

function bindCheckbox(checkbox){
    var elm = document.getElementById(checkbox);
    elm.addEventListener("click", function(){
        sendData(checkbox, elm.checked);
            state.variables[checkbox] = elm.checked;
    });
    state.addListener(checkbox, function(value){elm.checked = value;})
}


function newInformation(statusbar_elm, text){
   var newDiv = newStatus(statusbar_elm, text);
   newDiv.classList.add("information");
}

function newWarning(statusbar_elm, text){
    var newDiv = newStatus(statusbar_elm, text);
    newDiv.classList.add("warning");
 }

 function newError(statusbar_elm, text){
    var newDiv = newStatus(statusbar_elm, text);
    newDiv.classList.add("error");
 }

function newStatus(statusbar_elm, text){
    var newDiv = document.createElement("div");
    var newContent = document.createTextNode(text);
    newDiv.appendChild(newContent);
    statusbar_elm.appendChild(newDiv);
    return newDiv;
  }

function setupCanvas(){
    canvas = document.getElementById("canvas");
    w = canvas.width;
    h = canvas.height;
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;

    ctx = canvas.getContext("2d");

    canvas.addEventListener("mousedown", (ev) => {
        var rect = canvas.getBoundingClientRect();
        var offset = transformCoord(state.variables["pos_offset"][0],state.variables["pos_offset"][1]);
        console.log(ev.clientX, rect.left, rect.width, canvas.width);
        var canvas_pos = [(ev.clientX- rect.left-offset[0]),
                        (ev.clientY- rect.top-offset[1])];
        setValue("laser_pos",  inverseTransformCoord(canvas_pos[0], canvas_pos[1]));
        var relative_pos = [canvas_pos[0]/rect.width, canvas_pos[1]/rect.height]
        sendCommand("mouse_click", relative_pos);
    });

    function inverseTransformCoord(x,y){
        MAXX = state.variables["laser_bed_size"][0];
        MINY = -state.variables["laser_bed_size"][1];
        var new_x = MAXX*x/canvas.width;
        var new_y = MINY*y/canvas.height;
        return [new_x, new_y];
    }

    function transformCoord(x,y){
        MAXX = state.variables["laser_bed_size"][0];
        MINY = -state.variables["laser_bed_size"][1];
        var new_x = canvas.width*x/MAXX;
        var new_y = canvas.height*y/MINY;
        return [new_x, new_y];
    }

    function draw_target(){
        var offset = transformCoord(state.variables["pos_offset"][0], state.variables["pos_offset"][1]);
        var coord = transformCoord(state.variables["laser_pos"][0], state.variables["laser_pos"][1]);
        ctx.fillStyle = "#7f7f7f";
        ctx.strokeStyle = "#7f7f7f";
        ctx.beginPath();
        var r = 5;
        var xpos = offset[0]+coord[0]-0.5;
        var ypos = offset[1]+coord[1]-0.5
        ctx.ellipse(
            xpos,
            ypos,
             r, r, 0, 0, 2.01 * Math.PI);
        ctx.closePath();
        ctx.stroke();
        ctx.fill();
        
        ctx.strokeStyle = "#AAAAAA";
        ctx.beginPath();
        if(offset[0] != 0 || offset[1] != 0){
            ctx.moveTo(xpos-r,ypos);
            ctx.lineTo(xpos+r,ypos);
            ctx.moveTo(xpos,ypos+r);
            ctx.lineTo(xpos,ypos-r);
        }
        ctx.closePath();
        ctx.stroke();
    }

    function draw_Reng_image(){
        var img = new Image();
        img.src = 'data:image/png;base64,'+state.variables["Reng_image"];
        coord = transformCoord(state.variables["laser_pos"][0], state.variables["laser_pos"][1]);
        img.onload = function(){
            ctx.drawImage(img, coord[0], coord[1]);
        }
    }

    function draw_coords(coords, color){
        var cursor_coord = transformCoord(state.variables["laser_pos"][0], state.variables["laser_pos"][1]);
        ctx.strokeStyle = color;
        ctx.beginPath();
        coords.forEach(coord => {
            var move_coord = transformCoord(coord[0], coord[1]);
            var line_coord = transformCoord(coord[2], coord[3]);
            var move_x_pos = cursor_coord[0]+move_coord[0];
            var move_y_pos = cursor_coord[1]+move_coord[1];
            ctx.moveTo(move_x_pos, move_y_pos);
            var line_x_pos = cursor_coord[0]+line_coord[0];
            var line_y_pos = cursor_coord[1]+line_coord[1];
            ctx.lineTo(line_x_pos, line_y_pos);
        });
        ctx.closePath();
        ctx.stroke();
    }

    function redraw(){
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        draw_Reng_image();
        draw_coords(state.variables["Veng_coords"], "#0000FF");
        draw_coords(state.variables["Vcut_coords"], "#FF0000");
        draw_coords(state.variables["Trace_coords"], "#00FF00");
        draw_target();
    }

    state.addListener("laser_pos", redraw);
    draw_target();

    state.addListener("Reng_image", redraw);
    state.addListener("Veng_coords", redraw);
    state.addListener("Vcut_coords", redraw);
    state.addListener("Trace_coords", redraw);
    state.addListener("pos_offset", redraw);
}

function setupBezierCanvas(){
    canvas = document.getElementById("bezierCanvas");
    w = canvas.width;
    h = canvas.height;

    ctx = canvas.getContext("2d");

    function redraw(){
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        ctx.strokeStyle = "#000000";
        ctx.beginPath();
        var bezier_x = state.variables["bezier_plot"]["x"];
        var bezier_y = state.variables["bezier_plot"]["y"];
        
        ctx.moveTo(w*bezier_x[0]/255, h-h*bezier_y[0]/255);
        for(var i = 0; i < bezier_x.length; i++){
            ctx.lineTo(w*bezier_x[i]/255, h-h*bezier_y[i]/255);
        }
        ctx.moveTo(w*bezier_x[0]/255, h-h*bezier_y[0]/255);
        ctx.closePath();
        ctx.stroke();
    }
    
    state.addListener("bezier_plot", redraw);
}

function upload_file_setup(){
    var btn = document.getElementById("Upload_file");
    var upload_elm = document.getElementById("file_select");
    btn.addEventListener("click", function(){
        const formData = new FormData();
        formData.append("file", upload_elm.files[0]);
        console.log(formData.files);
        fetch("/upload", {
            method: "POST",
            body: formData,
        });
    });
}

var tabs;
var buttons;
function tabUpdate(new_active){
    var idx = buttons.indexOf(document.getElementById(new_active.id));
    buttons.forEach(element => {
        element.classList.remove("active");
    });
    buttons[idx].classList.add("active");
    tabs.forEach(element => {
        element.classList.remove("active");
        element.classList.remove("show");
    });
    tabs[idx].classList.add("active");
    tabs[idx].classList.add("show");
}

function addTabs(tab_list, button_list){
    tabs = tab_list;
    buttons = button_list;
    function btnCallback(ev){
        tabUpdate(ev.target);
    }
    for(var i = 0; i < button_list.length; i++){
        button_list[i].addEventListener("click", btnCallback);
    }
}

function init_UI(){
    // control tab
    bindButton("Initialize_Laser");
    bindButton("Home");
    bindButton("Unlock");

    bindButton("Move_UL");
    bindButton("Move_UC");
    bindButton("Move_UR");
    bindButton("Move_CL");
    bindButton("Move_CC");
    bindButton("Move_CR");
    bindButton("Move_LL");
    bindButton("Move_LC");
    bindButton("Move_LR");

    bindButton("Move_Up");
    bindButton("Move_Left");
    bindButton("Move_Down");
    bindButton("Move_Right");
    
    bindButton("Raster_Eng");
    bindButton("Vector_Eng");
    bindButton("Vector_Cut");

    bindInput("Reng_feed", true);
    bindInput("Veng_feed", true);
    bindInput("Vcut_feed", true);

    bindButton("Reload_design");
    // advanced tab
    bindCheckbox("halftone");
    bindCheckbox("invert");
    bindCheckbox("mirror");
    bindCheckbox("rotate");
    bindCheckbox("inputCSYS");
    bindInput("design_scale", true);
    bindCheckbox("inside_first");
    bindCheckbox("is_rotary");
    bindCheckbox("comb_engrave");
    bindCheckbox("comb_vector");

    bindInput("Reng_passes", true);
    bindInput("Veng_passes", true);
    bindInput("Vcut_passes", true);
    // settings tab
    // raster tab
    bindInput("rast_step", true);
    bindInput("ht_size", true);

    bindCheckbox("engrave_up");
    bindInput("bezier_m1", true);
    bindInput("bezier_m2", true);
    bindInput("bezier_weight", true);
    // trace tab

    upload_file_setup();
    // ensure all values are initialized
    for(var variable in state.listeners) {
        state.listeners[variable].forEach(listener => {
            listener(state.variables[variable]);
        });
    }

    addTabs([control, advanced, settings, raster, trace], [control_tab, advanced_tab, settings_tab, raster_tab, trace_tab])

    statusStream();
    setupCanvas();
    setupBezierCanvas();
}