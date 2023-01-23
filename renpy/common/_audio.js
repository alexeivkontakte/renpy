﻿/* Copyright 2004-2023 Tom Rothamel <pytom@bishoujo.us>
 *
 * Permission is hereby granted, free of charge, to any person
 * obtaining a copy of this software and associated documentation files
 * (the "Software"), to deal in the Software without restriction,
 * including without limitation the rights to use, copy, modify, merge,
 * publish, distribute, sublicense, and/or sell copies of the Software,
 * and to permit persons to whom the Software is furnished to do so,
 * subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
 * LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
 * OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
 * WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 */

const USE_TGA = true;  // XXX TGA support is disabled in SDL2 for RenpyWeb :(
// const USE_TGA = false;  // XXX TGA support is disabled in SDL2 for RenpyWeb :(

/**
 * A map from channel to channel object.
 */
let channels = { };
let next_chan_id = 0;

let context = new AudioContext();

/**
 * Given a channel number, gets the channel object, creating a new channel
 * object if required.
 */
let get_channel = (channel) => {

    let c = channels[channel];

    if (c) {
        return c;
    }

    c = {
        playing : null,
        queued : null,
        stereo_pan : context.createStereoPanner(),
        fade_volume : context.createGain(),
        primary_volume : context.createGain(),
        secondary_volume : context.createGain(),
        relative_volume : context.createGain(),
        paused : false,
        video: false,
        video_el: null,
        canvas_el: null,
        canvas_ctx: null,
        chan_id: next_chan_id++,
        video_frame: null,
        media_source: null,
        tga_header: null,
    };

    c.destination = c.stereo_pan;
    c.stereo_pan.connect(c.fade_volume);
    c.fade_volume.connect(c.primary_volume);
    c.primary_volume.connect(c.secondary_volume);
    c.secondary_volume.connect(c.relative_volume);
    c.relative_volume.connect(context.destination);

    channels[channel] = c;

    return c;
};

let interpolate = (a, b, done) => {
    return a + (b - a) * done;
}

/**
 * Given an audio parameter, linearly ramps it from start to end over
 * duration seconds.
 */
let linearRampToValue = (param, start, end, duration) => {
    param.cancelScheduledValues(context.currentTime);

    let points = 30;

    for (let i = 0; i <= points; i++) {
        let done = i / points;
        param.setValueAtTime(interpolate(start, end, done), context.currentTime + interpolate(0, duration, done));
    }
}

/**
 * Given an audio parameter, sets it to the given value.
 */
let setValue= (param, value) => {
    param.cancelScheduledValues(context.currentTime);
    param.setValueAtTime(value, context.currentTime);
}

/**
 * Attempts to start playing channel `c`.
 */
let start_playing = (c) => {

    let p = c.playing;

    if (p === null) {
        return;
    }

    if (p.started !== null) {
        return;
    }

    if (p.source === null) {
        return;
    }

    if (c.paused) {
        return;
    }

    context.resume();
    p.source.connect(c.destination);

    if (p.fadeout === null) {
        if (p.fadein > 0) {
            linearRampToValue(c.fade_volume.gain, c.fade_volume.gain.value, 1.0, p.fadein);
        } else {
            setValue(c.fade_volume.gain, 1.0);
        }
    }

    if (p.end >= 0) {
        p.source.start(0, p.start, p.end);
    } else {
        p.source.start(0, p.start);
    }

    if (p.fadeout !== null) {
        linearRampToValue(c.fade_volume.gain, c.fade_volume.gain.value, 0.0, p.fadeout);
        try {
            c.playing.source.stop(context.currentTime + p.fadeout);
        } catch (e) {
        }

    }

    setValue(c.relative_volume.gain, p.relative_volume);

    p.started = context.currentTime;
    p.started_once = true;
};


let pause_playing = (c) => {

    if (c.paused) {
        return;
    }

    c.paused = true;

    let p = c.playing;

    if (p === null) {
        return;
    }

    if (p.source === null) {
        return;
    }

    if (p.started === null) {
        return;
    }

    try {
        p.source.stop()
    } catch (e) {
    }

    p.start += (context.currentTime - p.started);
    p.started = null;
}


/**
 * Stops playing channel `c`.
 */
