
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

    sucursal_contrato = ""

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

        # Extraer sucursal y contrato
        match = re.search(r"sucursal\s*(\d+)[^\d]+(contrato\s*)?(\d+)", full_text, re.IGNORECASE)
        if match:
            sucursal_contrato = f"{match.group(1)}-{match.group(3)}"

        prompt = f"""Eres un auditor experto en validación de ventas de telefonía móvil. Vas a evaluar la transcripción de una llamada entre un asesor y un cliente. Tu análisis debe centrarse únicamente en la primera parte de la conversación, hasta el momento en que el asesor menciona que la llamada será transferida al área de validación o calidad. Ignora todo lo que ocurra después de esa transferencia.
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
  o Si aplica portabilidad, el asesor debe mencionar que se cuenta con 7 días naturales a partir de recibir el chip para realizar el proceso.
5. Validación de mayoría de edad o titularidad
  o El asesor debe verificar si la persona que contrata es mayor de edad o titular, o bien, si tiene autorización para contratar por el titular.
6. Confirmación de condiciones técnicas del servicio
  o Debe mencionarse que el servicio cuenta con cobertura nacional y opera en la red 4.5G (también se acepta: 4.5 o 4.5LTE).
7. Tiempo estimado de entrega del chip
  o El asesor debe indicar que el chip será entregado en un máximo de 7 días hábiles. También son válidas frases como “de 5 a 7 días hábiles”.

Transcripción real:
{{full_text}}
""".replace("{{full_text}}", full_text)

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Eres un auditor experto en validación de ventas de telefonía móvil. Solo debes evaluar la parte de la llamada anterior a la transferencia a validación o calidad, ignorando todo lo posterior."},
                {"role": "user", "content": prompt}
            ]
        )

        resultado = response.choices[0].message["content"]
        score_match = re.search(r"(\d{{1,3}})%", resultado)
        score = score_match.group(1) + "%" if score_match else "N/A"

        guardar_en_historial(session["usuario"], score, resultado)
        return render_template("index.html", segments=segments, resultado=resultado, sucursal_contrato=sucursal_contrato)

    return render_template("index.html", segments=None, resultado=None, sucursal_contrato=None)

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
