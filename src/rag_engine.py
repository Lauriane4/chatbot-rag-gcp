import os
import requests
from src.vector_store import GestionnaireVecteurs

# Instruction système d'entreprise (Prompt Template)
SYSTEM_PROMPT = """Tu es un assistant précis. Réponds à la question en t'appuyant UNIQUEMENT sur le contexte suivant. Si l'information n'y est pas, dis que tu ne sais pas.
Contexte fourni :
{contexte}

Question de l'utilisateur :
{question}

Réponse :"""


class MoteurRAG:
    """
    Moteur RAG (Retrieval-Augmented Generation) Agnostique.

     Description :
        Cette classe orchestre la recherche d'informations dans la base vectorielle,
        construit le prompt d'entreprise et communique avec un service d'inférence LLM
        (local ou hébergé) via une interface HTTP standard.

    Attributes:
        gestionnaire_db (GestionnaireVecteurs): L'instance active de la base vectorielle.
        nom_modele (str): Le nom du modèle de langage utilisé par le service d'inférence.
        endpoint_inference (str): L'URL du service d'inférence LLM.
    """

    def __init__(self, gestionnaire_db: GestionnaireVecteurs, nom_modele: str = None, endpoint_inference: str = None):
        """
        Initialise le moteur RAG avec son gestionnaire vectoriel.

        Args:
            gestionnaire_db (GestionnaireVecteurs): Instance de la base ChromaDB.
            nom_modele (str): Le nom du modèle de langage utilisé par le service d'inférence.
            endpoint_inference (str): L'URL du service d'inférence LLM.
        """
        self.db = gestionnaire_db
        self.nom_modele = nom_modele or os.getenv("LLM_MODEL_NAME", "local-model")
        self.endpoint_inference = endpoint_inference or os.getenv(
            "LLM_INFERENCE_ENDPOINT", 
            "http://localhost:11434/api/generate"
        )

    def construire_contexte(self, chunks: list[dict]) -> str:
        """
        Formate la liste des chunks trouvés en une seule chaîne de texte lisible.

        Exemple de sortie :
            [Extrait 1 | Source: contrat.pdf, Page: 1]
            Les congés doivent être déposés 2 semaines à l'avance...
            ----------------------------------------
            [Extrait 2 | Source: rh.pdf, Page: 3]
            Le portail RH permet de valider les absences...

        Args:
            chunks (list[dict]): La liste de dictionnaires renvoyée par ChromaDB.

        Returns:
            str: Le bloc de texte représentant l'ensemble des extraits pertinents.
        """
        if not chunks:
            return "Aucun document pertinent trouvé."

        blocs_contexte = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk["metadata"].get("source", "Inconnue")
            page = chunk["metadata"].get("page", "Inconnue")
            texte = chunk["texte"]

            bloc = f"[Extrait {i} | Source: {source}, Page: {page}]\n{texte}"
            blocs_contexte.append(bloc)

        return "\n\n----------------------------------------\n\n".join(blocs_contexte)

    def poser_question(self, question: str, top_k: int = 3) -> dict:
        """
        Exécute le pipeline RAG complet : recherche vectorielle, génération du prompt 
        et appel au service d'inférence LLM.

        Args:
            question (str): La question posée par l'utilisateur.
            top_k (int, optional): Nombre d'extraits pertinents à récupérer. Défaut: 3.

        Returns:
            dict: Dictionnaire contenant la question, la réponse générée et les sources d'origine.
        """
        # 1. Recherche des K morceaux les plus pertinents dans la base vectorielle
        chunks_pertinents = self.db.chercher_similaires(question, nombre_resultats=top_k)

        # 2. Construction du contexte et assemblage du prompt final
        contexte_formate = self.construire_contexte(chunks_pertinents)
        prompt_final = SYSTEM_PROMPT.format(
            contexte=contexte_formate,
            question=question
        )

        # 3. Préparation de la requête standard pour le service d'inférence
        payload = {
            "model": self.nom_modele,
            "prompt": prompt_final,
            "stream": False
        }

        try:
            # Envoi de la requête HTTP au service d'inférence LLM
            response = requests.post(self.endpoint_inference, json=payload, timeout=200)
            response.raise_for_status()
            donnees = response.json()
            
            # Extraction générique du texte généré
            reponse_texte = donnees.get("response") or donnees.get("content") or "Aucune réponse générée."

            return {
                "question": question,
                "reponse": reponse_texte,
                "sources": chunks_pertinents
            }

        except Exception as e:
            return {
                "question": question,
                "reponse": f"⚠️ **Service d'inférence LLM indisponible** : Impossible de contacter le serveur d'inférence à l'adresse `{self.endpoint_inference}`.\n\nDétail : `{str(e)}`",
                "sources": chunks_pertinents
            }

    def preparer_prompt(self, question: str, top_k: int = 3) -> dict:
        """
        Interroge ChromaDB pour trouver les chunks pertinents et génère le prompt final.

        Args:
            question (str): La question posée par l'utilisateur.
            top_k (int, optional): Nombre d'extraits à récupérer. Défaut: 3.

        Returns:
            dict: Dictionnaire contenant la question, le contexte extrait et le prompt complet.
        """
        # 1. Recherche des K morceaux les plus pertinents dans ChromaDB
        chunks_pertinents = self.db.chercher_similaires(question, nombre_resultats=top_k)

        # 2. Mise en forme du texte de contexte
        contexte_formate = self.construire_contexte(chunks_pertinents)

        # 3. Injection du contexte et de la question dans notre modèle de prompt
        prompt_final = SYSTEM_PROMPT.format(
            contexte=contexte_formate,
            question=question
        )

        return {
            "question": question,
            "chunks": chunks_pertinents,
            "contexte": contexte_formate,
            "prompt_final": prompt_final
        }