let stop_playing = (c) => {


    if (c.playing !== null && c.playing.source !== null) {
        try {
            c.playing.source.stop()
        } catch (e) {
        }

        c.playing.source.disconnect();
    }

    c.playing = c.queued;
    c.queued = null;
};


/**
 * Called when a channel ends naturally, to move things along.
 */
let on_end = (c) => {
    if (c.playing !== null && c.playing.started !== null) {
        stop_playing(c);
    }

    start_playing(c);
};

let video_start = (c) => {
    const p = c.playing;

    if (p === null) {
        return;
    }

    if (p.started !== null) {
        return;
    }

    // TODO Check if video has already been started?

    if (c.paused) {
        return;
    }

    if (c.video_el === null) {
        return;
    }

    //TODO? if (p.fadeout === null) {
    //TODO?     if (p.fadein > 0) {
    //TODO?         linearRampToValue(c.fade_volume.gain, c.fade_volume.gain.value, 1.0, p.fadein);
    //TODO?     } else {
    //TODO?         setValue(c.fade_volume.gain, 1.0);
    //TODO?     }
    //TODO? }

    c.video_el.src = p.url;
    c.video_el.play().then(() => {
        // TODO?
    }).catch((e) => {
        Module.print(`Cannot play ${p.name} (${e})`);
        throw e;
    });

    //TODO? if (p.fadeout !== null) {
    //TODO?     linearRampToValue(c.fade_volume.gain, c.fade_volume.gain.value, 0.0, p.fadeout);
    //TODO?     try {
    //TODO?         c.playing.source.stop(context.currentTime + p.fadeout);
    //TODO?     } catch (e) {
    //TODO?     }
    //TODO? 
    //TODO? }

    setValue(c.relative_volume.gain, p.relative_volume);

    p.started = c.video_el.currentTime;  // XXX Probably not ready yet
    p.started_once = true;
};

let video_pause = (c) => {
    if (p.started === null) {
        return;
    }

    c.paused = true;
    c.video_el?.pause();

    //TODO? p.start += (context.currentTime - p.started);
    p.started = null;
};

let video_stop = (c) => {
    if (c.video_el !== null) {
        c.video_el.src = '';
    }

    if (c.playing !== null) {
        const q = c.playing;
        const period = q.period_stats[1] > 0 ? q.period_stats[0] / q.period_stats[1] : 0;
        const fetch = q.fetch_stats[1] > 0 ? q.fetch_stats[0] / q.fetch_stats[1] : 0;
        const draw = q.draw_stats[1] > 0 ? q.draw_stats[0] / q.draw_stats[1] : 0;
        const blob = q.blob_stats[1] > 0 ? q.blob_stats[0] / q.blob_stats[1] : 0;
        const array = q.array_stats[1] > 0 ? q.array_stats[0] / q.array_stats[1] : 0;
        const file = q.file_stats[1] > 0 ? q.file_stats[0] / q.file_stats[1] : 0;
        console.debug(`period=${period} (${q.period_stats[1]})`,
            `fetch=${fetch} (${q.fetch_stats[1]})`,
            `draw=${draw} (${q.draw_stats[1]})`,
            `blob=${blob} (${q.blob_stats[1]})`,
            `array=${array} (${q.array_stats[1]})`,
            `file=${file} (${q.file_stats[1]})`);
    }

    c.playing = c.queued;
    c.queued = null;

    if (c.playing == null && c.video_el !== null) {
        // Channel is not used anymore, release resources
        c.media_source.disconnect();
        c.media_source = null;

        c.video_frame = null;
        c.canvas_ctx = null;

        c.canvas_el.parentElement.removeChild(c.canvas_el);
        c.canvas_el = null;

        c.video_el.parentElement.removeChild(c.video_el);
        c.video_el = null;
    }
};

let on_video_end = (c) => {
    if (c.playing !== null && c.playing.started !== null) {
        video_stop(c);
    }

    video_start(c);
};

renpyAudio = { };


