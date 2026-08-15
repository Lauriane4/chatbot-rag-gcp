import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from src.vector_store import GestionnaireVecteurs

# Instruction système d'entreprise (Prompt Template)
SYSTEM_PROMPT = """Tu es un assistant précis. Réponds à la question en t'appuyant UNIQUEMENT sur le contexte suivant. Si l'information n'y est pas, dis que tu ne sais pas.
Contexte fourni :
{contexte}

Question de l'utilisateur :
{question}

Réponse :"""
# Charge les variables définies dans le fichier .env
load_dotenv()

# Prompt strict anti-hallucination
SYSTEM_PROMPT = """Tu es un assistant IA d'entreprise expert et rigoureux.
Réponds à la question en t'appuyant EXCLUSIVEMENT sur le contexte fourni ci-dessous.
Sois précis, concis et ne donne que des informations réelles présentes dans le texte.

Règles strictes :
1. Si l'information ne se trouve pas dans le contexte, réponds : "Je ne trouve pas cette information dans les documents fournis."
2. Ne fais aucune supposition et n'invente rien.

Contexte :
{contexte}

Question : {question}
Réponse :"""

class MoteurRAG:
    """
    Moteur RAG (Retrieval-Augmented Generation).

     Description :
        Cette classe orchestre la recherche d'informations dans la base vectorielle,
        construit le prompt d'entreprise et communique avec un service d'inférence LLM
        (local ou hébergé) via une interface HTTP standard.

    Attributes:
        gestionnaire_db (GestionnaireVecteurs): L'instance active de la base vectorielle.
        nom_modele (str): Le nom du modèle de langage utilisé par le service d'inférence.
    
    """

    def __init__(self, gestionnaire_db: GestionnaireVecteurs, nom_modele: str = "gemini-3.6-flash"):
        """
        Initialise le moteur RAG avec son gestionnaire vectoriel.

        Args:
            gestionnaire_db (GestionnaireVecteurs): Instance de la base ChromaDB.
            nom_modele (str): Le nom du modèle de langage utilisé par le service d'inférence.
            
        """
        self.db = gestionnaire_db
        self.nom_modele = nom_modele or os.getenv("LLM_MODEL_NAME", "local-model")
        api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key else None

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
        donnees_prompt = self.preparer_prompt(question, top_k=top_k)
        chunks_pertinents = donnees_prompt["chunks"]
        prompt_final = donnees_prompt["prompt_final"]

        if not self.client:
            return {
                "question": question,
                "reponse": "⚠️ **Clé API manquante** : Vérifie que `GEMINI_API_KEY` est bien définie dans ton fichier `.env`.",
                "sources": chunks_pertinents
            }

        try:
            response = self.client.models.generate_content(
                model=self.nom_modele,
                contents=prompt_final,
                config=types.GenerateContentConfig(
                    temperature=0.0
                )
            )

            return {
                "question": question,
                "reponse": response.text,
                "sources": chunks_pertinents
            }

        except Exception as e:
            return {
                "question": question,
                "reponse": f"⚠️ **Erreur lors de l'appel au modèle** : `{str(e)}`",
                "sources": chunks_pertinents
            }