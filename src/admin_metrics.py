import os
import glob
import pandas as pd


class AnalyseurFeedback:
    """Analyse les fichiers de feedback mensuels pour le tableau de bord administrateur."""

    def __init__(self, dossier_logs: str = "logs"):
        self.dossier_logs = dossier_logs

    def lister_mois_disponibles(self) -> list[str]:
        """Retourne la liste des mois ayant des fichiers de logs."""
        fichiers = glob.glob(os.path.join(self.dossier_logs, "feedback_*.csv"))
        mois = []
        for f in fichiers:
            nom_base = os.path.basename(f)
            # Extrait YYYY_MM depuis feedback_YYYY_MM.csv
            m = nom_base.replace("feedback_", "").replace(".csv", "")
            mois.append(m)
        return sorted(mois, reverse=True)

    def charger_donnees_mois(self, mois: str) -> pd.DataFrame:
        """Charge le DataFrame correspondant au mois demandé."""
        chemin = os.path.join(self.dossier_logs, f"feedback_{mois}.csv")
        if os.path.exists(chemin):
            try:
                return pd.read_csv(chemin, encoding="utf-8")
            except Exception:
                return pd.DataFrame()
        return pd.DataFrame()

    def calculer_indicateurs(self, df: pd.DataFrame) -> dict:
        """Calcule les KPI de satisfaction et d'utilisation."""
        if df.empty:
            return {
                "total_questions": 0,
                "taux_satisfaction": 0.0,
                "nb_positifs": 0,
                "nb_negatifs": 0,
                "nb_sans_avis": 0
            }

        total = len(df)
        positifs = len(df[df["note_utilisateur"] == "positif"])
        negatifs = len(df[df["note_utilisateur"] == "negatif"])
        sans_avis = total - (positifs + negatifs)

        total_exprimes = positifs + negatifs
        taux_sat = (positifs / total_exprimes * 100) if total_exprimes > 0 else 0.0

        return {
            "total_questions": total,
            "taux_satisfaction": round(taux_sat, 1),
            "nb_positifs": positifs,
            "nb_negatifs": negatifs,
            "nb_sans_avis": sans_avis
        }