renpyAudio.queue = (channel, file, name,  paused, fadein, tight, start, end, relative_volume) => {

    const c = get_channel(channel);

    if (file.startsWith('url:')) {
        const url = new URL(file.slice(4), window.location);
        if (!c.video) {
            throw new Error('URL resources are only supported for videos');
        }

        const q = {
             url: url,
             name : name,
             start : start,  // TODO?
             end : end,  // TODO?
             relative_volume : relative_volume,
             started : null,
             fadein : fadein,  // TODO?
             fadeout: null,  // TODO?
             tight : tight,  // TODO?
             started_once: false,

             period_stats: [0, 0],
             fetch_stats: [0, 0],
             draw_stats: [0, 0],
             blob_stats: [0, 0],
             array_stats: [0, 0],
             file_stats: [0, 0],
        };

        if (c.video_el === null) {
            c.video_el = document.createElement('video');
            c.video_el.style.display = 'none';
            document.body.appendChild(c.video_el);

            c.canvas_el = document.createElement('canvas');
            c.canvas_el.style.display = 'none';
            document.body.appendChild(c.canvas_el);

            c.canvas_ctx = c.canvas_el.getContext('2d', {willReadFrequently: USE_TGA,});

            c.video_el.addEventListener('loadedmetadata', function() {
                c.canvas_el.width = c.video_el.videoWidth;
                c.canvas_el.height = c.video_el.videoHeight;
                //c.canvas_el.width = c.video_el.videoWidth / 2;
                //c.canvas_el.height = c.video_el.videoHeight / 2;
                if (USE_TGA) {
                    c.tga_header.setUint16(12, c.canvas_el.width, true);  // Width, little endian
                    c.tga_header.setUint16(14, c.canvas_el.height, true);  // Height, little endian
                }
            });

            c.media_source = context.createMediaElementSource(c.video_el);
            c.media_source.connect(c.destination);

            if (USE_TGA) {
                // Pre-build TGA header
                c.tga_header = new DataView(new ArrayBuffer(18));
                c.tga_header.setUint8(0, 0);  // ID length (empty)
                c.tga_header.setUint8(1, 0);  // Color map type (none)
                c.tga_header.setUint8(2, 2);  // Image type (uncompressed true-color image)
                c.tga_header.setUint32(3, 0);  // Color map (ignored)
                c.tga_header.setUint8(7, 0);  // Color map (ignored)
                c.tga_header.setUint32(8, 0);  // X and Y origin (0, 0)
                // c.tga_header.setUint16(12, width, true);  // Width, little endian
                // c.tga_header.setUint16(14, height, true);  // Height, little endian
                c.tga_header.setUint8(16, 32);  // Pixels depth (32)
                c.tga_header.setUint8(17, 0x28);  // Flags (3-0: alpha channel width, 5: top to bottom)
            }

            let fetch_timer = null;
            let fetch_busy = false;
            function fetch_frame() {
                const start = performance.now();

                if (fetch_busy) {
                    // Make sure there is only 1 fetch timer
                    return;
                }
                fetch_timer = null

                if (c.playing === null || c.paused) {
                    return;
                }

                fetch_busy = true;

                const q = c.playing;
                if (q.last_fetch !== undefined) {
                    q.period_stats[0] += start - q.last_fetch;
                    q.period_stats[1]++;
                }
                q.last_fetch = start;

                c.canvas_ctx.drawImage(c.video_el, 0, 0);
                //c.canvas_ctx.drawImage(c.video_el, 0, 0, c.canvas_el.width, c.canvas_el.height);

                let prev_ts = start, cur_ts = performance.now();
                q.draw_stats[0] += cur_ts - prev_ts;
                q.draw_stats[1]++;

                if (USE_TGA) {
                    c.video_frame = c.canvas_ctx;

                    q.fetch_stats[0] += cur_ts - start;
                    q.fetch_stats[1]++;

                    fetch_busy = false;
                    // Assuming 30 FPS
                    let next = 1000 / 30.0 - (start - performance.now());
                    if (next <= 0) {
                        // Browser is struggling to render video, give it some rest
                        next = 10;
                    }
                    fetch_timer = setTimeout(fetch_frame, next);

                } else {  // JPG or PNG (both slower than TGA because of compression)
                    c.canvas_el.toBlob((blob) => {
                        prev_ts = cur_ts;
                        cur_ts = performance.now();
                        q.blob_stats[0] += cur_ts - prev_ts;
                        q.blob_stats[1]++;

                        blob.arrayBuffer().then((buffer) => {
                            c.video_frame = new Uint8Array(buffer);

                            prev_ts = cur_ts;
                            cur_ts = performance.now();
                            q.array_stats[0] += cur_ts - prev_ts;
                            q.array_stats[1]++;
                            q.fetch_stats[0] += cur_ts - start;
                            q.fetch_stats[1]++;

                            fetch_busy = false;
                            // Assuming 30 FPS
                            let next = 1000 / 30.0 - (start - performance.now());
                            if (next <= 0) {
                                // Browser is struggling to render video, give it some rest
                                next = 10;
                            }
                            fetch_timer = setTimeout(fetch_frame, next);
                        });
                    // }, 'image/png');
                    }, 'image/jpeg');
                }
            }

            c.video_el.addEventListener('ended', (e) => {
                clearTimeout(fetch_timer);
                fetch_timer = null;
                on_video_end(c);
            });

            c.video_el.addEventListener('paused', (e) => {
                clearTimeout(fetch_timer);
                fetch_timer = null;
            });

            c.video_el.addEventListener('playing', function() {
                clearTimeout(fetch_timer);
                fetch_timer = null;
                fetch_frame();
            });
        }

        if (c.playing === null) {
            c.playing = q;
            c.paused = paused;
        } else {
            c.queued = q;
        }

        video_start(c);
        return;
    }

    const q = {
        source : null,
        buffer : null,
        name : name,
        start : start,
        end : end,
        relative_volume : relative_volume,
        started : null,
        fadein : fadein,
        fadeout: null,
        tight : tight,
        started_once : false,
        file: file,
    };

    function reuseBuffer(c) {
        // We can re-use the audio buffer, but not the buffer source
        c.queued.buffer = c.playing.buffer;
        c.queued.source = context.createBufferSource();
        c.queued.source.buffer = c.playing.buffer;
        c.queued.source.onended = () => { on_end(c); };

        start_playing(c);
    }

    if (c.playing === null) {
        c.playing = q;
        c.paused = paused;
    } else {
        c.queued = q;
        if (c.playing.file === file) {
            // Same file, re-use the data to reduce memory and CPU footprint
            if (c.playing.buffer !== null) {
                reuseBuffer(c);
            } else {
                // Not ready yet, wait for decodeAudioData() to complete
            }

            return;
        }
    }

    const array = FS.readFile(file);
    context.decodeAudioData(array.buffer, (buffer) => {

        const source = context.createBufferSource();
        source.buffer = buffer;
        source.onended = () => { on_end(c); };

        q.source = source;
        q.buffer = buffer;

        start_playing(c);

        if (c.playing === q && c.queued !== null && c.queued.file === q.file) {
            // Same file, re-use the data to reduce memory and CPU footprint
            reuseBuffer(c);
        }
    }, () => {
        console.log(`The audio data in ${file} could not be decoded. The file format may not be supported by this browser.`);
    });
};


