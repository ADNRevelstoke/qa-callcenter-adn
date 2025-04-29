
from flask import Flask, request, render_template, redirect, url_for, session
import openai
import os
import re
import json
from dotenv import load_dotenv
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.secret_key = "supersecreto"
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

def cargar_usuarios_desde_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials_info = json.loads(os.environ["GOOGLE_SHEETS_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(os.environ["SHEET_ID"]).worksheet("Lista")
    data = sheet.get_all_records()
    return {row["NombreUsuario"]: {"password": row["Password"], "nombre": row["NombreCompleto"], "rol": row["Rol"]} for row in data}

USUARIOS = cargar_usuarios_desde_sheets()
HISTORIAL_FILE = "historial.json"

def guardar_en_historial(usuario, ejecutivo, score, resumen):
    fila = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "evaluador": usuario,
        "evaluado": ejecutivo,
        "score": score,
        "resumen": resumen.strip()
    }
    try:
        with open(HISTORIAL_FILE, "r") as f:
            historial = json.load(f)
    except FileNotFoundError:
        historial = []
    historial.insert(0, fila)
    with open(HISTORIAL_FILE, "w") as f:
        json.dump(historial, f, indent=2)

@app.route("/", methods=["GET", "POST"])
def index():
    if "usuario" not in session:
        return redirect(url_for("login"))
    if USUARIOS[session["usuario"]]["rol"] == "ejecutivo":
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        ejecutivo = request.form.get("evaluado")
        if not ejecutivo:
            return "Debe seleccionar al ejecutivo evaluado", 400

        audio_file = request.files["audio"]
        audio_path = "static/audio.wav"
        audio_file.save(audio_path)

        transcript_data = openai.Audio.transcribe(
            "whisper-1", open(audio_path, "rb"), response_format="verbose_json"
        )
        segments = transcript_data["segments"]
        # Limpieza de saltos de línea innecesarios
        for s in segments:
            s["text"] = s["text"].replace("\n", " ").strip()
            
        full_text = " ".join([s["text"] for s in segments])

        prompt = f'''Eres un auditor experto en validación de ventas de telefonía móvil. Vas a evaluar la transcripción de una llamada entre un asesor y un cliente. Tu análisis debe centrarse únicamente en la primera parte de la conversación, hasta el momento en que el asesor menciona que la llamada será transferida al área de validación o calidad. Ignora todo lo que ocurra después de esa transferencia.
No infieras información que no esté presente en la transcripción. Solo responde en función del contenido textual que aparece.
Por cada uno de los siguientes criterios, responde únicamente con una de estas opciones:
• ✅ Cumple
• ⚠️ Cumple Parcialmente
• ❌ No cumple

Criterios de Evaluación
1. Permanencia mínima de 3 meses
  o Evalúa si el asesor menciona que el servicio contratado requiere una permanencia mínima de tres meses.
  o Debe indicarlo explícitamente, con sinónimos como: mínimo, al menos, obligatorio mantenerlo tres meses, etc.
2. Mención clara del costo del paquete ($150, $280 o $330)
  o El asesor debe indicar el precio del paquete de forma clara. Puede omitir la palabra “pesos”, pero el monto debe mencionarse de forma inequívoca.
  o Evalúa también si explica correctamente las características correspondientes a cada plan:
    - $150: 7 GB de navegación al mes, redes sociales ilimitadas, llamadas y mensajes ilimitados.
    - $280: Todo ilimitado. Si el cliente pregunta si puede compartir internet, el asesor debe aclarar que no. Si el cliente no pregunta, este punto no es obligatorio.
    - $330: Todo ilimitado y sí se puede compartir internet. Solo debe mencionarse si se está comparando con el de $280.
  o Si el cliente pregunta qué redes sociales están incluidas, el asesor debe decir exactamente estas 7: Facebook, Instagram, X (o Twitter), WhatsApp, Messenger, Snapchat y Telegram.
3. Proceso de activación del chip
  o Si el cliente solicita número nuevo, el asesor debe explicar que solo necesita insertar (o sinónimos: ingresar, colocar, introducir, meter) el chip en el teléfono.
  o Si el cliente desea conservar su número (portabilidad), el asesor debe indicar que debe primero llamar al 3396901234 opción 2 antes de insertar el chip.
  o Si el cliente dice que no puede anotar, el asesor debe mencionar que esta información está disponible en la página de Megamóvil.
  o El asesor debe mencionar que en esa llamada el cliente debe decir que quiere hacer la portabilidad y seguir instrucciones del ejecutivo.
4. Plazo para realizar portabilidad: 7 días naturales
5. Validación de mayoría de edad o titularidad
6. Confirmación de condiciones técnicas del servicio
7. Tiempo estimado de entrega del chip
8. Evaluar que el asesor no mencione las palabras "probar gratis" o "cancelar", si menciona alguna de esas palabras, no cumple este criterio y señalalo. Detecta solo si fue el asesor quien menciono estas palabras ya que si fue el cliente, el rubro no debe ser penalizado.

Tu respuesta debe tener este formato:

1. [TÍTULO DEL RUBRO]: ✅/⚠️/❌
...
8. [TÍTULO DEL RUBRO]: ✅/⚠️/❌

Observaciones:
- [TÍTULO DEL RUBRO]: Explica por qué no cumple o cumple parcialmente.
...

Transcripción real:
{full_text}
'''

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Eres un auditor automatizado de calidad en llamadas."},
                {"role": "user", "content": prompt}
            ]
        )

        resultado = response.choices[0].message["content"]
        score_match = re.search(r"(\d{1,3})%", resultado)
        score = score_match.group(1) + "%" if score_match else "N/A"

        guardar_en_historial(session["usuario"], ejecutivo, score, resultado)
        return render_template("index.html", segments=segments, resultado=resultado, usuarios=get_ejecutivos())

    return render_template("index.html", segments=None, resultado=None, usuarios=get_ejecutivos())

def get_ejecutivos():
    return [v["nombre"] for v in USUARIOS.values() if v["rol"] == "ejecutivo"]

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session:
        return redirect(url_for("login"))
    nombre = USUARIOS[session["usuario"]]["nombre"]
    try:
        with open(HISTORIAL_FILE, "r") as f:
            historial = json.load(f)
    except FileNotFoundError:
        historial = []
    personales = [h for h in historial if h["evaluado"] == nombre]
    return render_template("dashboard.html", historial=personales, nombre=nombre)

@app.route("/historial")
def historial():
    if "usuario" not in session:
        return redirect(url_for("login"))
    with open(HISTORIAL_FILE, "r") as f:
        historial = json.load(f)
    return render_template("historial.html", historial=historial)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form["username"]
        clave = request.form["password"]
        if usuario in USUARIOS and USUARIOS[usuario]["password"] == clave:
            session["usuario"] = usuario
            return redirect(url_for("index"))
        else:
            error = "Usuario o contraseña incorrectos"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
