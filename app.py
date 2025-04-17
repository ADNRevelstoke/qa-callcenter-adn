from flask import Flask, request, render_template
import openai
import os
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

openai.api_key = os.environ.get("OPENAI_API_KEY", "MISSING_KEY")

def construir_prompt(transcripcion):
    return f"""Eres un auditor experto en validación de ventas de telefonía móvil. Evalúa esta transcripción y responde en el siguiente formato:

1. Revisa si el agente menciona claramente los siguientes puntos durante la llamada. Para cada uno, responde "✅ Cumple" o "❌ No cumple":
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

3. Observaciones: breve explicación de cualquier omisión.

4. Reestructura la transcripción en formato:
Agente: ...
Cliente: ...
"""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        audio_file = request.files["audio"]
        audio_path = "temp.wav"
        audio_file.save(audio_path)

        transcript = openai.Audio.transcribe("whisper-1", open(audio_path, "rb"))
        transcripcion = transcript["text"]

        prompt = construir_prompt(transcripcion)
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Eres un evaluador automatizado de calidad en llamadas de ventas de telefonía móvil."},
                {"role": "user", "content": prompt}
            ]
        )

        resultado = response.choices[0].message["content"]
        return render_template("index.html", transcript=transcripcion, resultado=resultado)

    return render_template("index.html", transcript=None, resultado=None)
@app.route("/check-api")
def check_api():
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and api_key.startswith("sk-"):
        return "✅ API key cargada correctamente."
    else:
        return "❌ No se detectó la API key en el entorno."
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))