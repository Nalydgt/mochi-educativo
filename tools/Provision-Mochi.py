"""USB provisioning; credentials are never printed or written to a file."""
import argparse
import getpass
import json
import time
import serial

parser = argparse.ArgumentParser()
parser.add_argument("--port", default="COM3")
args = parser.parse_args()
settings = {
    "ssid": input("Nombre de tu Wi-Fi de 2,4 GHz: ").strip(),
    "password": getpass.getpass("Contrasena Wi-Fi: "),
    "server_url": input("URL HTTPS de la pasarela: ").strip().rstrip("/"),
    "token": getpass.getpass("Clave MOCHI_TOKEN de la pasarela: ").strip(),
}
if len(settings["ssid"].encode()) > 32 or not settings["ssid"]:
    raise SystemExit("El nombre Wi-Fi debe ocupar entre 1 y 32 bytes.")
if len(settings["password"].encode()) > 64 or (settings["password"] and len(settings["password"].encode()) < 8):
    raise SystemExit("La contrasena debe tener entre 8 y 64 bytes, o estar vacia para una red abierta.")
if len(settings["token"]) < 32:
    raise SystemExit("MOCHI_TOKEN necesita al menos 32 caracteres.")
message = ("@config " + json.dumps(settings, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
if len(message) >= 1200:
    raise SystemExit("La configuracion es demasiado larga para el dispositivo.")
port = serial.Serial(port=None, baudrate=115200, timeout=.3)
port.dtr = port.rts = False
port.port = args.port
with port:
    time.sleep(.5)
    port.reset_input_buffer()
    port.write(message)
    port.flush()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        line = port.readline()
        if b"@mochi_config ok" in line:
            print("Configuracion guardada. Mochi se reiniciara y conectara al Wi-Fi.")
            break
        if b"@mochi_config invalid" in line:
            raise SystemExit("Mochi rechazo la configuracion. Revisa la URL, las longitudes y la clave.")
    else:
        raise SystemExit("No se recibio confirmacion. Cierra cualquier monitor serie y vuelve a intentarlo.")
