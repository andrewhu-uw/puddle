let fetch_data = null;
let game;
let droplets = []; // holds droplets from state-to-state
let ready = false; // 'ready' continuous animation checkbox
let running = false; // flag for animation after onComplete
let server_closed = false;
let prev_json = [];
let json_queue = [];
let frame = 0;
let forward = true;
let last_range = 100;
const CELL_SIZE = 50;
const TWEEN_TIME = 200; // in millisec
// TODO: remove when volume is no longer used
const Y_OFFSET = 50; // downward offset to leave room for volume droplets

/**
 * Loads all of the necessary Phaser stuff and initializes
 * the step function.
 * TODO: ensure devicePixelRatio takes care of high-res screens
 * TODO: add tween when volume increases
 */
window.onload = function() {
    game = new Phaser.Game(
        window.innerWidth * window.devicePixelRatio,
        window.innerHeight * window.devicePixelRatio / 2,
        Phaser.CANVAS,
        'game');

    var step = function(game) {};

    step.prototype = {
        // load assets here if we wind up with any
        preload: function() {},

        create: function() {

            game.stage.backgroundColor = "#ffffff";
            game.physics.startSystem(Phaser.Physics.ARCADE);

            fetch_data();

            document.getElementById("back").onclick = function() {
                frame--;
                animate(prev_json[frame]);
            }

            document.getElementById("step").onclick = function() {
                if (prev_json.length > 0) {
                    if (frame == prev_json.length - 1) {
                        if (!server_closed) {
                            fetch_data();
                            frame++;
                        }

                    } else {
                        frame++;
                        animate(prev_json[frame]);
                    }
                }
            }

            document.getElementById("ready").onclick = function() {
                if (this.checked) {
                    run_animation();
                }
                ready = this.checked;
            }

            document.getElementById("slider").oninput = function() {
                console.log(this.value);
                forward = this.value < last_range;
            }
            document.addEventListener('keypress', (event) => {
              const keyName = event.key;
              if (keyName == 'l') {
                console.log('keypress event\n\n' + 'key: ' + keyName);
            }
            });

            game.stage.disableVisibilityChange = true;
        },

        update: function() {},
    };

    game.state.add("step", step);
    game.state.start("step");
};

/**
 * Takes information about a set of droplets and either
 * initializes the board or animates from the previous state.
 * @param {json} array of droplet json
 */
function parse_data(data) {
    prev_json.push(data);
    if (droplets.length == 0) {
        for (let json of data) {
            add_drop(json);
        }
    } else {
        if (!running) {
            animate(prev_json[frame]);
        } else {
            json_queue.push(data);
        }
    }
}

/**
 * Takes json for a single droplet and adds it to the board.
 * Initializes the associated tween and sprite and stores
 * each droplet by associated id in droplets.
 * @param {json} single droplet json
 */
function add_drop(json) {
    let s = game.add.sprite((json.location[1] * CELL_SIZE), (json.location[0] * CELL_SIZE) + Y_OFFSET);
    for (let cell of json.shape) {
        let graphics = game.add.graphics(0, 0);
        let y = cell[0] * CELL_SIZE;
        let x = cell[1] * CELL_SIZE;
        graphics.beginFill(0x006699)
            .drawCircle(x, y, Math.sqrt(json.volume) * CELL_SIZE)
            .endFill();
        s.addChild(graphics);
    }
    let tween = game.add.tween(s);
    let drop = {
        sprite: s,
        deleted: false,
        id: json.id,
        volume: json.volume,
        info: json.info
    };
    droplets[json.id] = drop;
}

/**
 * Cycles through the queue of data, which grows
 * whenever 'step' is called or 'ready' is checked.
 */
function animate_queue() {
    if (json_queue.length == 0) {
        running = false;
    } else {
        animate(json_queue.shift());
        running = true;
    }
}

/**
 * Takes json for a set of droplets and creates a tween
 * from their previous state to the next one, removing
 * drops and creating combinations along the way.
 * Assigns the onComplete function to the first drop
 * in every set of droplets.
 * @param {data} array of droplet json
 */
function animate(data) {
    remove_drops(data);
    let count = 0;
    for (let json of data) {
        let drop = droplets[json.id];

        if (drop == null) {
            add_drop(json);
        }

        if (drop != null) {
            if (drop.deleted) {
                drop.sprite.revive();
                drop.deleted = false;
            }
            let x = json.location[1] * CELL_SIZE;
            let y = json.location[0] * CELL_SIZE + Y_OFFSET;
            let tween = game.add.tween(drop.sprite)
                .to({ x: x, y: y },
                    TWEEN_TIME / (json_queue.length + 1),
                    Phaser.Easing.Quadratic.InOut).start()
            if (count == 0) {
                tween.onComplete.add(onComplete, this);
            }
            count++;
        }
    }
}

/**
 * Removes drops that have been combined from one state
 * to the next.
 * @param {data} array of droplet json
 */
function remove_drops(data) {
    let new_ids = [];
    for (let id of data) {
        new_ids.push(id.id);
    }
    for (let droplet of droplets) {
        if (droplet != undefined) {
            if (new_ids.indexOf(droplet.id) == -1) {
                droplets[droplet.id].sprite.kill();
                droplets[droplet.id].deleted = true;
            }
        }
    }
}

/**
 * Function that begins operations for the next set of
 * droplets once the previous set has completed.
 */
function onComplete() {
    animate_queue();
}

/**
 * Begins execution whenever the 'ready' button is clicked
 * and runs continuously on a 500 ms interval until it's
 * clicked again.
 */
function run_animation() {
    let interval_id = setInterval(function() {
        if (ready && !server_closed) {
            fetch_data();
        } else {
            clearInterval(interval_id);
        }
    }, 500);
}

$(function() {
    function jQuery_fetch(){
        var fetch = $.getJSON('/state', parse_data)
            .fail(function() {
                server_closed = true;
            });
    }
    fetch_data = jQuery_fetch;
});