renpyAudio.stop = (channel) => {
    let c = get_channel(channel);
    c.queued = null;
    if (c.video) {
        video_stop(c);
    } else {
        stop_playing(c);
    }
};


renpyAudio.dequeue = (channel, even_tight) => {

    let c = get_channel(channel);

    if (c.queued && c.queued.tight && !even_tight) {
        return;
    }

    c.queued = null;
};


renpyAudio.fadeout = (channel, delay) => {

    let c = get_channel(channel);
    if (c.playing == null || c.playing.started == null) {
        c.playing = c.queued;
        c.queued = null;
        start_playing(c);
        return;
    }

    let p = c.playing;

    linearRampToValue(c.fade_volume.gain, c.fade_volume.gain.value, 0.0, delay);

    if (c.video) {
        // TODO?
        return;
    }

    try {
        p.source.stop(context.currentTime + delay);
    } catch (e) {
    }

    if (c.queued === null || !c.queued.tight) {
        return;
    }

    let remaining = delay + context.currentTime - p.started - p.buffer.duration;

    if (remaining > 0 && c.queued) {
        c.queued.fadeout = remaining;
    } else {
        c.queued = null;
    }

};

renpyAudio.queue_depth = (channel) => {
    let rv = 0;
    let c = get_channel(channel);

    if (c.playing !== null) {
        rv += 1;
    }

    if (c.queued !== null) {
        rv += 1;
    }

    return rv;
};


renpyAudio.playing_name = (channel) => {
    let c = get_channel(channel);

    if (c.playing !== null) {
        return c.playing.name;
    }

    return "";
};


