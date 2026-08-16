import os
import csv
from datetime import datetime


class GestionnaireFeedback:
    """Gère l'enregistrement et l'organisation des retours utilisateurs par mois."""

    def __init__(self, dossier_logs: str = "logs"):
        self.dossier_logs = dossier_logs
        os.makedirs(self.dossier_logs, exist_ok=True)

    def _obtenir_chemin_fichier_mensuel(self) -> str:
        """Génère le nom de fichier basé sur le mois et l'année en cours."""
        mois_actuel = datetime.now().strftime("%Y_%m")
        return os.path.join(self.dossier_logs, f"feedback_{mois_actuel}.csv")

    def enregistrer_interaction(
        self,
        id_interaction: str,
        question: str,
        reponse: str,
        sources: list,
        note: str,
        commentaire: str = ""
    ):
        """Enregistre ou met à jour une interaction dans le CSV du mois."""
        fichier_csv = self._obtenir_chemin_fichier_mensuel()
        fichier_existe = os.path.exists(fichier_csv)

        # Extraction propre des noms de fichiers sources
        noms_sources = []
        if sources:
            for s in sources:
                nom = s.get("metadata", {}).get("source", "Inconnue")
                noms_sources.append(nom)
        sources_str = " | ".join(set(noms_sources))

        champs = [
            "id_interaction",
            "date_heure",
            "question",
            "reponse",
            "sources",
            "note_utilisateur",
            "commentaire"
        ]

        # Mode écriture / mise à jour
        lignes = []
        maj_effectuee = False

        if fichier_existe:
            with open(fichier_csv, mode="r", encoding="utf-8", newline="") as f:
                lecteur = csv.DictReader(f)
                for row in lecteur:
                    if row["id_interaction"] == id_interaction:
                        row["note_utilisateur"] = note
                        row["commentaire"] = commentaire
                        maj_effectuee = True
                    lignes.append(row)

        if not maj_effectuee:
            nouvelle_ligne = {
                "id_interaction": id_interaction,
                "date_heure": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "question": question,
                "reponse": reponse,
                "sources": sources_str,
                "note_utilisateur": note,
                "commentaire": commentaire
            }
            lignes.append(nouvelle_ligne)

        with open(fichier_csv, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=champs)
            writer.writeheader()
            writer.writerows(lignes)