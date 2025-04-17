from flask import Flask, request, render_template, redirect, url_for, session
import openai
import os
import re
from dotenv import load_dotenv
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = "supersecreto"
load_dotenv()

openai.api_key = os.environ.get("OPENAI_API_KEY", "MISSING_KEY")

USUARIOS = {
    "admin": "adn2025",
    "calidadadn": "ADN2025*",
    "CALIDAD1": "calidadADN20205*"
}

HISTORIAL_FILE = "historial.json"

def guardar_en_historial(usuario, score, resumen):
    fila = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "usuario": usuario,
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

    if request.method == "POST":
        audio_file = request.files["audio"]
        audio_path = "static/audio.wav"
        audio_file.save(audio_path)

        transcript_data = openai.Audio.transcribe(
            "whisper-1",
            open(audio_path, "rb"),
            response_format="verbose_json"
        )

        segments = transcript_data["segments"]
        full_text = " ".join([s["text"] for s in segments])

        prompt = f"""Eres un auditor experto en validación de ventas de telefonía móvil. Evalúa la siguiente transcripción real de una llamada entre un agente y un cliente. No inventes contenido. Solo responde con base en lo que está presente en la transcripción.

1. Evalúa si se mencionaron claramente los siguientes puntos. Responde "✅ Cumple" o "❌ No cumple":
- Permanencia mínima de 3 meses
- Costo de $150 mensual y penalización de $280 si no paga antes del corte
- Proceso de activación (insertar chip si es número nuevo)
- Portabilidad: debe marcar al 3396901234 opción 2 y tiene 7 días naturales para hacerla desde que recibe el chip
- Número correcto para activación: 3396901234 opción 2
- Validación de que es mayor de edad o titular
- Confirmación de condiciones: $150, red 4.5G, cobertura
- Tiempo de entrega del chip: 7 días hábiles
- Repetición de condiciones del servicio
- Repetición del tiempo estimado de entrega

2. Calcula un score final en porcentaje (cada punto vale 10%).

3. Observaciones claras sobre lo que faltó.

Transcripción real:
{full_text}
""" 

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

        guardar_en_historial(session["usuario"], score, resultado)
        return render_template("index.html", segments=segments, resultado=resultado)

    return render_template("index.html", segments=None, resultado=None)

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
        if usuario in USUARIOS and USUARIOS[usuario] == clave:
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