import mpv
import sounddevice as sd
import numpy as np
import time
import json
import threading

# Load playlist
with open('playlist.json') as f:
    playlist = json.load(f)

player = mpv.MPV(vo='gpu-next', gpu_api='auto', fullscreen=True, loop=True)

current_index = 0
current_shader = None

def load_video(item):
    global current_shader
    player.play(item['video'])
    if current_shader:
        player.command('change-list', 'glsl-shaders', 'remove', current_shader)
    if 'shader' in item and item['shader']:
        shader_path = f"shaders/{item['shader']}.glsl"
        player.command('change-list', 'glsl-shaders', 'append', shader_path)
        current_shader = shader_path

# Simple audio reactivity thread
def audio_reactivity():
    device = None  # set to your Zoom F1 device index/name
    with sd.InputStream(samplerate=44100, channels=1, dtype='float32', device=device) as stream:
        while True:
            data, _ = stream.read(2048)
            volume = np.abs(data).mean()
            # Map volume to shader parameter (example)
            if current_shader:
                intensity = min(1.0, volume * 8)  # tune this multiplier
                player.command('set', 'glsl-shader-opts', f'intensity={intensity}')
            time.sleep(0.03)

# Start audio thread
threading.Thread(target=audio_reactivity, daemon=True).start()

# Load first video
load_video(playlist[0])

print("Press Ctrl+C to quit. Test your Zoom F1 now!")
mpv.MPV.wait_for_property(player, 'idle-active', lambda p: False)  # keep running
