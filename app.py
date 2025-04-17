from flask import Flask, request, render_template, redirect, url_for, session
import openai
import os
import re
from dotenv import load_dotenv

app = Flask(__name__)
app.secret_key = "supersecreto"
load_dotenv()

openai.api_key = os.environ.get("OPENAI_API_KEY", "MISSING_KEY")

USUARIOS = {
    "admin": "adn2025",
    "calidadadn": "ADN2025*"
}

def construir_prompt(transcripcion):
    return f"""Eres un auditor experto en validación de ventas de telefonía móvil. Evalúa la siguiente transcripción real de una llamada entre un agente y un cliente. No inventes contenido. Solo responde con base en lo que está presente en la transcripción.

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
{transcripcion}
"""


@app.route("/", methods=["GET", "POST"])
def index():
    if "usuario" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        audio_file = request.files["audio"]
        audio_path = "static/audio.wav"
        audio_file.save(audio_path)

        transcript = openai.Audio.transcribe(
            "whisper-1",
            open(audio_path, "rb"),
            response_format="verbose_json"
        )

        segments = transcript["segments"]
        full_text = " ".join([seg["text"] for seg in segments])
        prompt = construir_prompt(full_text)

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Eres un auditor automatizado de calidad en llamadas."},
                {"role": "user", "content": prompt}
            ]
        )

        resultado = response.choices[0].message["content"]
        return render_template("index.html", segments=segments, resultado=resultado, transcript=full_text)

    return render_template("index.html", segments=None, resultado=None, transcript=None)

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