renpyAudio.pause = (channel) => {

    let c = get_channel(channel);
    if (c.video) {
        video_pause(c);
    } else {
        pause_playing(c);
    }
};


renpyAudio.unpause = (channel) => {
    let c = get_channel(channel);
    if (c.video) {
        video_start(c);
    } else {
        start_playing(c);
    }
};


renpyAudio.unpauseAllAtStart = () => {
    for (let i of Object.entries(channels)) {
        const c = i[1];
        if (c.playing && ! c.playing.started_once && c.paused) {
            c.paused = false;
            if (c.video) {
                video_start(c);
            } else {
                start_playing(c);
            }
        }
    }
};


renpyAudio.get_pos = (channel) => {

    let c = get_channel(channel);
    let p = c.playing;

    if (p === null) {
        return 0;
    }

    let rv = p.start;

    if (p.started !== null) {
        if (c.video) {
            rv += c.video_el.currentTime - p.started;
        } else {
            rv += (context.currentTime - p.started);
        }
    }

    return rv * 1000;
};


renpyAudio.get_duration = (channel) => {
    let c = get_channel(channel);
    let p = c.playing;

    if (c.video) {
        if (c.video_el) {
            const duration = c.video_el.duration;
            if (Number.isFinite(duration)) {
                return duration * 1000;
            }
        }
    } else if (p.buffer) {
        return p.buffer.duration * 1000;
    }

    return 0;
};


renpyAudio.set_volume = (channel, volume) => {
    let c = get_channel(channel);
    setValue(c.primary_volume.gain, volume);
};


renpyAudio.set_secondary_volume = (channel, volume, delay) => {
    let c = get_channel(channel);
    let control = c.secondary_volume.gain;

    linearRampToValue(control, control.value, volume, delay);
};


renpyAudio.get_volume = (channel) => {
    const c = get_channel(channel);
    return c.primary_volume.gain * 1000;
};


renpyAudio.set_pan = (channel, pan, delay) => {

    let c = get_channel(channel);
    let control = c.stereo_pan.pan;

    linearRampToValue(control, control.value, pan, delay);
};

renpyAudio.tts = (s) => {
    console.log("tts: " + s);

    let u = new SpeechSynthesisUtterance(s);
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
};

renpyAudio.can_play_types = (l) => {
    let a = document.createElement("audio");

    for (let i of l) {
        if (!a.canPlayType(i)) {
            console.log("Can't play", i);
            return 0;
        } else {
            console.log("Can play", i);
        }
    }

    return 1;
}

renpyAudio.set_video = (channel, video) => {
    const c = get_channel(channel);
    c.video = !!video;
}

renpyAudio.video_ready = (channel) => {
    const c = get_channel(channel);
    return c.video && c.video_frame !== null;
}

renpyAudio.read_video = (channel) => {
    const c = get_channel(channel);
    if (c.video && c.video_frame !== null) {
        const start = performance.now();
        const q = c.playing;

        // Store the frame to a MEMFS file for RenPy to access it
        const ext = USE_TGA ? '.tga' : '.jpg';
        const filename = 'video_frame_' + c.chan_id + ext;
        const stream = FS.open(filename, 'w+');
        if (USE_TGA) {
            const imageData = c.video_frame.getImageData(0, 0, c.canvas_el.width, c.canvas_el.height);
            FS.write(stream, new Uint8Array(c.tga_header.buffer), 0, c.tga_header.byteLength, 0);
            FS.write(stream, imageData.data, 0, imageData.data.length, c.tga_header.byteLength);
        } else {
            FS.write(stream, c.video_frame, 0, c.video_frame.length, 0);
        }
        FS.close(stream);
        c.video_frame = null;

        if (q !== null) {
            q.file_stats[0] += performance.now() - start;
            q.file_stats[1]++;
        }

        return filename;
    }
    return '';
}

if (context.state == "suspended") {
    let unlockContext = () => {
        context.resume().then(() => {
            document.body.removeEventListener('click', unlockContext, true);
            document.body.removeEventListener('touchend', unlockContext, true);
            document.body.removeEventListener('touchstart', unlockContext, true);
        });
    };

    document.body.addEventListener('click', unlockContext, true);
    document.body.addEventListener('touchend', unlockContext, true);
    document.body.addEventListener('touchstart', unlockContext, true);
}
