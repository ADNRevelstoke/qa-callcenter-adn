import csv
import firebase_admin
from firebase_admin import credentials, firestore

# Inicializa Firebase
cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

with open("asesores.csv", newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        # Maneja el posible BOM en el encabezado
        nombre = row.get("nombre", row.get("\ufeffnombre", "")).strip()
        email = row["email"].strip()
        rol = row.get("rol", "").strip() or "asesor"
        campaña = row["campaña"].strip()
        doc_id = row["Id"].strip()

        data = {
            "nombre": nombre,
            "email": email,
            "rol": rol,
            "campaña": campaña
        }

        db.collection("usuarios").document(doc_id).set(data)
        print(f"✔️ Asesor creado: {nombre}")
