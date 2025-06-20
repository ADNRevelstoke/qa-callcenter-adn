from flask import Flask, request, render_template, redirect, url_for, session
import openai
import os
import re
import json
from dotenv import load_dotenv
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, auth, firestore

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "clave-predeterminada")

# Inicializa Firebase solo una vez
if not firebase_admin._apps:
    cred = credentials.Certificate(json.loads(os.environ["FIREBASE_CREDENTIALS_JSON"]))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

# Carga clave OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

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

    if request.method == "POST":
        ejecutivo = request.form.get("ejecutivo", "SIN NOMBRE")
        audio_file = request.files["audio"]
        audio_path = "static/audio.wav"
        audio_file.save(audio_path)

        transcript_data = openai.Audio.transcribe(
            "whisper-1", open(audio_path, "rb"), response_format="verbose_json"
        )
        segments = transcript_data["segments"]

        for s in segments:
            s["text"] = s["text"].replace("\n", " ").strip()

        full_text = " ".join([s["text"] for s in segments])

        prompt = f'''Asume el rol de un analista de calidad y evalúa la siguiente transcripción de una llamada entre un asesor y un cliente. 

Tu tarea consiste en calificar con un ✅ si el asesor cumple correctamente con cada punto y con una ❌ si no lo menciona. Debes analizar únicamente la parte de la conversación **previa a la frase**: "del departamento de calidad", o detectando que el asesor esta transfiriendo la llamada a un validador, porque esa etapa de la llamada no debe ser calificada. Una vez que dicha frase o escenario de transferencia a validador, equipo de validacion, equipo de calidad, etc,  aparece, debes detener la evaluación y no considerar nada de lo que ocurra después.

Evalúa los siguientes criterios:

1. **Red y cobertura**
   - El asesor debe mencionar que el servicio cuenta con cobertura nacional y/o red 4.5G LTE.
   - Si lo menciona, califica como ✅.
   - Si no lo menciona, califica como ❌.
   - Únicamente si el cliente pregunta directamente por cobertura, señal o red, el asesor puede responder que existe un margen de error. Si lo menciona sin que se le pregunte, también es válido y debe calificarse como ✅.

2. **Llamadas, mensajes, redes sociales y 3 GB**
   - Se debe mencionar en algún momento que el paquete incluye llamadas, mensajes, redes sociales ilimitadas y 3 GB de navegación. Es valido si el asesor menciona palabras articuladas para referirse a las redes sociales, como por ejemplo "X" "EX" o "Twitter" es lo mismo y es válido. 
   - Si lo menciona, califica como ✅.
   - Si no lo menciona, califica como ❌.

3. **Doble de gigabytes por portabilidad**
   - El asesor debe decir que si el cliente conserva su número (portabilidad), obtiene el doble de gigabytes durante los primeros 12 meses.
   - Si lo menciona, califica como ✅.
   - Si no lo menciona, califica como ❌.

4. **Costo del paquete**
   - Se debe mencionar que el costo del paquete es de $100, $200 o $300.
   - Si menciona alguno de estos precios, califica como ✅.
   - Si no menciona ningún precio, califica como ❌.

5. **Permanencia de 3 meses**
   - Debe decirse que el servicio tiene una permanencia mínima de 3 meses.
   - Si lo menciona o usa sinónimos como "obligatorio 3 meses", califica como ✅.
   - Si no lo menciona, califica como ❌.

6. **Tiempo de entrega: 7 días hábiles**
   - El asesor debe indicar que el chip se entrega en 7 días hábiles.
   - Si lo menciona, califica como ✅.
   - Si no lo menciona, califica como ❌.

7. **Número para portabilidad**
   - El asesor debe mencionar el número 3396901234 como parte del proceso de portabilidad. Por favor considera que el asesor puede mencionar el numero de manera continua o con equivalencias como 33 96 90 12 34, o numero por numero y cualquiera de esos escenarios es valido. 
   - Si lo menciona, califica como ✅.
   - Si no lo menciona, califica como ❌.

8. **Plazo de activación: 7 días naturales**
   - Debe indicarse que hay 7 días o 7 días naturales para realizar la portabilidad o marcar.
   - Si lo menciona, califica como ✅.
   - Si no lo menciona, califica como ❌.

9. **10 Mbps adicionales**
   - El asesor debe mencionar que el cliente recibe 10 megabits o 10 megas adicionales a su servicio de internet en casa por conceptos que pueden ser portabilidad y/o contratación del servicio, osea en total pueden sumar 20 megas, con que el asesor mencione uno u otro, es un rubro positivo, si no menciona ninguno u omite alguno, no lo penalices solo observalo en las notas.
   - Si lo menciona, califica como ✅.
   - Si no lo menciona, califica como ❌.

10. **Recargas**
   - Se debe preguntar al cliente si actualmente usa recargas.
   - Si el cliente responde que sí, y el asesor reacciona de forma adecuada (positiva), califica como ✅.
   - Si no se pregunta o no se menciona el tema, califica como ❌.

11. **Palabras Prohibidas*
   - El asesor tiene prohibido mencionar explicitamente las palabras: "probar", "cancelar" y "gratis" por lo que mencionarlas en cualquier punto de la llamada, se debe penalizar negativamente el rubro.
   - Si la o las menciona cualquiera de esas palabras, califica como ❌.
   - Si no las menciona, califica como ✅.


Tu respuesta debe tener este formato:

1. [Nombre del criterio]: ✅/❌  
2. [Nombre del criterio]: ✅/❌  
...  
11. [Nombre del criterio]: ✅/❌

Después, proporciona una sección de **observaciones** explicando brevemente las razones de los ❌ en caso de que existan.
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

        db.collection("evaluaciones").add({
            "fecha": datetime.now().isoformat(),
            "evaluador": session.get("usuario", "desconocido"),
            "evaluado": ejecutivo,
            "score": score,
            "resumen": resultado
        })
        return render_template("index.html", segments=segments, resultado=resultado, usuarios=get_ejecutivos())

    return render_template("index.html", segments=None, resultado=None, usuarios=get_ejecutivos())

def get_ejecutivos():
    docs = db.collection("usuarios").where("rol", "==", "asesor").stream()
    return [doc.to_dict().get("nombre", "") for doc in docs]

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session:
        return redirect(url_for("login"))

    nombre = session["usuario"]

    docs = db.collection("evaluaciones").where("evaluado", "==", nombre).order_by("fecha", direction=firestore.Query.DESCENDING).stream()

    historial = []
    scores = []
    fechas = []

    for doc in docs:
        data = doc.to_dict()
        historial.append(data)
        scores.append(int(data.get("score", "0").replace("%", "")))
        fechas.append(data.get("fecha", "")[:10])

    promedio_asesor = sum(scores) / len(scores) if scores else 0

    all_docs = db.collection("evaluaciones").stream()
    promedios_por_asesor = {}

    for doc in all_docs:
        d = doc.to_dict()
        ev = d.get("evaluado", "")
        s = int(d.get("score", "0").replace("%", ""))
        if ev not in promedios_por_asesor:
            promedios_por_asesor[ev] = []
        promedios_por_asesor[ev].append(s)

    ranking = sorted(
        [(k, sum(v) / len(v)) for k, v in promedios_por_asesor.items()],
        key=lambda x: x[1],
        reverse=True
    )

    posicion = next((i + 1 for i, r in enumerate(ranking) if r[0] == nombre), None)

    prompt = f"""
Eres un coach experto en evaluación de calidad en call centers. Con base en las siguientes evaluaciones previas del asesor '{nombre}', genera un resumen de retroalimentación constructiva. Menciona fortalezas, áreas a mejorar y un consejo accionable.

Evaluaciones previas:
{[h['resumen'] for h in historial[:5]]}  # máximo 5 más recientes
"""

    retro_ai = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Eres un experto en evaluación de calidad."},
            {"role": "user", "content": prompt}
        ]
    ).choices[0].message['content']

    return render_template("dashboard.html",
        nombre=nombre,
        usuario=nombre,
        historial=historial,
        fechas=fechas,
        scores=scores,
        promedio=int(promedio_asesor),
        posicion=posicion,
        ranking=[{"usuario": r[0], "score": int(r[1])} for r in ranking],
        retro_ai=retro_ai
    )

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

        try:
            import requests
            firebase_api_key = os.environ.get("FIREBASE_API_KEY")
            payload = {
                "email": usuario,
                "password": clave,
                "returnSecureToken": True
            }
            r = requests.post(
                f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}",
                json=payload
            )

            if r.status_code != 200:
                error = "Usuario o contraseña incorrectos"
                return render_template("login.html", error=error)

            doc_ref = db.collection("usuarios").document(usuario)
            doc = doc_ref.get()
            if doc.exists:
                rol = doc.to_dict().get("rol", "")
                session["usuario"] = usuario
                session["rol"] = rol

                if rol == "asesor":
                    return redirect(url_for("dashboard"))
                else:
                    return redirect(url_for("index"))
            else:
                error = "Usuario sin rol asignado en base de datos"

        except Exception as e:
            error = "Error de autenticación: " + str(e)

    return render_template("login.html", error=error)

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    mensaje = None
    if request.method == "POST":
        email = request.form["email"]
        try:
            firebase_api_key = os.environ.get("FIREBASE_API_KEY")
            import requests
            payload = {"requestType": "PASSWORD_RESET", "email": email}
            r = requests.post(
                f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={firebase_api_key}",
                json=payload,
            )
            if r.status_code == 200:
                mensaje = "
